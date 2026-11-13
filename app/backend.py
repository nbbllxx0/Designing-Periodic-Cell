"""Session backends behind the GUI server, and the one-worker job queue.

MockBackend (default for development while E4 runs): never imports amm, never solves.
  * Spec tools (set_material, set_constraints, set_target, set_source, submit, undo, get_session, list_families)
    are a mirror of amm.tools.Session: same state, state hash, certificate keys and results. Recorded sessions
    replayed through the mirror reproduce their logged results and state hashes (tests/test_app.py).
  * Solver tools (check_bounds, atlas_suggest, evaluate, search, certify) return a *recorded* result: the index
    holds every call of the development sessions keyed by (tool, arguments, normalized targets, Poisson ratio,
    families); a certificate is keyed exactly like amm (`cert_key`). `evaluate` falls back to the nearest
    search-atlas row of the same kind. A call with no recorded result fails with a clear error.
  * Recorded sessions can be loaded whole (`load_recorded`): the GUI then shows that session and can continue it.

LiveBackend (app/live.py) wraps amm.tools.Session (imported in live mode only). Its solving tools run on the one
worker thread of the JobQueue, one at a time, each holding the shared solver lock.
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import io
import itertools
import json
import queue
import threading
import time
import uuid
import zipfile
from pathlib import Path

import numpy as np

from . import geom, mockdata, outcomes, physics, toolspec

SCHEMA_V1 = "amm-tools/1"
SCHEMA_VERSION = "amm-tools/2"                     # amm.tools.SCHEMA_VERSION (B1, 2026-11-07)
HEAVY = ("evaluate", "search", "certify", "as_built", "export", "screen_manufacturing")  # queued on the worker
SOLVER = ("check_bounds", "atlas_suggest") + HEAVY  # served from recordings in mock mode
MAX_EVAL = 16
MAX_SESSION_DESIGNS = 400
MAX_SESSION_CERTIFY = 4
MAX_SESSION_AS_BUILT = 8
V2_SUBMISSION_KEYS = ("outcome", "evidence")


def project_submission(sub, schema):
    """amm.tools.project_submission: a schema-1 session hashes and returns the submission without the B1 fields."""
    if sub is None or schema != SCHEMA_V1:
        return sub
    return {k: v for k, v in sub.items() if k not in V2_SUBMISSION_KEYS}
VOLATILE = ("seconds", "timing", "dt_s", "batch_seconds_per_cell", "static_s", "bloch_s", "t")


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default)


def _default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o).__name__)


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def strip_volatile(x):
    if isinstance(x, dict):
        return {k: strip_volatile(v) for k, v in x.items() if k not in VOLATILE}
    if isinstance(x, list):
        return [strip_volatile(v) for v in x]
    return x


def result_hash(result) -> str:
    return hashlib.sha256(canon(strip_volatile(result)).encode()).hexdigest()[:16]


def _floats(x):
    """Numbers as floats (for lookup keys: a recorded 80 and a GUI 80.0 are the same argument)."""
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        return {k: _floats(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_floats(v) for v in x]
    return x


class ToolError(ValueError):
    pass


class JobCancelled(BaseException):
    """Raised inside a running job when it is cancelled. Not an Exception, so fail-closed `except Exception`
    handlers (amm's solver wrappers, Session._call) do not turn a cancel into a result."""


# ================================================================================================================
# events and the job queue
# ================================================================================================================
class EventBus:
    def __init__(self):
        self.listeners: list = []
        self._seq = itertools.count(1)

    def publish(self, ev: dict):
        ev = dict(ev, id=next(self._seq), t=time.time())
        for fn in list(self.listeners):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001 -- a broken listener never stops the session
                pass


class JobQueue:
    """FIFO of solver calls run by ONE worker thread (one GPU). Jobs: queued -> running -> done | failed, or
    cancelled while queued. `execute(job)` returns the tool output."""

    def __init__(self, execute, bus: EventBus, cancellable=None):
        self.execute = execute
        self.bus = bus
        self.cancellable = cancellable or (lambda job: False)  # may a RUNNING job be cancelled (cooperatively)?
        self.jobs: dict[str, dict] = {}
        self.order: list[str] = []
        self._q: queue.Queue = queue.Queue()
        self._done: dict[str, threading.Event] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._last_progress: dict[str, float] = {}
        self._lock = threading.Lock()
        self.current: str | None = None
        self.worker = threading.Thread(target=self._run, name="amm-gpu-worker", daemon=True)
        self.worker.start()

    def submit(self, tool: str, args: dict, actor: str, kind: str = "tool") -> dict:
        jid = uuid.uuid4().hex[:10]
        job = dict(id=jid, kind=kind, tool=tool, args=args, actor=actor, status="queued", t_queued=time.time(),
                   t_start=None, t_end=None, output=None, progress=None, cancel_requested=False)
        with self._lock:
            self.jobs[jid] = job
            self.order.append(jid)
            self._done[jid] = threading.Event()
            self._cancel[jid] = threading.Event()
            job["position"] = sum(1 for j in self.jobs.values() if j["status"] == "queued")
        self._q.put(jid)
        self.bus.publish(dict(type="job", job=self.public(job)))
        return self.public(job)

    def cancel(self, jid: str) -> bool:
        """A queued job is dropped; a running one is asked to stop (only if `cancellable(job)`: the job's solver
        hooks raise JobCancelled at the next checkpoint and the call is rolled back)."""
        with self._lock:
            j = self.jobs.get(jid)
            if j is None:
                return False
            if j["status"] == "running" and self.cancellable(j):
                j["cancel_requested"] = True
                self._cancel[jid].set()
                running = True
            elif j["status"] == "queued":
                j["status"], j["t_end"] = "cancelled", time.time()
                self._cancel[jid].set()
                running = False
            else:
                return False
        if not running:
            self._done[jid].set()
        self.bus.publish(dict(type="job", job=self.public(j)))
        return True

    def cancel_event(self, jid: str) -> threading.Event:
        return self._cancel[jid]

    def progress(self, jid: str, info: dict, force: bool = False, every: float = 0.25):
        """Latest progress of a running job, broadcast as a "progress" event (at most every `every` seconds)."""
        j = self.jobs.get(jid)
        if j is None:
            return
        j["progress"] = info
        now = time.time()
        if force or now - self._last_progress.get(jid, 0.0) >= every:
            self._last_progress[jid] = now
            self.bus.publish(dict(type="progress", job_id=jid, tool=j["tool"], progress=info))

    def wait(self, jid: str, timeout: float | None = None) -> dict | None:
        ev = self._done.get(jid)
        if ev is None:
            return None
        ev.wait(timeout)
        return self.public(self.jobs[jid])

    def list(self, limit: int = 50) -> list[dict]:
        return [self.public(self.jobs[j]) for j in self.order[-limit:]]

    @staticmethod
    def public(j: dict) -> dict:
        return {k: v for k, v in j.items()}

    def _run(self):
        while True:
            jid = self._q.get()
            j = self.jobs[jid]
            if j["status"] != "queued":
                continue
            j["status"], j["t_start"], self.current = "running", time.time(), jid
            self.bus.publish(dict(type="job", job=self.public(j)))
            try:
                j["output"] = self.execute(j)
                j["status"] = "done" if (j["output"] or {}).get("ok", True) else "failed"
            except JobCancelled:
                j["output"] = dict(ok=False, error=f"{j['tool']} cancelled by the user after "
                                   f"{time.time() - j['t_start']:.0f} s; the call was rolled back (not logged)")
                j["status"] = "cancelled"
            except Exception as ex:  # noqa: BLE001
                j["output"], j["status"] = dict(ok=False, error=f"{type(ex).__name__}: {ex}"), "failed"
            j["t_end"], self.current = time.time(), None
            self._done[jid].set()
            self.bus.publish(dict(type="job", job=self.public(j)))


# ================================================================================================================
# mock session: a mirror of amm.tools.Session
# ================================================================================================================
class MockSession:
    def __init__(self, root: Path | None = None, profile: str = "C", index: "RecordedIndex | None" = None,
                 schema: str = SCHEMA_VERSION):
        self.root = Path(root) if root is not None else None
        self.profile = profile
        self.schema = schema if schema in (SCHEMA_V1, SCHEMA_VERSION) else SCHEMA_V1
        self.evidence: list[dict] = []           # amm.outcomes evidence records (B1)
        self.cert_seq: dict[str, int] = {}
        self.state: dict = dict(material=None, cell_size=None, targets={}, families=["tpms", "struts", "resonator"],
                                sources={}, gap_type=None)
        self.certs: dict[str, dict] = {}
        self.used = dict(designs=0, certify=0)
        self.submission: dict | None = None
        self.undo_stack: list = []
        self.seq = 0
        self.index = index
        self.records: list[dict] = []
        self.cert_files: dict[str, str] = {}   # cert_key -> path of the full certificate
        self.cert_origin: dict[str, str] = {}  # copied certificate file name -> recorded source path
        self._lock = threading.RLock()
        self.log_path = None
        head = dict(type="session", t=_now(), schema=self.schema, schema_version=self.schema, id=uuid.uuid4().hex[:12],
                    profile=profile, code=mockdata.code_hash(), mode="mock")
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
            self.log_path = self.root / "session.jsonl"
        self._append(head)

    # ---- plumbing ----------------------------------------------------------------------------------------------
    def _append(self, rec: dict):
        self.records.append(rec)
        if self.log_path is not None:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(canon(rec) + "\n")

    def state_hash(self) -> str:
        s = dict(self.state, certs=sorted(self.certs), submission=project_submission(self.submission, self.schema))
        return hashlib.sha256(canon(s).encode()).hexdigest()[:16]

    def tools(self) -> list[str]:
        return [t["name"] for t in toolspec.tool_specs() if self.profile in t["profiles"]
                and (self.schema != SCHEMA_V1 or t["since"] == SCHEMA_V1)]

    # ---- evidence (mirror of amm.tools.Session._evidence_ctx / _holds) -----------------------------------------
    def _evidence_ctx(self, name: str, args: dict) -> dict:
        norm, _ = self.normalized(strict=False)
        fams = list(args.get("families") or self.state["families"]) if name == "search" else list(self.state["families"])
        return dict(targets=norm, nu=(self._material() or {}).get("nu"), material=self.state["material"],
                    families=sorted(fams))

    def _holds(self, e: dict) -> bool:
        if e["tool"] == "set_target":
            return "gap" not in self.state["targets"]
        c = e["ctx"]
        norm, _ = self.normalized(strict=False)
        if canon(c["targets"]) != canon(norm) or c["nu"] != (self._material() or {}).get("nu"):
            return False
        if e["kind"].startswith("certificate_") and c["material"] != self.state["material"]:
            return False
        if e["kind"] in ("atlas_not_found", "search_not_found") and not set(self.state["families"]) <= set(c["families"]):
            return False
        return True

    def _material(self) -> dict | None:
        m = self.state["material"]
        if m is None:
            return None
        return physics.materials()[m] if isinstance(m, str) else m

    def _nu(self) -> float:
        m = self._material()
        if m is None:
            raise ToolError("no material: call set_material first (the solid's Poisson ratio enters every solve)")
        return float(m["nu"])

    def request(self) -> dict:
        r = dict(self.state["targets"])
        if self.state["material"] is not None:
            r["material"] = self.state["material"]
        if self.state["cell_size"] is not None:
            r["cell_size"] = self.state["cell_size"]
        return r

    def normalized(self, strict: bool = True) -> tuple[dict, list[str]]:
        t, missing, _ = physics.normalize(self.request())
        if strict and missing:
            raise ToolError("targets cannot be normalized: " + "; ".join(missing))
        return t, missing

    def cert_key(self, spec: dict, targets: dict) -> str:
        return hashlib.sha256(canon(dict(spec=spec, targets=targets, material=self.state["material"],
                                         nu=(self._material() or {}).get("nu"))).encode()).hexdigest()[:16]

    def phys(self, row: dict) -> dict:
        m = self._material()
        a = (self.state["cell_size"][0] * physics.LENGTH_UNITS[self.state["cell_size"][1]]
             if self.state["cell_size"] else None)
        out = {}
        if m is not None:
            for k in ("E100", "G", "bulk"):
                if row.get(k) is not None:
                    out[f"{k}_MPa"] = row[k] * m["E"] / 1e6
            if a is not None:
                out["gaps_Hz"] = [[g["f_lo"] * physics.c_t(m) / a, g["f_hi"] * physics.c_t(m) / a]
                                  for g in row.get("gaps", [])[:3]]
        return out

    def _spend(self, what: str, n: int):
        cap = dict(designs=MAX_SESSION_DESIGNS, certify=MAX_SESSION_CERTIFY)[what]
        if self.used[what] + n > cap:
            raise ToolError(f"session budget exhausted: {self.used[what]} of {cap} {what} used, this call needs {n}")
        self.used[what] += n

    @staticmethod
    def _spec(design: dict) -> dict:
        if not isinstance(design, dict) or set(design) != {"kind", "params"}:
            raise ToolError("design must be {kind, params}")
        try:
            return physics.design_spec(design)
        except ValueError as ex:
            raise ToolError(str(ex))

    # ---- calls -------------------------------------------------------------------------------------------------
    def call(self, name: str, args: dict | None = None, actor: str = "user") -> dict:
        with self._lock:
            return self._call(name, dict(args or {}), actor)

    def _validate(self, name: str, args: dict) -> dict:
        spec = next((t for t in toolspec.tool_specs() if t["name"] == name), None)
        names = {p["name"] for p in spec["params"]}
        extra = sorted(set(args) - names)
        if extra:
            raise ToolError("; ".join(f"{k}: Extra inputs are not permitted" for k in extra))
        miss = [p["name"] for p in spec["params"] if p["required"] and p["name"] not in args]
        if miss:
            raise ToolError("; ".join(f"{k}: Field required" for k in miss))
        return spec

    def _call(self, name: str, args: dict, actor: str, recorded: dict | None = None) -> dict:
        spec = next((t for t in toolspec.tool_specs() if t["name"] == name), None)
        if spec is None or name not in self.tools():
            return dict(ok=False, error=f"unknown tool {name!r}")
        self.seq += 1
        seq = self.seq
        self._seq_now = seq
        t0 = time.perf_counter()
        before = copy.deepcopy(self.state)
        source = None
        try:
            self._validate(name, args)
            if name in SOLVER:
                result, source = self._solver(name, args, recorded)
            else:
                result = json.loads(canon(getattr(self, "t_" + name)(**args)))
            ok, err = True, None
        except (ToolError, ValueError, TypeError, KeyError) as ex:
            ok, err, result = False, str(ex), None
            if isinstance(ex, LookupError) and not isinstance(ex, ToolError):
                err = f"internal error: {type(ex).__name__}: {ex}"
        if not ok and spec["mutates"]:
            self.state = before
        elif ok and spec["mutates"] and name != "undo" and before != self.state:
            self.undo_stack.append(before)
        for e in outcomes.schema_rules().evidence_from_result(name, result, ok, err):
            self.evidence.append(dict(e, seq=seq, tool=name, ctx=self._evidence_ctx(name, args)))
        if ok and self.schema == SCHEMA_V1 and name in ("submit", "get_session", "certify"):
            result = dict(result)
            result.pop("outcome_card", None)
            if name == "certify":
                result.pop("outcome", None)
            if name == "submit":
                result["submitted"] = project_submission(result["submitted"], self.schema)
        rec = dict(type="call", seq=seq, t=_now(), actor=actor, tool=name, args=json.loads(canon(args)), ok=ok,
                   state_hash=self.state_hash(), dt_s=round(time.perf_counter() - t0, 3), schema_version=self.schema)
        if ok:
            rec["result"] = result
            rec["result_hash"] = result_hash(result)
        else:
            rec["error"] = err
        if source is not None:
            rec["mock_source"] = source
        self._append(rec)
        out = dict(ok=ok, seq=seq, state_hash=rec["state_hash"], schema_version=self.schema)
        out.update(dict(result=result) if ok else dict(error=err))
        if source is not None:
            out["mock_source"] = source
        return out

    # ---- solver tools: recorded results ------------------------------------------------------------------------
    def lookup_key(self, name: str, args: dict) -> str:
        if name == "certify":
            norm, _ = self.normalized()
            return "certify:" + self.cert_key(self._spec(args["design"]), norm)
        nu = (self._material() or {}).get("nu")
        if name == "evaluate":
            return canon(["evaluate", [self._spec(d) for d in args.get("designs", [])], nu])
        norm, missing = self.normalized(strict=False)
        return canon([name, _floats(args), norm, missing, nu, self.state["families"]])

    def _solver(self, name: str, args: dict, recorded: dict | None):
        """(result, provenance) of a solver tool. `recorded` is the logged record when a recorded session is being
        loaded; otherwise the index is consulted."""
        if name == "certify":
            norm, _ = self.normalized()
            if not norm:
                raise ToolError("no targets set")
        elif name in ("search", "atlas_suggest"):
            norm, _ = self.normalized()
            if not norm:
                raise ToolError("no targets set")
        if name == "evaluate":
            designs = args.get("designs") or []
            if not 1 <= len(designs) <= MAX_EVAL:
                raise ToolError(f"give 1-{MAX_EVAL} designs")
            [self._spec(d) for d in designs]
        key = self.lookup_key(name, args)
        rec = recorded
        src = None
        if rec is None and self.index is not None:
            hit = self.index.get(key)
            if hit is not None:
                rec, src = hit["record"], dict(kind="recorded", session=hit["session"], seq=hit["record"]["seq"],
                                               dt_s=hit["record"].get("dt_s"))
        elif rec is not None:
            src = dict(kind="recorded", session="(loaded)", seq=rec.get("seq"), dt_s=rec.get("dt_s"))
        if rec is None and name == "evaluate":
            return self._evaluate_from_atlas(args["designs"]), dict(kind="atlas", note=(
                "mock: nearest search-atlas row of the same kind (recorded search-tier values, not a new solve)"))
        if rec is None:
            raise ToolError(f"mock mode: no recorded result for this {name} call (the solver is not run in mock "
                            "mode; use live mode after E4)")
        if not rec["ok"]:
            raise ToolError(rec.get("error", "recorded call failed"))
        result = rec["result"]
        # side effects that the real tool has on the session
        if name == "evaluate":
            self._spend("designs", len(args["designs"]))
        elif name == "search":
            self._spend("designs", int(args.get("budget", 32)))
        elif name == "certify":
            self._spend("certify", 1)
            norm, _ = self.normalized()
            spec = self._spec(args["design"])
            k = self.cert_key(spec, norm)
            full = mockdata.certificate(k)
            self.certs[k] = dict(verdict=result["verdict"], robust=result["robust"], material=self.state["material"],
                                 nu=self._nu(), checker=(full or {}).get("checker"))
            self.cert_seq[k] = self._seq_now
            p = mockdata.certificate_files().get(k)
            if p is not None:
                self.cert_files[k] = str(p)
        return result, src

    def _evaluate_from_atlas(self, designs: list[dict]) -> dict:
        nu = self._nu()
        if mockdata.atlas(nu) is None:
            raise ToolError(f"mock mode: no atlas at nu_s = {nu:g} and no recorded evaluate for these designs")
        specs = [self._spec(d) for d in designs]
        self._spend("designs", len(specs))
        out = []
        for sp in specs:
            hit = mockdata.nearest_atlas_row(sp["kind"], sp["params"], nu)
            if hit is None:
                raise ToolError(f"mock mode: no atlas row of kind {sp['kind']}")
            r, d = hit
            v = {k: r.get(k) for k in ("density", "E100", "G", "bulk", "nu100", "valid")}
            gaps = physics.complete_gaps(r["bands"], 0.01) if r.get("bloch_valid") and r.get("bands") else []
            v["gaps"] = [dict(f_lo=g["f_lo"], f_hi=g["f_hi"], rel=g["rel"]) for g in gaps[:3]]
            v.update(self.phys(dict(r, gaps=v["gaps"])))
            out.append(dict(design=dict(kind=sp["kind"], params=sp["params"]), **v,
                            mock=dict(atlas_params=r["spec"]["params"], param_distance=d)))
        return dict(results=out, tier="search (not certified)")

    # ---- spec tools (mirror of amm.tools.Session) --------------------------------------------------------------
    def t_set_material(self, name=None, E_Pa=None, nu=None, rho_kg_m3=None):
        if name is not None:
            if name not in physics.materials():
                raise ToolError(f"name: Input should be one of {', '.join(physics.materials())}")
            self.state["material"] = name
        elif None not in (E_Pa, nu, rho_kg_m3):
            E_Pa, nu, rho_kg_m3 = float(E_Pa), float(nu), float(rho_kg_m3)
            if not (E_Pa > 0 and rho_kg_m3 > 0 and -1 < nu < 0.5):
                raise ToolError("need E_Pa > 0, rho_kg_m3 > 0 and -1 < nu < 0.5")
            self.state["material"] = dict(E=E_Pa, nu=nu, rho=rho_kg_m3)
        else:
            raise ToolError("give a material name, or all of E_Pa, nu and rho_kg_m3")
        m = self._material()
        return dict(material=self.state["material"], E_Pa=m["E"], nu=m["nu"], rho_kg_m3=m["rho"],
                    atlas_available=mockdata.atlas_rows_exist(m["nu"]))

    def t_set_constraints(self, cell_size=None, cell_size_unit="mm", families=None):
        if cell_size is not None:
            cell_size = float(cell_size)
            if cell_size_unit not in physics.LENGTH_UNITS:
                raise ToolError(f"cell_size_unit: Input should be one of {list(physics.LENGTH_UNITS)}")
            if cell_size <= 0:
                raise ToolError("cell_size must be positive")
            self.state["cell_size"] = [cell_size, cell_size_unit]
        if families is not None:
            if not families:
                raise ToolError("families must not be empty")
            bad = [f for f in families if f not in ("tpms", "struts", "resonator")]
            if bad:
                raise ToolError(f"families: unknown {bad}")
            self.state["families"] = list(dict.fromkeys(families))
        return dict(cell_size=self.state["cell_size"], families=self.state["families"])

    @staticmethod
    def _stiff(v):
        if not isinstance(v, dict) or set(v) - {"value", "unit"} or "value" not in v:
            raise ToolError("stiffness target must be {value, unit}")
        u = v.get("unit")
        if u not in tuple(physics.PRESSURE_UNITS) + ("E_s",):
            raise ToolError(f"unit: Input should be one of {list(physics.PRESSURE_UNITS) + ['E_s']}")
        return float(v["value"]), u

    def t_set_target(self, density_max=None, density_min=None, E100_min=None, E100_max=None, G_min=None,
                     bulk_min=None, nu100_min=None, nu100_max=None, gap=None, gap_type=None, clear=False):
        t = {} if clear else dict(self.state["targets"])
        for k, v in dict(density_max=density_max, density_min=density_min, nu100_min=nu100_min,
                         nu100_max=nu100_max).items():
            if v is not None:
                t[k] = float(v)
        for k, v in dict(E100_min=E100_min, E100_max=E100_max, G_min=G_min, bulk_min=bulk_min).items():
            if v is not None:
                val, unit = self._stiff(v)
                t[k] = val if unit == "E_s" else [val, unit]
        if gap is not None:
            if not isinstance(gap, dict) or {"f_lo", "f_hi"} - set(gap):
                raise ToolError("gap must be {f_lo, f_hi, unit}")
            lo, hi, unit = float(gap["f_lo"]), float(gap["f_hi"]), gap.get("unit")
            if unit not in tuple(physics.FREQ_UNITS) + ("f*",):
                raise ToolError(f"gap.unit: Input should be one of {list(physics.FREQ_UNITS) + ['f*']}")
            if not 0 < lo < hi:
                raise ToolError("gap needs 0 < f_lo < f_hi (a band gap cannot contain f = 0)")
            t["gap"] = ({"f_lo": lo, "f_hi": hi} if unit == "f*" else {"f_lo": [lo, unit], "f_hi": [hi, unit]})
        if gap_type is not None:
            if gap_type != "complete":
                raise ToolError("gap_type: Input should be 'complete'")
            self.state["gap_type"] = gap_type
        self.state["targets"] = t
        norm, missing = self.normalized(strict=False)
        return dict(targets=t, normalized=norm, cannot_normalize_yet=missing)

    def t_set_source(self, key, source, note=""):
        if source not in ("stated", "derived", "assumed", "answered"):
            raise ToolError("source: Input should be 'stated', 'derived', 'assumed' or 'answered'")
        known = {"material", "cell_size", "families", "gap_type"} | set(self.state["targets"])
        if key not in known:
            raise ToolError(f"unknown key {key!r} (set keys: {sorted(known)})")
        self.state["sources"][key] = dict(source=source, note=note)
        return dict(sources=self.state["sources"])

    def t_ask_clarification(self, question, options):
        raise ToolError("no user is available to answer in this session")

    def t_list_families(self):
        f = toolspec.families()
        return dict(families=f["families"], rules=f["rules"],
                    units="lengths in units of the cell size a; density = solid fraction")

    def t_submit(self, decision, design=None, verdict=None, note="", evidence=None):
        if decision not in ("release", "refuse", "need_info"):
            raise ToolError("decision: Input should be 'release', 'refuse' or 'need_info'")
        if self.submission is not None:
            raise ToolError("already submitted")
        if evidence is not None and decision != "refuse":
            raise ToolError("evidence is cited by a refusal (a release cites its certificate itself)")
        R = outcomes.schema_rules()
        sub = dict(decision=decision, note=note)
        cited, outcome, card_design = [], None, None
        if decision == "release":
            if design is None:
                raise ToolError("release needs a design")
            norm, _ = self.normalized()
            spec = self._spec(design)
            cert = self.certs.get(self.cert_key(spec, norm))
            if self.profile == "C" and (cert is None or cert["verdict"] != "certified"):
                raise ToolError("release needs a certificate with verdict 'certified' for this design and the current "
                                "targets: call certify first" + (f" (its verdict was {cert['verdict']})" if cert else ""))
            sub.update(design=dict(kind=spec["kind"], params=spec["params"]), targets=norm, certificate=cert)
            card_design = sub["design"]
            if cert is not None and cert["verdict"] == "certified":
                outcome = "certified_candidate"
                k = self.cert_key(spec, norm)
                cited = [e for e in self.evidence if e["kind"] == "certificate_certified" and e["seq"] == self.cert_seq.get(k)]
            else:
                outcome = R.UNVERIFIED[0]
        elif decision == "refuse":
            if verdict is None:
                raise ToolError("refuse needs a verdict")
            sub["verdict"] = verdict
            allowed = R.VERDICT_EVIDENCE[verdict]
            held = [e for e in self.evidence if self._holds(e)]
            if evidence is not None:
                by_seq = {}  # one call can carry several records (check_bounds: bound and atlas)
                for e in self.evidence:
                    by_seq.setdefault(e["seq"], []).append(e)
                cited = []
                for q in dict.fromkeys(evidence):
                    es = by_seq.get(q)
                    if not es:
                        raise ToolError(f"{R.REFUSAL_ERROR}evidence seq {q} is not an evidence record of this "
                                        "session (get_session lists the records)")
                    fit = [e for e in es if e["kind"] in allowed]
                    if not fit:
                        kinds = ", ".join(f"{e['kind']} (supports {R.EVIDENCE_OUTCOME[e['kind']]})" for e in es)
                        raise ToolError(f"{R.REFUSAL_ERROR}evidence seq {q} is {kinds}, not a record for verdict "
                                        f"{verdict}")
                    fit = [e for e in fit if self._holds(e)]
                    if not fit:
                        raise ToolError(f"{R.REFUSAL_ERROR}evidence seq {q} was computed for another spec (targets, "
                                        "material or families changed since)")
                    cited += fit
            else:
                cited = [e for e in held if e["kind"] in allowed]
            if self.profile in R.EVIDENCE_PROFILES:
                if not cited:
                    raise ToolError(R.rejection(verdict, held))
                outcome = R.refusal_outcome(verdict, cited)
            else:
                outcome = R.VERDICT_OUTCOME.get(verdict)
        else:
            outcome = "need_info"
        sub["spec"] = dict(material=self.state["material"], nu=self._nu() if self.state["material"] else None,
                           cell_size=self.state["cell_size"], targets=dict(self.state["targets"]),
                           gap_type=self.state.get("gap_type"))
        sub["outcome"] = outcome
        sub["evidence"] = [dict(seq=e["seq"], tool=e["tool"], kind=e["kind"]) for e in cited]
        self.submission = sub
        return dict(submitted=sub, outcome_card=R.card(outcome, decision, verdict, cited, self.profile, card_design))

    def t_undo(self):
        if not self.undo_stack:
            raise ToolError("nothing to undo")
        self.state = self.undo_stack.pop()
        return dict(state=self.state)

    def t_get_session(self):
        norm, missing = self.normalized(strict=False)
        out = dict(state=self.state, normalized_targets=norm, cannot_normalize=missing,
                   certificates=self.certs, submission=project_submission(self.submission, self.schema),
                   profile=self.profile, tools=self.tools(), budget_used=dict(self.used),
                   budget=dict(designs=MAX_SESSION_DESIGNS, certify=MAX_SESSION_CERTIFY))
        if self.schema != SCHEMA_V1:  # schema 2 additions (amm.tools.Session.get_session)
            R = outcomes.schema_rules()
            out["budget_used"].setdefault("as_built", 0)
            out["budget"]["as_built"] = MAX_SESSION_AS_BUILT
            out.update(schema_version=self.schema, evidence=[
                dict(seq=e["seq"], tool=e["tool"], kind=e["kind"], outcome=R.EVIDENCE_OUTCOME[e["kind"]],
                     summary=e["summary"], holds_for_current_spec=self._holds(e)) for e in self.evidence])
        return out

    # ---- replay of a recorded log through the mirror -------------------------------------------------------------
    def apply_recorded(self, rec: dict) -> dict | None:
        """Re-execute one logged call. Spec tools run in the mirror; solver tools take the logged result. Returns a
        mismatch description or None. The new record keeps the original actor and the original solver result."""
        name, args = rec["tool"], rec.get("args") or {}
        if name == "ask_clarification":
            self.seq += 1
            r = dict(rec, seq=self.seq)
            r["state_hash"] = self.state_hash()
            self._append(r)
            out = dict(ok=rec["ok"], state_hash=r["state_hash"], result=rec.get("result"), error=rec.get("error"))
        elif name in SOLVER:
            out = self._call(name, args, rec.get("actor", "agent"), recorded=rec)
        else:
            out = self._call(name, args, rec.get("actor", "agent"))
        if out["ok"] != rec["ok"]:
            return dict(seq=rec["seq"], tool=name, field="ok", log=rec["ok"], mirror=out["ok"], error=out.get("error"))
        if rec["ok"] and result_hash(out["result"]) != rec.get("result_hash", result_hash(rec.get("result"))):
            return dict(seq=rec["seq"], tool=name, field="result")
        if out["state_hash"] != rec["state_hash"]:
            return dict(seq=rec["seq"], tool=name, field="state_hash", log=rec["state_hash"], mirror=out["state_hash"])
        return None


class RecordedIndex(dict):
    """{lookup key: {"record", "session"}} over every recorded development session (first occurrence wins)."""

    @classmethod
    def build(cls, sessions: dict | None = None) -> "RecordedIndex":
        idx = cls()
        idx.replay_checks = {}
        for sid, meta in (sessions or mockdata.sessions()).items():
            if meta.get("profile") not in ("B", "C"):
                continue
            s = MockSession(None, profile=meta["profile"], index=None, schema=meta.get("schema") or SCHEMA_V1)
            mism = []
            for rec in mockdata.read_log(mockdata.session_path(sid)):
                if rec.get("type") != "call":
                    continue
                if rec["tool"] in SOLVER and rec["ok"]:
                    try:
                        key = s.lookup_key(rec["tool"], rec.get("args") or {})
                        idx.setdefault(key, dict(record=rec, session=sid))
                    except (ToolError, ValueError, KeyError, TypeError):
                        pass
                try:
                    m = s.apply_recorded(rec)
                except Exception as ex:  # noqa: BLE001
                    m = dict(seq=rec.get("seq"), tool=rec["tool"], field="exception", error=str(ex))
                if m:
                    mism.append(m)
            idx.replay_checks[sid] = dict(n_mismatch=len(mism), first=mism[:3], same_code=meta.get("same_code"),
                                          replay_compatible=meta.get("replay_compatible"))
        return idx


# ================================================================================================================
# backends
# ================================================================================================================
class Backend:
    mode = "base"

    def __init__(self, root: Path, delay_scale: float = 0.0, delay_cap: float = 3.0):
        self.root_dir = Path(root)
        self.bus = EventBus()
        self.delay_scale, self.delay_cap = delay_scale, delay_cap
        self.queue = JobQueue(self._execute, self.bus, cancellable=self.cancellable)
        self.session = None
        self.session_meta: dict = {}

    def cancellable(self, job: dict) -> bool:
        return False

    def shutdown(self):
        """Stop cleanly (server shutdown); the base backend holds nothing."""

    def design_spec(self, design: dict) -> dict:
        return physics.design_spec(design)

    # ---- tool calls --------------------------------------------------------------------------------------------
    def call(self, name: str, args: dict | None, actor: str = "user", wait: bool = False,
             timeout: float | None = None) -> dict:
        """Run a tool. Solving tools go to the worker queue: returns {"job": ...} (or the finished output with
        wait=True). Other tools run at once and return the tool output."""
        args = dict(args or {})
        if name in HEAVY:
            job = self.queue.submit(name, args, actor)
            if wait:
                job = self.queue.wait(job["id"], timeout)
            return dict(job=job)
        out = self._direct(name, args, actor)
        self._after_call()
        return out

    def _direct(self, name, args, actor):
        return self.session.call(name, args, actor)

    def _execute(self, job: dict) -> dict:
        if job["kind"] == "details":
            return dict(ok=True, result=self._details_live(job["args"]))
        out = self._run_heavy(job)
        self._after_call()
        return out

    def _run_heavy(self, job):
        return self.session.call(job["tool"], job["args"], job["actor"])

    def _after_call(self):
        recs = self.records()
        if recs:
            self.bus.publish(dict(type="record", record=_lite(recs[-1])))
        self.bus.publish(dict(type="session", seq=self.session.seq, state_hash=self.session.state_hash()))

    # ---- views -------------------------------------------------------------------------------------------------
    def records(self) -> list[dict]:
        return list(self.session.records)

    def tool_list(self) -> list[dict]:
        prof = self.session.profile
        return [dict(t, available=prof in t["profiles"], queued=t["name"] in HEAVY) for t in toolspec.tool_specs()]

    def summary(self, tail: int = 200) -> dict:
        s = self.session
        norm, missing = s.normalized(strict=False)
        recs = self.records()
        calls = [r for r in recs if r.get("type") == "call"]
        return dict(mode=self.mode, meta=self.session_meta, profile=s.profile, state=s.state, normalized_targets=norm,
                    cannot_normalize=missing, certificates=s.certs, submission=s.submission, budget_used=s.used,
                    budget=dict(designs=MAX_SESSION_DESIGNS, certify=MAX_SESSION_CERTIFY), seq=s.seq,
                    state_hash=s.state_hash(), log=[_lite(r) for r in recs[-tail:]], n_records=len(recs),
                    focus=outcomes.focus_design(calls, s.submission), physical=self.physical(),
                    evidence=outcomes.cards(calls, s.submission, norm, self.cert_lookup),
                    outcome=outcomes.b1_view(s, calls), exports=self.exports(calls),
                    schema_version=getattr(s, "schema", None), root=str(s.root) if s.root else None)

    def physical(self) -> dict:
        """Material constants and unit-conversion factors for the GUI (E_s in Pa, c_t, a in m, f* -> Hz)."""
        s = self.session
        m = s._material()
        out = dict(material=None)
        if m is not None:
            out.update(material=dict(E=m["E"], nu=m["nu"], rho=m["rho"]), c_t=physics.c_t(m))
            if s.state["cell_size"]:
                a = s.state["cell_size"][0] * physics.LENGTH_UNITS[s.state["cell_size"][1]]
                out.update(a_m=a, fstar_to_Hz=physics.c_t(m) / a)
        return out

    def cert_lookup(self, design: dict, targets: dict) -> dict | None:
        """Full certificate held for a design and targets in this session (or recorded), with its file."""
        try:
            spec = self.design_spec(design)
        except (ValueError, KeyError, TypeError):
            return None
        k = self.session.cert_key(spec, targets)
        path = self._cert_path(k)
        if path is None:
            path = self._cert_by_content(spec, targets)
        if path is None:
            return None
        origin = getattr(self.session, "cert_origin", {}).get(Path(path).name)
        shown = origin or (str(Path(path).relative_to(mockdata.ROOT)).replace("\\", "/")
                           if Path(path).is_relative_to(mockdata.ROOT) else str(path))
        return dict(key=k, path=shown,
                    certificate=json.loads(Path(path).read_text(encoding="utf-8")))

    def _cert_by_content(self, spec: dict, targets: dict):
        """Certificates written before the cert key covered the material (audit F02) are found by content: same
        spec, targets and solver Poisson ratio, in this session's certificate folder."""
        if self.session.root is None:
            return None
        nu = (self.session._material() or {}).get("nu")
        want = canon(dict(spec=spec, targets=targets))
        for p in sorted((self.session.root / "certificates").glob("*.json")):
            try:
                c = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if canon(dict(spec=c.get("spec"), targets=c.get("targets"))) == want and \
                    (c.get("solver") or {}).get("nu") == nu:
                return p
        return None

    def _cert_path(self, key: str):
        if self.session.root is not None:
            hits = sorted((self.session.root / "certificates").glob(f"*_{key}.json"))
            if hits:
                return hits[0]
        return None

    def details(self, design: dict) -> dict:
        """Everything the result panels need for one design: preview statistics, search-tier tensor and bands,
        certificate data if held, in normalized and physical units."""
        spec = self.design_spec(design)
        out = dict(design=dict(kind=spec["kind"], params=spec["params"]), family=spec["family"])
        out["search"] = self._details_search(spec)
        norm, _ = self.session.normalized(strict=False)
        c = self.cert_lookup(design, norm)
        out["certificate"] = outcomes.certificate_view(c) if c else None
        out["physical"] = self.physical()
        return out

    def _details_search(self, spec):
        raise NotImplementedError

    def _details_live(self, args):
        raise NotImplementedError

    # ---- export ------------------------------------------------------------------------------------------------
    def export(self, design: dict | None = None, tiles: int = 3, n: int = 40) -> dict:
        """Export bundle (zip): cell.stl, tiled STL, report.json (spec, design, evidence cards, certificate summary,
        provenance), session.jsonl, the full certificate if held. Geometry is the voxel-centre PREVIEW surface;
        mock mode only: live mode exports through the amm `export` tool (certified geometry model, screening)."""
        summ = self.summary(tail=10 ** 6)
        if design is None:
            design = summ["focus"]
        if design is None:
            raise ValueError("no design to export (choose or certify a design first)")
        spec = physics.design_spec(design)
        tiles = int(min(max(tiles, 1), 6))
        m = geom.mask(spec["kind"], spec["params"], n)
        cs = self.session.state["cell_size"]
        scale_mm = cs[0] * physics.LENGTH_UNITS[cs[1]] * 1e3 if cs else 1.0
        v1, f1 = geom.boundary_mesh(m, periodic=False)
        vt, ft = geom.boundary_mesh(np.tile(m, (tiles, tiles, tiles)), periodic=False)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = f"amm_export_{stamp}_{uuid.uuid4().hex[:4]}.zip"
        norm = summ["normalized_targets"]
        cert = self.cert_lookup(design, norm)
        report = dict(schema="amm-gui-export/0", created=_now(), mode=self.mode, code=mockdata.code_hash(),
                      session=self.session_meta, state=summ["state"], normalized_targets=norm,
                      design=dict(kind=spec["kind"], params=spec["params"], family=spec["family"]),
                      submission=summ["submission"], evidence=summ["evidence"],
                      certificate=outcomes.certificate_view(cert) if cert else None,
                      geometry=dict(kind="preview voxel-centre mask surface", n=n, tiles=tiles,
                                    density_preview=float(m.mean()), unit="mm" if cs else "cell units (a = 1)",
                                    scale_mm=scale_mm if cs else None),
                      disclaimers=[
                          "Preview geometry (binary mask at voxel centres); the certificate is computed on amm's "
                          "anti-aliased finite-cell voxelization. The certified-geometry export and the "
                          "manufacturing screening are the amm tools export and screen_manufacturing (live mode).",
                          "No printability claim.",
                          "Search-tier values are not certificates." + (
                              " Mock mode: solver results are recorded results from development sessions."
                              if self.mode == "mock" else "")])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("cell.stl", geom.stl_bytes(v1, f1, scale=scale_mm, name=f"amm {spec['kind']} cell"))
            z.writestr(f"tiled_{tiles}x{tiles}x{tiles}.stl",
                       geom.stl_bytes(vt, ft, scale=scale_mm * tiles, name=f"amm {spec['kind']} {tiles}^3"))
            z.writestr("report.json", json.dumps(report, indent=1, default=_default))
            z.writestr("session.jsonl", "".join(canon(r) + "\n" for r in self.records()))
            if cert:
                z.writestr(f"certificate_{cert['key']}.json", json.dumps(cert["certificate"], indent=1))
        d = self.export_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(buf.getvalue())
        self.bus.publish(dict(type="export", name=name))
        return dict(name=name, url=f"/api/files/{name}", bytes=len(buf.getvalue()),
                    files=["cell.stl", f"tiled_{tiles}x{tiles}x{tiles}.stl", "report.json", "session.jsonl"]
                    + ([f"certificate_{cert['key']}.json"] if cert else []), n_triangles=int(len(ft)))

    def export_dir(self) -> Path:
        return (self.session.root or self.root_dir) / "exports"

    # ---- amm export tool output (B2) ------------------------------------------------------------------------------
    def exports(self, calls: list[dict]) -> list[dict]:
        """Results of the amm `export` and `screen_manufacturing` calls of this session, newest first, with download
        URLs for the files the export tool wrote under <session>/exports/<name>/."""
        out = []
        for r in reversed(calls):
            if r.get("tool") not in ("export", "screen_manufacturing") or not r.get("ok"):
                continue
            res = r.get("result") or {}
            item = dict(seq=r["seq"], tool=r["tool"], design=(r.get("args") or {}).get("design"), result=res)
            if r["tool"] == "export":
                item["files"] = {k: dict(v, url="/api/session-files/" + v["path"]) for k, v in
                                 (res.get("files") or {}).items()}
                item["zip_url"] = f"/api/export-zip/{res.get('name')}"
            out.append(item)
        return out[:6]

    def session_file(self, rel: str) -> Path:
        """A file the export tool wrote (path relative to the session folder; only inside exports/)."""
        root = Path(self.session.root or self.root_dir).resolve()
        p = (root / rel).resolve()
        if not p.is_relative_to(root / "exports") or not p.is_file():
            raise KeyError(rel)
        return p

    def export_zip(self, name: str) -> tuple[bytes, str]:
        """One export folder of the amm export tool, plus the session log, as a zip."""
        root = Path(self.session.root or self.root_dir).resolve()
        d = (root / "exports" / name).resolve()
        if d.parent != root / "exports" or not d.is_dir():
            raise KeyError(name)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(d.iterdir()):
                if f.is_file():
                    z.write(f, f"{name}/{f.name}")
            lp = getattr(self.session, "log_path", None)
            if lp is not None and Path(lp).is_file():
                z.write(lp, f"{name}/session.jsonl")
        return buf.getvalue(), f"{name}.zip"


def _lite(rec: dict) -> dict:
    """A log record for the GUI timeline: large results are summarized (full ones via /api/session/record)."""
    r = dict(rec)
    if "result" in r and len(canon(r["result"])) > 4000:
        r["result"] = dict(_truncated=True, keys=sorted(r["result"]) if isinstance(r["result"], dict) else None)
    return r


class MockBackend(Backend):
    mode = "mock"

    def __init__(self, root: Path, delay_scale: float = 0.0, delay_cap: float = 3.0, load: str | None = None):
        super().__init__(root, delay_scale, delay_cap)
        self.index = RecordedIndex.build()
        self.new_session()
        if load:
            self.load_recorded(load)

    def _session_root(self, label: str) -> Path:
        return self.root_dir / f"mock-{time.strftime('%Y%m%d-%H%M%S')}-{label}-{uuid.uuid4().hex[:4]}"

    def new_session(self, profile: str = "C") -> dict:
        self.session = MockSession(self._session_root("new"), profile=profile, index=self.index)
        self.session_meta = dict(kind="new", profile=profile)
        self.bus.publish(dict(type="session", seq=0, reset=True))
        return self.summary()

    def load_recorded(self, sid: str) -> dict:
        meta = mockdata.sessions()[sid]
        s = MockSession(self._session_root(sid.replace("/", "-")), profile=meta["profile"] or "C", index=self.index,
                        schema=meta.get("schema") or SCHEMA_V1)
        mism = []
        for rec in mockdata.read_log(mockdata.session_path(sid)):
            if rec.get("type") == "call":
                m = s.apply_recorded(rec)
                if m:
                    mism.append(m)
        # certificates of that session, by the same file names
        src = mockdata.session_path(sid).parent / "certificates"
        if src.is_dir():
            dst = s.root / "certificates"
            dst.mkdir(exist_ok=True)
            for p in src.glob("*.json"):
                (dst / p.name).write_bytes(p.read_bytes())
                s.cert_origin[p.name] = str(p.relative_to(mockdata.ROOT)).replace("\\", "/")
        self.session = s
        self.session_meta = dict(kind="recorded", id=sid, source=meta["path"], brief=mockdata.brief_text(sid),
                                 same_code=meta["same_code"], replay=dict(n_mismatch=len(mism), first=mism[:3]))
        self.bus.publish(dict(type="session", seq=s.seq, reset=True))
        return self.summary()

    def _cert_path(self, key):
        return super()._cert_path(key) or mockdata.certificate_files().get(key)

    def cancellable(self, job: dict) -> bool:
        return self.delay_scale > 0  # the replay delay is waited BEFORE the call, so a cancel logs nothing

    def _run_heavy(self, job):
        if self.delay_scale > 0:
            rec = None
            try:
                hit = self.index.get(self.session.lookup_key(job["tool"], job["args"]))
                rec = hit["record"] if hit else None
            except (ToolError, ValueError, KeyError, TypeError):
                pass
            dt = min(((rec or {}).get("dt_s") or 0.0) * self.delay_scale, self.delay_cap)
            if dt:
                self.queue.progress(job["id"], dict(stage=f"mock replay of a recorded {job['tool']} ({dt:.1f} s)",
                                                    elapsed_s=0.0), force=True)
                if self.queue.cancel_event(job["id"]).wait(dt):
                    raise JobCancelled(job["id"])
        return self.session.call(job["tool"], job["args"], job["actor"])

    def _details_search(self, spec):
        nu = (self.session._material() or {}).get("nu")
        if nu is None:
            return dict(available=False, reason="set a material first (its Poisson ratio selects the atlas)")
        hit = mockdata.nearest_atlas_row(spec["kind"], spec["params"], nu)
        if hit is None:
            return dict(available=False, reason=f"no search atlas at nu_s = {nu:g}")
        v = _search_view(hit[0], source=dict(kind="atlas", nu=nu, atlas_params=hit[0]["spec"]["params"],
                                             param_distance=hit[1], note="mock: nearest search-atlas row "
                                             "(recorded search-tier solve), not a new evaluation"))
        v["tensor"] = cubic_tensor_view(hit[0], "mock: cubic reconstruction from the atlas row's C11, C12, C44 "
                                                "(atlas rows store the cubic constants only)")
        return v


def cubic_tensor_view(row: dict, source: str) -> dict | None:
    """6x6 Voigt C* rebuilt from the cubic constants (rows without the full tensor), with derived quantities."""
    C = {k: row.get(k) for k in ("C11", "C12", "C44")}
    if None in C.values():
        return None
    M = physics.voigt_cubic(**C)
    return dict(C=M.tolist(), derived=dict(physics.tensor_summary(M), C11=C["C11"], C12=C["C12"], C44=C["C44"],
                                           zener=row.get("zener"), cubic_deviation=row.get("cubic_deviation"),
                                           min_eig=row.get("min_eig")),
                kind="cubic", source=source)


def _search_view(row: dict, source: dict) -> dict:
    bands = row.get("bands")
    ok_b = bool(row.get("bloch_valid") and bands)
    C = {k: row.get(k) for k in ("C11", "C12", "C44")}
    return dict(available=True, tier="search (not certified)", source=source, density=row.get("density"),
                valid=row.get("valid"), cubic=physics.cubic_summary(**C) if None not in C.values() else None,
                bands=bands if ok_b else None, ticks=physics.kpath_ticks(len(bands)) if ok_b else [],
                gaps=[dict(g) for g in physics.complete_gaps(bands, 0.01)[:3]] if ok_b else [])
