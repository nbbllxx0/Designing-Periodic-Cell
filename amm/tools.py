"""Tool contract of the agent layer: typed tools, a logged session, and LLM-free replay.

Pattern from AgenticTO (agentto.tools), re-implemented for unit cells:
  * every tool is a Session method registered with @tool: arguments are validated by a pydantic model built from
    the signature (extra keys forbidden), the call runs, and one record is appended to session.jsonl
    {seq, t, actor, tool, args, ok, result | error, state_hash, dt_s};
  * `replay(log)` re-runs every call of a log in a fresh session without any LLM and compares ok, state hash and
    the full result (timing fields removed). The gate of week 4 is that replay is exact;
  * profiles select the tools an arm sees: "B" = spec, ask, evaluate, search, submit (no bounds, no certificates);
    "C" = everything ("full system"). Arm D has no tools.

Units: the agent states targets in physical units (Pa, Hz) or normalized ones ("E_s" = fraction of the solid's
Young's modulus, "f*" = f a / c_t). The session converts with amm.units; physics runs on normalized values.
Results carry both. Search-tier values are labelled as such and are never certificates.

Release rule in profile C: `submit(decision="release")` needs a certificate with verdict "certified" for that
design and the current targets, computed by `certify` in this session. The agent can read certificates but has no
way to write one.

Refusal rule in profile C (B1, 2026-11-07): `submit(decision="refuse")` must cite an evidence record held in the
session for the current spec (amm.outcomes): a bound record (`check_bounds` with a violated rigorous bound),
a bounded-search or atlas record (nothing found in the declared families), or an undetermined certificate. Every
submission carries one of the outcomes of amm.outcomes (five plus need_info) and returns an outcome card.

Schema versions. Tool results follow schema "amm-tools/2" (SCHEMA_VERSION; every call record and the session
header carry `schema_version`). Version 2 only ADDS to version 1: the tools as_built, screen_manufacturing and
export; the full tensor C* in evaluate; outcome and evidence in submit; schema_version and evidence in
get_session. A log written with "amm-tools/1" is replayed in a session of that schema, whose results and state
hash are the version-1 projection of the current ones (`project`), so unchanged behaviour replays exactly; a
changed decision (the refusal rule) is reported by `replay`, not hidden.
Schema "amm-tools/3" (B9, 2026-11-08) only adds the optional `bands` argument of `evaluate` (default False: the
result is the schema-2 result) and, when it is true, a `bands` field per design. A schema-2 log replays in a
schema-2 session (no `bands` argument offered); its contract is unchanged (`contract("amm-tools/2")`).

Calls (B9). `Session.call` is transactional: a call interrupted by a BaseException (KeyboardInterrupt, a cancel
through amm.progress) writes no record and leaves seq, budget, certificates and spec as they were. Optional
`progress` and `cancel` hooks (amm.progress) report from, and stop, the long solves at natural boundaries. The
read-only tools of CONCURRENT_READ do not wait for a running solve (see `Session.call`).
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import inspect
import json
import threading
import time
import typing
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from . import atlas, bounds, data, outcomes, progress as _progress, units

SCHEMA_V1 = "amm-tools/1"
SCHEMA_V2 = "amm-tools/2"
SCHEMA_VERSION = "amm-tools/3"
SCHEMAS = (SCHEMA_V1, SCHEMA_V2, SCHEMA_VERSION)


def schema_at_least(schema: str, since: str) -> bool:
    return SCHEMAS.index(schema) >= SCHEMAS.index(since)


PROFILES = ("B", "C")
VOLATILE = ("seconds", "timing", "dt_s", "batch_seconds_per_cell", "static_s", "bloch_s", "t")
# Search atlas location. None (default): amm.data.data_dir() at each call ($AMM_DATA_DIR if set, else results/atlas
# of the source checkout; B6-1 fixed in B9). Set it to a folder to override both.
ATLAS_DIR: Path | None = None
# Read-only tools that do not wait for a running solve (Session.call): they read only the spec, the evidence held,
# the atlas and the budget / certificates as they were before the running call.
CONCURRENT_READ = ("get_session", "check_bounds", "atlas_suggest", "list_families")
# Code identity: the certificate checker hash of earlier amm code (results/software/NOTES_B1B3.md, NOTES_B9.md),
# for replaying logs whose results record no checker (an export of an uncertified design); see `replay`.
KNOWN_CHECKERS = {"90f3823f15cbeff4": "f2e482d81382b400", "dc9d810c7020a7e9": "f141e46cb67a78db",
                  "5970bf55108f1584": "f141e46cb67a78db"}
MAX_EVAL = 16
# session budgets, equal for both arms (audit F07, 2026-11-06); never reached in the 56 development sessions
# (max 288 designs, 3 certificates)
MAX_SESSION_DESIGNS = 400
MAX_SESSION_CERTIFY = 4
MAX_SESSION_AS_BUILT = 8  # schema 2

# ----------------------------------------------------------------------------------------------------------------
# argument types
# ----------------------------------------------------------------------------------------------------------------
Family = Literal["tpms", "struts", "resonator"]
Kind = Literal["gyroid", "schwarz_p", "diamond", "iwp", "sc", "bcc", "octet", "cube_bars", "sphere_ligaments"]


class Stiffness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float
    unit: Literal["Pa", "kPa", "MPa", "GPa", "psi", "E_s"] = Field(
        description='"E_s": fraction of the solid material\'s Young\'s modulus')


class Gap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    f_lo: float
    f_hi: float
    unit: Literal["Hz", "kHz", "MHz", "f*"] = Field(description='"f*": normalized frequency f a / c_t')


class Design(BaseModel):
    """A cell design. Parameters by kind: TPMS {density, mode: sheet|network}; sc/bcc/octet {r, R} (strut radius,
    node-sphere radius, R = 0 or R >= r + 0.03); cube_bars {c, w}; sphere_ligaments {c, w}. Lengths in cell units."""
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    params: dict[str, float | str]


class ClarifyOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(description="short answer text shown to the user")
    set: dict[str, Any] = Field(default_factory=dict, description=(
        'what choosing it sets, with the keys of the session state: material (name), cell_size ([value, unit]), '
        'gap_type ("complete"), or a target key (density_max, E100_min, G_min, bulk_min, nu100_min, nu100_max, '
        'gap)'))


# ----------------------------------------------------------------------------------------------------------------
# registry
# ----------------------------------------------------------------------------------------------------------------
TOOLS: dict[str, dict] = {}


def tool(*, mutates: bool = False, profiles=PROFILES, replay: str = "run", since: str = SCHEMA_V1,
         arg_since: dict | None = None):
    """since: the schema version that introduced the tool (a session of an older schema does not offer it).
    arg_since: {argument: schema version that introduced it}; a session of an older schema rejects the argument
    (its argument model is the one of that schema; the argument then takes its default)."""
    arg_since = dict(arg_since or {})

    def deco(fn):
        params = list(inspect.signature(fn).parameters.values())[1:]
        hints = typing.get_type_hints(fn, include_extras=True)
        models, params_by = {}, {}
        for sch in SCHEMAS:
            ps = [p for p in params if schema_at_least(sch, arg_since.get(p.name, SCHEMA_V1))]
            fields = {p.name: (hints.get(p.name, Any), ... if p.default is inspect.Parameter.empty else p.default)
                      for p in ps}
            models[sch] = create_model(f"{fn.__name__}_args", __config__=ConfigDict(extra="forbid"), **fields)
            params_by[sch] = ps
        TOOLS[fn.__name__] = dict(fn=fn, model=models[SCHEMA_VERSION], models=models, params_by=params_by,
                                  mutates=mutates, profiles=set(profiles), replay=replay,
                                  doc=inspect.getdoc(fn) or "", params=params, since=since, arg_since=arg_since)
        return fn
    return deco


class ToolError(ValueError):
    pass


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default)


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    if isinstance(o, BaseModel):
        return o.model_dump(mode="json")
    raise TypeError(type(o).__name__)


def _plain(x):
    """JSON-plain copy (numpy scalars and arrays, pydantic models)."""
    return json.loads(canon(x))


def strip_volatile(x):
    if isinstance(x, dict):
        return {k: strip_volatile(v) for k, v in x.items() if k not in VOLATILE}
    if isinstance(x, list):
        return [strip_volatile(v) for v in x]
    return x


def result_hash(result) -> str:
    return hashlib.sha256(canon(strip_volatile(result)).encode()).hexdigest()[:16]


# ---- schema projection: what a schema-1 session returns is the schema-2 result minus the fields schema 2 added
V2_SUBMISSION_KEYS = ("outcome", "evidence")
V2_EVALUATE_KEYS = ("C", "derived", "C_MPa")
V3_EVALUATE_KEYS = ("bands",)  # present only when evaluate(bands=True), which schemas 1 and 2 do not accept
V1_BUDGET_KEYS = ("designs", "certify")


def project_submission(sub: dict | None, schema: str) -> dict | None:
    if sub is None or schema != SCHEMA_V1:
        return sub
    return {k: v for k, v in sub.items() if k not in V2_SUBMISSION_KEYS}


def project(tool: str, result: dict | None, schema: str) -> dict | None:
    """The result of `tool` as schema `schema` defines it. Schema 2 only adds fields, so the schema-1 result is the
    schema-2 result without them (the values of every other field are the same objects)."""
    if schema == SCHEMA_VERSION or result is None:
        return result
    if schema == SCHEMA_V2:  # schema 3 adds only the optional evaluate bands, which a schema-2 session never asks for
        if tool == "evaluate" and any("bands" in x for x in result["results"]):
            result = dict(result, results=[{k: v for k, v in x.items() if k not in V3_EVALUATE_KEYS}
                                           for x in result["results"]])
        return result
    r = dict(result)
    if tool == "evaluate":
        r["results"] = [{k: v for k, v in x.items() if k not in V2_EVALUATE_KEYS + V3_EVALUATE_KEYS}
                        for x in r["results"]]
    elif tool == "certify":
        r.pop("outcome", None)
    elif tool == "submit":
        r.pop("outcome_card", None)
        r["submitted"] = project_submission(r["submitted"], schema)
    elif tool == "get_session":
        r.pop("schema_version", None)
        r.pop("evidence", None)
        r["submission"] = project_submission(r["submission"], schema)
        r["budget_used"] = {k: v for k, v in r["budget_used"].items() if k in V1_BUDGET_KEYS}
        r["budget"] = {k: v for k, v in r["budget"].items() if k in V1_BUDGET_KEYS}
    return r


NOT_HASHED = ("bench.py", "llm.py", "mcp_server.py", "cli.py")


def code_hash() -> str:
    """Hash of the sources that determine tool results: a replay is exact only against the code that wrote the
    log. Excluded: the clarification oracle (bench.py; replay takes answers from the log), the LLM CLI runner
    (llm.py), the MCP transport (mcp_server.py) and the command line (cli.py, V2: a thin wrapper over Session.call)."""
    h = hashlib.sha256()
    for f in sorted(Path(__file__).resolve().parent.glob("*.py")):
        if f.name in NOT_HASHED:
            continue
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _short_errors(ex: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in ex.errors()[:6])


# computed outputs that a request may try to state as a target (V2-2, 2026-11-08: refused with the reason)
OUTPUT_QUANTITIES = ("zener", "anisotropy", "c11", "c12", "c44", "e110", "e111", "cubic_deviation", "min_eig")


def _output_hint(name: str, args) -> str:
    """The reason a set_target key that names a computed output (Zener ratio, cubic constants, E110 / E111) is
    refused, appended to the validation message (which alone says only "Extra inputs are not permitted")."""
    if name != "set_target" or not isinstance(args, dict):
        return ""
    known = {p.name for p in TOOLS["set_target"]["params"]}
    bad = [k for k in args if k not in known and any(str(k).lower().startswith(q) for q in OUTPUT_QUANTITIES)]
    if not bad:
        return ""
    return (f"; {', '.join(bad)}: not a design target: the Zener ratio, the cubic constants C11, C12, C44 and "
            "E110 / E111 are computed outputs of evaluate (results[].derived), never targets or certified "
            "quantities. Targets: density_min, density_max, E100_min, E100_max, G_min, bulk_min, nu100_min, "
            "nu100_max, gap")


_ATLAS: dict[tuple, list] = {}


def atlas_dir() -> Path:
    """The folder the search atlas is read from: ATLAS_DIR if set, else amm.data.data_dir() (AMM_DATA_DIR, or
    results/atlas of the source checkout), resolved at each call."""
    return Path(ATLAS_DIR) if ATLAS_DIR is not None else data.data_dir()


def atlas_path(nu: float) -> Path:
    return atlas_dir() / f"atlas_nu{nu:g}.jsonl"


def atlas_rows(nu: float) -> list | None:
    """Atlas rows at this Poisson ratio, or None when no atlas file exists for it (see atlas_missing)."""
    p = atlas_path(nu)
    key = (str(p), round(nu, 4))
    if key not in _ATLAS:
        rows = atlas.load(str(p)) if p.exists() else None
        if rows is None:
            return None  # not cached: the files may appear later (AMM_DATA_DIR set, data downloaded)
        _ATLAS[key] = rows
    return _ATLAS[key]


def atlas_missing(nu: float) -> str:
    """Why atlas_rows(nu) is None. A Poisson ratio outside the data set keeps its earlier message (it is in logs);
    a missing file says what was not found, where amm looked, and how to set AMM_DATA_DIR (B6-2)."""
    if not any(abs(nu - x) < 5e-5 for x in data.ATLAS_NUS):
        return f"no atlas at nu_s = {nu:g} (atlases: 0.3, 0.342, 0.39)"
    return data.missing_message(f"the search atlas for nu_s = {nu:g}", atlas_path(nu),
                                None if ATLAS_DIR is None else f"amm.tools.ATLAS_DIR = {ATLAS_DIR}")


def error_model_missing() -> str | None:
    """None when the search-tier error model (amm.atlas.error_model_path) exists, else a clear message (B6-3)."""
    p = Path(atlas.error_model_path())
    if p.is_file():
        return None
    return data.missing_message("the search-tier error model error_model.json", p)


# ----------------------------------------------------------------------------------------------------------------
# session
# ----------------------------------------------------------------------------------------------------------------
class _ReadView:
    """The session as a concurrent read sees it while a non-mutating call runs (Session.call): the budget and
    certificates as they were when that call started; everything else is the live session (the spec, which a
    non-mutating call does not change, and the evidence, which a running call adds only when it commits)."""

    def __init__(self, session, used: dict, certs: dict):
        self._session, self.used, self.certs = session, used, certs

    def __getattr__(self, k):
        return getattr(self._session, k)


class Session:
    def __init__(self, root: str | Path | None = None, profile: str = "C", answerer=None,
                 schema: str = SCHEMA_VERSION):
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {PROFILES}")
        if schema not in SCHEMAS:
            raise ValueError(f"schema must be one of {SCHEMAS}")
        self.root = Path(root) if root is not None else None
        self.profile = profile
        self.schema = schema                      # SCHEMA_V1 only to replay a version-1 log (see `project`)
        self.state: dict = dict(material=None, cell_size=None, targets={}, families=["tpms", "struts", "resonator"],
                                sources={}, gap_type=None)
        self.certs: dict[str, dict] = {}          # key(design, targets) -> certificate summary
        self.used = dict(designs=0, certify=0, as_built=0)  # session budget use (MAX_SESSION_*)
        self.evidence: list[dict] = []            # evidence records (amm.outcomes), one per supporting result
        self._cert_full: dict[str, dict] = {}     # key -> full certificate (as_built, export)
        self._cert_seq: dict[str, int] = {}       # key -> seq of the certify call
        self._evaluated: dict[str, dict] = {}     # canon(spec, nu) -> last evaluate row (export report)
        self.checker_alias: dict[str, str] = {}   # replay only: current checker hash -> the logged one
        self.code_alias: str | None = None        # replay only: the logged code hash (export report identity)
        self._state_lock = threading.RLock()      # short: seq numbers, commit of a record, concurrent reads
        self._inflight = None                     # _ReadView of the running non-mutating call (Session.call)
        self._seq_now = None
        self.submission: dict | None = None
        self.undo_stack: list = []
        self.seq = 0
        self.answerer = answerer                  # callable(question, options) -> {"choice", "label", "comment"}
        self.replay_answer: dict | None = None
        self._lock = threading.RLock()            # MCP clients may send calls concurrently: run them one at a time
        self.log_path = None
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
            self.log_path = self.root / "session.jsonl"
            from .certify import checker_hash
            self._append(dict(type="session", t=_now(), schema=schema, schema_version=schema,
                              id=uuid.uuid4().hex[:12], profile=profile, code=code_hash(), checker=checker_hash()))

    # ---- plumbing --------------------------------------------------------------------------------------------
    def _append(self, rec: dict):
        if self.log_path is not None:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(canon(rec) + "\n")

    def state_hash(self) -> str:
        s = dict(self.state, certs=sorted(self.certs), submission=project_submission(self.submission, self.schema))
        return hashlib.sha256(canon(s).encode()).hexdigest()[:16]

    def tools(self) -> list[str]:
        return [n for n, t in TOOLS.items() if self.profile in t["profiles"] and schema_at_least(self.schema, t["since"])]

    def call(self, name: str, args: dict | None = None, actor: str = "script", progress=None, cancel=None) -> dict:
        """Validate, run and log one call. Returns {"ok", "seq", "result" | "error", "state_hash"}.

        progress, cancel: optional hooks for the long solves (amm.progress): `progress(info)` is called at the
        solvers' natural boundaries, and when `cancel.is_set()` (e.g. a threading.Event) the next boundary raises
        amm.progress.Cancelled. Defaults None: no hook, no change.

        Transactional: if the call is interrupted by a BaseException (Cancelled, KeyboardInterrupt) no record is
        written and seq, budget, certificates, spec and evidence are restored; the exception propagates. (Files a
        tool had already written, a certificate JSON or export files, stay; they are rewritten by a repeat call.)

        Concurrency: calls run one at a time (the log order is the execution order), with one exception. The
        read-only tools of CONCURRENT_READ do not wait while a NON-mutating call (a solve) runs: they are answered
        at once, from the session as it was when the running call started (the spec, which that call cannot
        change; the evidence held; the budget and certificates before that call), and their records are written
        before the running call's record. Executing the log in file order therefore gives the same results, and
        `replay` uses the logged seq numbers, so it is exact. While a mutating call runs they wait (it is fast)."""
        concurrent = name in CONCURRENT_READ
        while True:
            if self._lock.acquire(timeout=0.05) if concurrent else self._lock.acquire():
                try:
                    with _progress.hooks(progress, cancel):
                        return self._call(name, args, actor)
                finally:
                    self._lock.release()
            with self._state_lock:
                if self._inflight is not None:
                    return self._call(name, args, actor, view=self._inflight)

    def _snapshot(self) -> dict:
        return dict(seq=self.seq, seq_now=self._seq_now, used=dict(self.used), certs=dict(self.certs),
                    cert_full=dict(self._cert_full), cert_seq=dict(self._cert_seq), evaluated=dict(self._evaluated),
                    state=copy.deepcopy(self.state), undo=list(self.undo_stack), submission=self.submission)

    def _rollback(self, snap: dict, seq: int | None, view) -> None:
        """Undo an interrupted call (no record was written). A concurrent read restores only its own seq number
        and evidence; the running call it read from is untouched."""
        with self._state_lock:
            if seq is not None:
                if self.seq == seq:  # else a concurrent read took a later number: leave a gap, never reuse one
                    self.seq = seq - 1
                self.evidence[:] = [e for e in self.evidence if e["seq"] != seq]
            if view is not None:
                return
            self._seq_now = snap["seq_now"]
            self.used, self.certs = snap["used"], snap["certs"]
            self._cert_full, self._cert_seq, self._evaluated = snap["cert_full"], snap["cert_seq"], snap["evaluated"]
            self.state, self.undo_stack, self.submission = snap["state"], snap["undo"], snap["submission"]
            self._inflight = None

    def _call(self, name: str, args: dict | None, actor: str, view=None) -> dict:
        args = dict(args or {})
        if name not in TOOLS or name not in self.tools():
            return dict(ok=False, error=f"unknown tool {name!r}")
        t = TOOLS[name]
        model, params = t["models"][self.schema], t["params_by"][self.schema]
        me = self if view is None else view        # a concurrent read runs on the view of the running call
        snap = self._snapshot() if view is None else None
        seq, committed = None, False
        try:
            with self._state_lock:
                self.seq += 1
                seq = self.seq
                if view is None:
                    self._seq_now = seq
                    if not t["mutates"]:
                        self._inflight = _ReadView(self, dict(self.used), dict(self.certs))
            t0 = time.perf_counter()
            before = snap["state"] if snap is not None else None
            answer = None
            kw = {}
            try:
                parsed = model.model_validate(args)
                kw = {p.name: getattr(parsed, p.name) for p in params}
                result = _plain(t["fn"](me, **kw))
                ok, err = True, None
                if name == "ask_clarification":
                    answer = result.get("answer")
            except ValidationError as ex:
                ok, err, result = False, _short_errors(ex) + _output_hint(name, args), None
            except (ToolError, ValueError) as ex:
                ok, err, result = False, str(ex), None
            except Exception as ex:                # noqa: BLE001 -- a tool bug is reported, never kills the server
                ok, err, result = False, f"internal error: {type(ex).__name__}: {ex}", None
            with self._state_lock:                 # commit: evidence, then the record (the commit point)
                if not ok and t["mutates"]:
                    self.state = before
                elif ok and t["mutates"] and name != "undo" and before != self.state:
                    self.undo_stack.append(before)
                for e in outcomes.evidence_from_result(name, result, ok, err):
                    self.evidence.append(dict(e, seq=seq, tool=name, ctx=self._evidence_ctx(name, kw)))
                result = project(name, result, self.schema)
                rec = dict(type="call", seq=seq, t=_now(), actor=actor, tool=name, args=_plain(args), ok=ok,
                           state_hash=Session.state_hash(me), dt_s=round(time.perf_counter() - t0, 3),
                           schema_version=self.schema)
                if ok:
                    rec["result"] = result
                    rec["result_hash"] = result_hash(result)
                else:
                    rec["error"] = err
                if answer is not None:
                    rec["answer"] = answer
                self._append(rec)
                committed = True
                if view is None:
                    self._inflight = None
        except BaseException:
            if not committed:
                self._rollback(snap, seq, view)
            raise
        out = dict(ok=ok, seq=seq, state_hash=rec["state_hash"], schema_version=self.schema)
        out.update(dict(result=result) if ok else dict(error=err))
        return out

    # ---- evidence (amm.outcomes) -------------------------------------------------------------------------------
    def _evidence_ctx(self, name: str, kw: dict) -> dict:
        """The spec an evidence record was computed for."""
        try:
            norm, _ = self.normalized(strict=False)
        except Exception:  # noqa: BLE001
            norm = None
        fams = list(kw.get("families") or self.state["families"]) if name == "search" else list(self.state["families"])
        return dict(targets=norm, nu=(self._material() or {}).get("nu"), material=self.state["material"],
                    families=sorted(fams))

    def _holds(self, e: dict) -> bool:
        """Whether evidence record e supports a decision on the CURRENT spec (amm.outcomes, matching rules)."""
        if e["tool"] == "set_target":  # W1 rejection on input: valid while the request still states no gap
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

    def _held(self) -> list[dict]:
        return [e for e in self.evidence if self._holds(e)]

    # ---- helpers ---------------------------------------------------------------------------------------------
    def _material(self) -> dict | None:
        m = self.state["material"]
        if m is None:
            return None
        return units.MATERIALS[m] if isinstance(m, str) else m

    def _nu(self) -> float:
        m = self._material()
        if m is None:
            raise ToolError("no material: call set_material first (the solid's Poisson ratio enters every solve)")
        return float(m["nu"])

    def request(self) -> dict:
        """The state as an amm.units request."""
        r = dict(self.state["targets"])
        if self.state["material"] is not None:
            r["material"] = self.state["material"]
        if self.state["cell_size"] is not None:
            r["cell_size"] = self.state["cell_size"]
        return r

    def normalized(self, strict: bool = True) -> tuple[dict, list[str]]:
        t, missing, _ = units.normalize(self.request())
        if strict and missing:
            raise ToolError("targets cannot be normalized: " + "; ".join(missing))
        return t, missing

    def _phys(self, row: dict) -> dict:
        m, a = self._material(), (self.state["cell_size"][0] * units.LENGTH_UNITS[self.state["cell_size"][1]]
                                   if self.state["cell_size"] else None)
        out = {}
        if m is not None:
            for k in ("E100", "G", "bulk"):
                if row.get(k) is not None:
                    out[f"{k}_MPa"] = row[k] * m["E"] / 1e6
            if a is not None:
                out["gaps_Hz"] = [[g["f_lo"] * units.c_t(m) / a, g["f_hi"] * units.c_t(m) / a]
                                  for g in row.get("gaps", [])[:3]]
        return out

    def _design_spec(self, d: Design) -> dict:
        p = dict(d.params)
        fam = atlas.family_of(d.kind)
        mode = p.pop("mode", None)
        if fam == "tpms" and mode not in atlas.TPMS_MODES:
            raise ToolError(f"TPMS design needs params.mode in {list(atlas.TPMS_MODES)}")
        try:
            p = {k: float(v) for k, v in p.items()}
        except (TypeError, ValueError):
            raise ToolError("design parameters must be numbers (plus mode for TPMS)")
        box = atlas.box(d.kind)
        if set(p) != set(box):
            raise ToolError(f"{d.kind} takes parameters {sorted(box)} (got {sorted(p)})")
        for k, (lo, hi) in box.items():
            if not lo <= p[k] <= hi:
                raise ToolError(f"{d.kind}.{k} = {p[k]} outside the family box [{lo}, {hi}]")
        if not atlas.valid(d.kind, p):
            raise ToolError(f"{d.kind} parameters {p} violate the family's validity rule")
        return atlas.make_spec(d.kind, p, mode)

    def _spend(self, what: str, n: int):
        cap = dict(designs=MAX_SESSION_DESIGNS, certify=MAX_SESSION_CERTIFY, as_built=MAX_SESSION_AS_BUILT)[what]
        if self.used[what] + n > cap:
            raise ToolError(f"session budget exhausted: {self.used[what]} of {cap} {what} used, this call needs {n}")
        self.used[what] += n

    def _cert_key(self, spec: dict, targets: dict) -> str:
        """A certificate is bound to the geometry, the normalized targets AND the physics it was computed with
        (material, Poisson ratio): a change of material never reuses it (audit F02, 2026-11-06)."""
        return hashlib.sha256(canon(dict(spec=spec, targets=targets, material=self.state["material"],
                                         nu=(self._material() or {}).get("nu"))).encode()).hexdigest()[:16]

    # ---- spec ------------------------------------------------------------------------------------------------
    @tool(mutates=True)
    def set_material(self, name: Literal["PA12", "Ti6Al4V", "316L", "AlSi10Mg"] | None = None,
                     E_Pa: float | None = None, nu: float | None = None, rho_kg_m3: float | None = None) -> dict:
        """Set the solid material: a known name, or E_Pa, nu and rho_kg_m3 together. Its Poisson ratio enters every
        solve; E and density convert stiffness and frequency targets."""
        if name is not None:
            self.state["material"] = name
        elif None not in (E_Pa, nu, rho_kg_m3):
            if not (E_Pa > 0 and rho_kg_m3 > 0 and -1 < nu < 0.5):
                raise ToolError("need E_Pa > 0, rho_kg_m3 > 0 and -1 < nu < 0.5")
            self.state["material"] = dict(E=E_Pa, nu=nu, rho=rho_kg_m3)
        else:
            raise ToolError("give a material name, or all of E_Pa, nu and rho_kg_m3")
        m = self._material()
        return dict(material=self.state["material"], E_Pa=m["E"], nu=m["nu"], rho_kg_m3=m["rho"],
                    atlas_available=atlas_rows(m["nu"]) is not None)

    @tool(mutates=True)
    def set_constraints(self, cell_size: float | None = None, cell_size_unit: Literal["mm", "cm", "m", "um", "in"] = "mm",
                        families: list[Family] | None = None) -> dict:
        """Set the unit-cell size a (frequencies scale as 1/a) and the cell families allowed."""
        if cell_size is not None:
            if cell_size <= 0:
                raise ToolError("cell_size must be positive")
            self.state["cell_size"] = [cell_size, cell_size_unit]
        if families is not None:
            if not families:
                raise ToolError("families must not be empty")
            self.state["families"] = list(dict.fromkeys(families))
        return dict(cell_size=self.state["cell_size"], families=self.state["families"])

    @tool(mutates=True)
    def set_target(self, density_max: float | None = None, density_min: float | None = None,
                   E100_min: Stiffness | None = None, E100_max: Stiffness | None = None, G_min: Stiffness | None = None,
                   bulk_min: Stiffness | None = None, nu100_min: float | None = None, nu100_max: float | None = None,
                   gap: Gap | None = None, gap_type: Literal["complete"] | None = None, clear: bool = False) -> dict:
        """Set design targets (replaces only the keys given; clear=True starts from no targets). Stiffness in
        pressure units or "E_s"; density = solid fraction; E100 = Young's modulus along a cube axis; gap = a
        complete elastic-wave band gap covering [f_lo, f_hi] (all directions and polarizations)."""
        t = {} if clear else dict(self.state["targets"])
        for k, v in dict(density_max=density_max, density_min=density_min, nu100_min=nu100_min,
                         nu100_max=nu100_max).items():
            if v is not None:
                t[k] = float(v)
        for k, v in dict(E100_min=E100_min, E100_max=E100_max, G_min=G_min, bulk_min=bulk_min).items():
            if v is not None:
                if k.endswith("_min") and not v.value > 0:  # V2-3: bound rule P1 (amm.bounds), enforced on input
                    raise ToolError(f"{k} must be positive: a minimum modulus <= 0 constrains nothing (bound P1); "
                                    "leave it out")
                t[k] = v.value if v.unit == "E_s" else [v.value, v.unit]
        if gap is not None:
            if not 0 < gap.f_lo < gap.f_hi:
                raise ToolError("gap needs 0 < f_lo < f_hi (a band gap cannot contain f = 0)")
            t["gap"] = ({"f_lo": gap.f_lo, "f_hi": gap.f_hi} if gap.unit == "f*" else
                        {"f_lo": [gap.f_lo, gap.unit], "f_hi": [gap.f_hi, gap.unit]})
        if gap_type is not None:
            self.state["gap_type"] = gap_type
        self.state["targets"] = t
        norm, missing = self.normalized(strict=False)
        return dict(targets=t, normalized=norm, cannot_normalize_yet=missing)

    @tool(mutates=True)
    def set_source(self, key: str, source: Literal["stated", "derived", "assumed", "answered"], note: str = "") -> dict:
        """Record where a spec item came from: stated in the brief, derived from it, assumed, or answered by the
        user. Keys: material, cell_size, families, or a target key."""
        known = {"material", "cell_size", "families", "gap_type"} | set(self.state["targets"])
        if key not in known:
            raise ToolError(f"unknown key {key!r} (set keys: {sorted(known)})")
        self.state["sources"][key] = dict(source=source, note=note)
        return dict(sources=self.state["sources"])

    # ---- check -----------------------------------------------------------------------------------------------
    @tool(profiles=("C",))
    def check_bounds(self) -> dict:
        """Rigorous physics bounds on the current targets (Voigt, Hashin-Shtrikman advisory, cubic stability, gap
        rules) and the family-atlas verdict: PROVEN_INFEASIBLE (a bound is violated, named), NOT_FOUND_IN_FAMILIES
        (no atlas cell can meet it even with the most favourable search-tier error), FEASIBLE (an atlas cell meets
        it with the least favourable error) or BORDERLINE. NOT_FOUND is not a proof of impossibility."""
        norm, missing = self.normalized(strict=False)
        if not norm:
            raise ToolError("no targets that can be normalized yet" + (": " + "; ".join(missing) if missing else ""))
        nu = self._nu()
        b = bounds.check(norm, nu_s=nu, missing=missing)
        out = dict(bounds_verdict=b["verdict"], violated=b["violated"], advisory=b["advisory"],
                   normalized_targets=norm, cannot_normalize=missing)
        rows = atlas_rows(nu)
        err_missing = error_model_missing() if rows is not None else None
        if rows is None:
            out["atlas"] = dict(verdict="UNAVAILABLE", note=atlas_missing(nu))
        elif err_missing:  # the oracle needs the calibrated error ranges (B6-3)
            out["atlas"] = dict(verdict="UNAVAILABLE", note=err_missing)
        else:
            fam = set(self.state["families"])
            o = atlas.oracle([r for r in rows if r["spec"]["family"] in fam], norm)
            out["atlas"] = dict(verdict=o["verdict"], n_cells=o["n_cells"], n_clear=o["n_clear"],
                                n_possible=o["n_possible"], best=o["best"][:3],
                                note="search-tier atlas with calibrated error ranges; FEASIBLE is not a certificate")
        # V2-4: a request that cannot be stated in solver units yet is UNDERSPECIFIED as a whole (the atlas verdict
        # of its normalizable part stays in out["atlas"]); before, the partial atlas verdict was the top-level one
        out["verdict"] = ("PROVEN_INFEASIBLE" if b["violated"] else "UNDERSPECIFIED" if missing
                          else out["atlas"]["verdict"])
        return out

    @tool(replay="answer")
    def ask_clarification(self, question: str, options: list[ClarifyOption]) -> dict:
        """Ask the user one question with 2-5 options. The answer is returned; choosing an option does NOT change
        the spec, so apply it with set_material / set_constraints / set_target afterwards."""
        if not 2 <= len(options) <= 5:
            raise ToolError("give 2-5 options")
        opts = [o.model_dump() for o in options]
        if self.replay_answer is not None:
            ans = self.replay_answer
        elif self.answerer is None:
            raise ToolError("no user is available to answer in this session")
        else:
            ans = self.answerer(question, opts)
        return dict(question=question, answer=ans)

    # ---- design ----------------------------------------------------------------------------------------------
    @tool()
    def list_families(self) -> dict:
        """The cell families, their kinds, parameter boxes and validity rules."""
        from . import geometry
        out = {}
        for fam, kinds in geometry.FAMILIES.items():
            out[fam] = {k: dict(params={n: list(b) for n, b in atlas.box(k).items()},
                                modes=list(atlas.TPMS_MODES) if fam == "tpms" else None) for k in kinds}
        return dict(families=out, rules=dict(
            struts="R = 0 (no node sphere) or R >= r + 0.03",
            cube_bars="w <= c - 0.04", sphere_ligaments="w <= 2 c - 0.02",
            tpms="network TPMS do not percolate below density ~0.10 (Schwarz P ~0.15)"),
            units="lengths in units of the cell size a; density = solid fraction")

    @tool()
    def atlas_suggest(self, top: int = 5) -> dict:
        """The atlas cells (2,722 precomputed cells per material Poisson ratio, search tier) that come closest to the
        current targets, best first, with nominal and pessimistic slack (> 0 means met). Search-tier values, NOT
        certificates; costs no evaluations. Same in every profile (audit F07)."""
        if not 1 <= top <= 10:
            raise ToolError("top must be 1-10")
        norm, _ = self.normalized()
        if not norm:
            raise ToolError("no targets set")
        rows = atlas_rows(self._nu())
        if rows is None:
            raise ToolError(atlas_missing(self._nu()))
        if error_model_missing():
            raise ToolError(error_model_missing())
        fam = set(self.state["families"])
        o = atlas.oracle([r for r in rows if r["spec"]["family"] in fam], norm, top=top)
        out = []
        for b in o["best"]:
            sp = b["spec"]
            out.append(dict(design=dict(kind=sp["kind"], params=sp["params"]),
                            slack_nominal=b["slack_nominal"], slack_pess=b["slack_pess"]))
        return dict(best=out, normalized_targets=norm, tier="search (not certified)")

    @tool(arg_since={"bands": SCHEMA_VERSION})
    def evaluate(self, designs: list[Design], bands: Annotated[bool, Field(description=(
            "schema amm-tools/3: also return each design's search-tier band structure (`bands`: f* per k-point "
            "and band on the k-path G-X-M-G-R-X, with the k-points and labels; large, so off by default)"))] = False
                 ) -> dict:
        """Search-tier properties of up to 16 designs (fast, about 1-2 s each; NOT certified, biased stiff and
        high in frequency by several %): density, E100, G, bulk, nu100 (normalized by E_s), complete band gaps
        (normalized f* = f a / c_t, and Hz when material and cell size are set), and the full homogenized tensor
        C (6x6 Voigt, order 11 22 33 23 13 12, engineering shear, normalized by E_s; C_MPa with a material) with
        derived quantities (cubic constants, Zener ratio, directional E100/E110/E111, Voigt-Reuss averages,
        eigenvalues)."""
        if not 1 <= len(designs) <= MAX_EVAL:
            raise ToolError(f"give 1-{MAX_EVAL} designs")
        from . import evaluate as ev, tensor
        specs = [self._design_spec(d) for d in designs]
        self._spend("designs", len(specs))
        rows = ev.evaluate_batch(specs, nu=self._nu(), keep_bands=True, keep_tensor=True,
                                 **atlas.SEARCH_TIER)  # gaps need bands
        out = []
        m = self._material()
        for r in rows:
            v = {k: r.get(k) for k in ("density", "E100", "G", "bulk", "nu100", "valid")}
            v["gaps"] = [dict(f_lo=g["f_lo"], f_hi=g["f_hi"], rel=g["rel"]) for g in atlas.row_gaps(r, 0.01)[:3]]
            v.update(self._phys(dict(r, gaps=v["gaps"])))
            if r.get("C") is not None:  # schema 2: the full tensor and what follows from it
                C = r["C"]
                v["C"] = C
                v["derived"] = dict({k: r[k] for k in ("C11", "C12", "C44", "zener", "cubic_deviation", "min_eig")},
                                    **tensor.summary(C), voigt_order=tensor.VOIGT_ORDER,
                                    note="C11, C12, C44 are cubic averages; E100/E110/E111 from the full tensor")
                if m is not None:
                    v["C_MPa"] = (C * (m["E"] / 1e6)).tolist()
            row = dict(design=dict(kind=r["spec"]["kind"], params=r["spec"]["params"]), **v)
            self._evaluated[canon([r["spec"], self._nu()])] = dict(row)  # export report: never with the bands
            if bands:  # schema 3 (G5): the band structure the gaps were read from
                row["bands"] = self._band_data(r)
            out.append(row)
        return dict(results=out, tier="search (not certified)")

    def _band_data(self, row: dict) -> dict | None:
        """The search-tier band structure of one evaluate_batch row (None when the coarse mesh does not percolate:
        no bands are computed, and no gap is reported)."""
        import numpy as np
        from . import bloch
        f = row.get("bands")
        if f is None:
            return None
        f = np.asarray(f)
        ks, ticks = bloch.kpath(atlas.SEARCH_TIER["npts"])
        out = dict(f_star=f.tolist(), k_over_pi=np.round(ks / np.pi, 6).tolist(),
                   k_ticks=[[int(i), lab] for i, lab in ticks], n_bloch=atlas.SEARCH_TIER["n_bloch"],
                   n_bands=int(f.shape[1]), unit="f* = f a / c_t", tier="search (not certified)")
        m, a = self._material(), self._cell_size_m()
        if m is not None and a is not None:
            out["hz_per_f_star"] = units.c_t(m) / a
        return out

    @tool()
    def search(self, budget: int = 32, families: list[Family] | None = None,
               objective: Literal["expected", "pess", "nominal"] = "expected", margin: float = 0.0) -> dict:
        """Bayesian optimization (BoTorch) over the family parameters for the current targets, seeded by the
        family atlas. Slack = relative distance to the nearest target (> 0 means met). objective "expected" uses
        search-tier values corrected by the calibrated median error; margin asks for slack > margin. Returns the 5
        best designs with nominal / expected / pessimistic slack. Search-tier values, NOT certificates. Takes 1-15
        minutes (wide gap targets take longest); tools run one call at a time, so wait for the result."""
        if not 8 <= budget <= 96:
            raise ToolError("budget must be 8-96 evaluations")
        norm, _ = self.normalized()
        if not norm:
            raise ToolError("no targets set")
        try:
            from . import search as srch
        except ImportError as e:
            raise ToolError(str(e))
        nu = self._nu()
        if error_model_missing():  # B6-3: the objective needs the calibrated error ranges; no uncorrected fallback
            raise ToolError("search cannot run: " + error_model_missing() + ". search ranks designs by the "
                            "error-corrected slack and reports calibrated domains, so it does not run uncorrected")
        self._spend("designs", budget)
        fams = families or self.state["families"]
        rows = atlas_rows(nu)
        r = srch.search(norm, nu=nu, families=fams, budget=budget, q=8, objective=objective, seed=0,
                        atlas_rows=[x for x in rows if x["spec"]["family"] in fams] if rows else None)
        best = []
        for b in r["best"]:
            d = dict(design=dict(kind=b["spec"]["kind"], params=b["spec"]["params"]),
                     slack_nominal=b["slack_nominal"], slack_expected=b["slack_expected"],
                     slack_pess=b["slack_pess"], values=b["values"],
                     gaps=[dict(f_lo=g["f_lo"], f_hi=g["f_hi"], rel=g["rel"]) for g in b["gaps"]],
                     calibrated_domain=b["calibrated"], from_atlas=b["from_atlas"])
            d.update(self._phys(dict(b["values"], gaps=d["gaps"])))
            best.append(d)
        key = f"slack_{objective}"
        return dict(best=best, found=bool(best and best[0][key] > margin), objective=objective, margin=margin,
                    n_evaluations=r["n_evaluations"], arms=r["arms"], normalized_targets=norm,
                    atlas_seeded=rows is not None, tier="search (not certified)")

    # ---- release ---------------------------------------------------------------------------------------------
    @tool(profiles=("C",))
    def certify(self, design: Design) -> dict:
        """Certificate of one design against the current targets (2-20 minutes; wait for the result): static properties by a three-
        resolution ladder with grid phases and a guarded error bound; complete band gap by inertia counts over the
        Brillouin zone at two resolutions with an edge-convergence guard; as-built offset +-0.01 a as a robustness
        flag. Verdict: certified / refuted / undetermined (inside the guard band: neither proven nor disproven).
        Only a certified design can be released."""
        from . import certify as cf
        norm, _ = self.normalized()
        if not norm:
            raise ToolError("no targets set")
        spec = self._design_spec(design)
        self._spend("certify", 1)
        c = cf.certify(spec, norm, nu=self._nu())
        st, bl = c["blocks"]["static"], c["blocks"].get("bloch")
        conv = (st.get("convergence") or {}).get("quantities") or {}
        summ = dict(design=dict(kind=spec["kind"], params=spec["params"]), verdict=c["verdict"], robust=c["robust"],
                    static=dict(verdict=st["verdict"], rung=st.get("used"),
                                bounds={q: dict(lower=v["lower"], upper=v["upper"]) for q, v in conv.items()},
                                checks_failed=st.get("checks_failed")),
                    targets=norm, spec_hash=c["spec_hash"])
        if bl is not None:
            cv = bl.get("convergence") or {}
            summ["gap"] = dict(verdict=bl["verdict"], safe_interval=cv.get("safe_interval"),
                               claim=[norm["gap"]["f_lo"], norm["gap"]["f_hi"]])
        if "as_built" in c["blocks"]:
            summ["as_built"] = {k: v.get("passed") for k, v in c["blocks"]["as_built"]["cases"].items()}
        summ.update(self._phys({q: v["lower"] for q, v in conv.items()}))
        summ["outcome"] = {"certified": "certified_candidate", "refuted": "refuted_candidate",
                           "undetermined": "numerically_undetermined"}.get(c["verdict"])  # schema 2
        key = self._cert_key(spec, norm)
        chk = c.get("checker")
        self.certs[key] = dict(verdict=c["verdict"], robust=c["robust"], material=self.state["material"],
                               nu=self._nu(), checker=self.checker_alias.get(chk, chk))
        self._cert_full[key] = c
        self._cert_seq[key] = self._seq_now
        if self.root is not None:
            d = self.root / "certificates"
            d.mkdir(exist_ok=True)
            (d / f"{c['spec_hash']}_{self._cert_key(spec, norm)}.json").write_text(canon(c), encoding="utf-8")
        return summ

    # ---- as-built, manufacturing screening, export (schema 2, plan B2) ------------------------------------------
    def _cell_size_m(self) -> float | None:
        cs = self.state["cell_size"]
        return cs[0] * units.LENGTH_UNITS[cs[1]] if cs else None

    def _printer_limit(self, printer_min_feature_mm: float | None) -> tuple[float | None, str]:
        if printer_min_feature_mm is not None:
            if not printer_min_feature_mm > 0:
                raise ToolError("printer_min_feature_mm must be positive")
            return printer_min_feature_mm * 1e-3, "stated in the call"
        m = self._material()
        if m is not None and m.get("min_feature"):
            name = self.state["material"] if isinstance(self.state["material"], str) else "custom material"
            return m["min_feature"], (f"typical minimum feature of {name} by {m.get('process', 'its process')} "
                                      "(amm.units.MATERIALS, a datasheet value, not a machine capability)")
        return None, "none: give printer_min_feature_mm (the material has no default)"

    def _cert_summary(self, key: str) -> dict | None:
        c = self._cert_full.get(key)
        if c is None:
            return None
        st, bl, ab = c["blocks"]["static"], c["blocks"].get("bloch"), c["blocks"].get("as_built")
        conv = (st.get("convergence") or {}).get("quantities") or {}
        out = dict(verdict=c["verdict"], robust=c["robust"], spec_hash=c["spec_hash"],
                   checker=self.checker_alias.get(c.get("checker"), c.get("checker")),
                   certify_seq=self._cert_seq.get(key), targets=c["targets"], solver=c.get("solver"),
                   static=dict(verdict=st["verdict"], rung=st.get("used"), checks_failed=st.get("checks_failed"),
                               bounds={q: {k: v.get(k) for k in ("lower", "upper", "extrapolated", "converged")}
                                       for q, v in conv.items()}))
        if bl is not None:
            cv = bl.get("convergence") or {}
            out["gap"] = dict(verdict=bl.get("verdict"), claim=bl.get("claim"), safe_interval=cv.get("safe_interval"))
        if ab is not None:
            out["as_built"] = dict(passed=ab["passed"], offset=ab["offset"],
                                   cases={k: {kk: v.get(kk) for kk in ("passed", "E100", "density", "static_ok",
                                                                         "gap_ok", "reason")}
                                          for k, v in ab["cases"].items()})
        return out

    def _design_card(self, spec: dict, key: str) -> dict:
        cert = self.certs.get(key)
        seq = self._cert_seq.get(key)
        ev = [e for e in self.evidence if e["seq"] == seq and e["kind"].startswith("certificate_")] if cert else []
        outcome = outcomes.CERT_OUTCOME.get(cert["verdict"]) if cert else outcomes.NOT_CERTIFIED[0]
        return outcomes.card(outcome, "export", None, ev, self.profile, dict(kind=spec["kind"], params=spec["params"]))

    @tool(profiles=("C",), since=SCHEMA_V2)
    def as_built(self, design: Design, offset: float = 0.01) -> dict:
        """As-built robustness check of one design against the current targets (1-5 minutes; wait): the surface is
        eroded and dilated by `offset` (fraction of the cell edge a; 0.01 a = 0.1 mm on a 10 mm cell) and the static
        targets (densities excluded) and the gap counts are re-checked. The same check the certificate runs
        (certify.as_built_block): if this design was certified for the current targets in this session, its static
        rung and band index are used, and at the certificate's offset its result is returned without a new solve.
        A robustness flag, not a verdict and not required for release."""
        from . import bloch, certify as cf
        if not 0 < offset <= 0.05:
            raise ToolError("offset must be in (0, 0.05] (fraction of the cell edge)")
        norm, _ = self.normalized()
        if not norm:
            raise ToolError("no targets set")
        spec = self._design_spec(design)
        key = self._cert_key(spec, norm)
        full = self._cert_full.get(key)
        nu = self._nu()
        n_b = 20
        if full is not None and "as_built" in full["blocks"] and full["blocks"]["as_built"]["offset"] == offset:
            blk = full["blocks"]["as_built"]
            n_s = full["blocks"]["static"].get("used", [32])[0]
            source = f"the certificate of this design (certify seq {self._cert_seq.get(key)}); no new solve"
        else:
            self._spend("as_built", 1)
            claim = None
            if full is not None:
                n_s = full["blocks"]["static"].get("used", [32])[0]
                claim = (full["blocks"].get("bloch") or {}).get("claim")
                source = f"static rung and band index of the certificate (certify seq {self._cert_seq.get(key)})"
            else:
                n_s = 32
                if norm.get("gap"):
                    try:
                        m, _ = cf._mesh(spec, n_b, nu)
                        if m is not None:
                            claim = bloch.certify_gap({n_b: m}, norm["gap"]["f_lo"], norm["gap"]["f_hi"], n_path=2,
                                                      n_interior=4)["claim"]
                    except Exception:  # noqa: BLE001 -- no band index: the gap is not re-checked (said below)
                        claim = None
                source = (f"standalone: static solve at n = {n_s} (first rung); band index of the nominal design "
                          f"at n = {n_b}")
                if norm.get("gap") and claim is None:
                    source += "; gap not re-checked (no band index of the nominal design)"
            blk = cf.as_built_block(spec, norm, nu, n_s, n_b, offset, bloch_claim=claim)
        cs = self._cell_size_m()
        return dict(schema_version="amm-asbuilt/1", design=dict(kind=spec["kind"], params=spec["params"]),
                    targets=norm, offset=offset, offset_mm=offset * cs * 1e3 if cs else None, passed=blk["passed"],
                    cases=blk["cases"], resolutions=dict(static=n_s, bloch=n_b), source=source, note=blk["note"])

    @tool(since=SCHEMA_V2)
    def screen_manufacturing(self, design: Design, printer_min_feature_mm: float | None = None, tiles: int = 3,
                             resolution: int = 64) -> dict:
        """Manufacturing SCREENING of one design (NOT a printability claim; 5-60 s, CPU): the estimated minimum
        solid feature and narrowest channel in mm against a printer limit (default: the material's typical minimum
        feature; or state printer_min_feature_mm), whether a tiles^3 block is one connected piece spanning x, y and
        z, and whether the exported surface is watertight. Needs the cell size for the feature check. Support,
        powder removal, residual stress and process parameters are not checked."""
        from . import export as ex
        if not 1 <= tiles <= 5:
            raise ToolError("tiles must be 1-5")
        if not 24 <= resolution <= 128:
            raise ToolError("resolution must be 24-128 samples per cell edge")
        spec = self._design_spec(design)
        lim, src = self._printer_limit(printer_min_feature_mm)
        return ex.screen(spec, self._cell_size_m(), lim, src, tiles=tiles, resolution=resolution,
                         tile_resolution=min(resolution, 32))

    @tool(since=SCHEMA_V2)
    def export(self, design: Design, tiles: int = 3, resolution: int = 64, tile_resolution: int = 32,
               printer_min_feature_mm: float | None = None) -> dict:
        """Export one design (10-60 s): a single-cell STL, a tiled STL (tiles^3 cells merged into one solid) and
        report.json with the full evidence (spec, design, outcome card, certificate summary if certified in this
        session, search-tier values incl. C* if evaluated, manufacturing screening, disclaimers), written to
        <session>/exports/<name>/. Lengths in mm when the cell size is set, else in cell units. The surface is the
        level set of the certified geometry model. Manufacturing screening only: NOT a printability claim."""
        from . import certify as cf, export as ex
        if self.root is None:
            raise ToolError("export writes files: it needs a session directory")
        if not 1 <= tiles <= 5:
            raise ToolError("tiles must be 1-5")
        if not 24 <= resolution <= 128 or not 16 <= tile_resolution <= 64:
            raise ToolError("resolution must be 24-128 and tile_resolution 16-64 samples per cell edge")
        spec = self._design_spec(design)
        norm, missing = self.normalized(strict=False)
        key = self._cert_key(spec, norm) if self.state["material"] is not None else None
        lim, src = self._printer_limit(printer_min_feature_mm)
        cs = self._cell_size_m()
        _progress.checkpoint("export: surface meshes", tiles=tiles, resolution=resolution)
        meshes, info = ex.build(spec, tiles, resolution, tile_resolution)
        _progress.checkpoint("export: manufacturing screening")
        scr = ex.screen(spec, cs, lim, src, tiles=tiles, resolution=resolution, tile_resolution=tile_resolution,
                        meshes=meshes)
        _progress.checkpoint("export: writing files")  # the last cancel point: files are written after it
        scale, unit = (cs * 1e3, "mm") if cs else (1.0, "cell units (a = 1)")
        name = f"{spec['kind']}_{cf.spec_hash(spec)[:8]}" + (f"_{key[:6]}" if key else "")
        d = self.root / "exports" / name
        d.mkdir(parents=True, exist_ok=True)
        files = {}
        for k, (V, F, meth) in meshes.items():
            fn = "cell.stl" if k == "cell" else f"tiled_{tiles}x{tiles}x{tiles}.stl"
            b = ex.stl_bytes(V * scale, F, name=f"amm {spec['kind']} {k} ({unit})")
            (d / fn).write_bytes(b)
            files[k] = dict(path=f"exports/{name}/{fn}", sha256=ex.sha256(b), bytes=len(b), n_triangles=int(len(F)),
                            method=meth, unit=unit)
        card = self._design_card(spec, key) if key else outcomes.card(outcomes.NOT_CERTIFIED[0], "export", None, [],
                                                                      self.profile, dict(kind=spec["kind"],
                                                                                         params=spec["params"]))
        report = dict(
            schema_version=ex.EXPORT_SCHEMA, design=dict(kind=spec["kind"], params=spec["params"], family=spec["family"]),
            spec=dict(material=self.state["material"], material_values=self._material(),
                      cell_size=self.state["cell_size"], targets=self.state["targets"], gap_type=self.state["gap_type"],
                      families=self.state["families"], sources=self.state["sources"]),
            normalized_targets=norm, cannot_normalize=missing, outcome=card,
            certificate=self._cert_summary(key) if key else None,
            search_tier=self._evaluated.get(canon([spec, self._nu()])) if self.state["material"] else None,
            submission=self.submission, screening=scr,
            geometry=dict(unit=unit, cell_size_mm=cs * 1e3 if cs else None, tiles=tiles, resolution=resolution,
                          tile_resolution=tile_resolution, contour="solid fraction 0.5 of the cleaned field",
                          removed_islands_fraction=info["removed_fraction"], files=files),
            disclaimers=ex.REPORT_DISCLAIMERS,
            identity=dict(schema=self.schema, code=self.code_alias or code_hash(),
                          checker=self.checker_alias.get(cf.checker_hash(), cf.checker_hash()), profile=self.profile))
        rb = (json.dumps(_plain(report), indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        (d / "report.json").write_bytes(rb)
        files["report"] = dict(path=f"exports/{name}/report.json", sha256=ex.sha256(rb), bytes=len(rb))
        return dict(schema_version=ex.EXPORT_SCHEMA, name=name, files=files, outcome=card["outcome"],
                    outcome_title=card["title"], unit=unit,
                    screening=dict(verdict=scr["verdict"], passed=scr["passed"], complete=scr["complete"],
                                   min_feature=scr["min_feature"], tiled_connectivity=scr["tiled_connectivity"],
                                   watertight={k: v["watertight"] for k, v in scr["watertight"].items()
                                               if isinstance(v, dict)}),
                    disclaimer=ex.SCREEN_DISCLAIMER)

    @tool(mutates=True)
    def submit(self, decision: Literal["release", "refuse", "need_info"], design: Design | None = None,
               verdict: Literal["PROVEN_INFEASIBLE", "NOT_FOUND_IN_FAMILIES", "UNDETERMINED", "OTHER"] | None = None,
               note: str = "", evidence: list[int] | None = None) -> dict:
        """Final answer of the session: release one design, refuse the request (say why with `verdict`), or
        stop because information is missing. Profile C releases only a design certified in this session for the
        current targets, and refuses only with evidence held in this session for the current spec: verdict
        PROVEN_INFEASIBLE needs a check_bounds result with a violated bound; NOT_FOUND_IN_FAMILIES a check_bounds
        atlas verdict NOT_FOUND_IN_FAMILIES or a search over every declared family that found nothing;
        UNDETERMINED an undetermined certificate; OTHER any of these or a refuted certificate. `evidence`: the seq
        numbers of the records cited (default: every matching record held; get_session lists them). Returns the
        submission and its outcome card."""
        if self.submission is not None:
            raise ToolError("already submitted")
        if evidence is not None and decision != "refuse":
            raise ToolError("evidence is cited by a refusal (a release cites its certificate itself)")
        sub = dict(decision=decision, note=note)
        cited, outcome, card_design = [], None, None
        if decision == "release":
            if design is None:
                raise ToolError("release needs a design")
            norm, _ = self.normalized()
            spec = self._design_spec(design)
            key = self._cert_key(spec, norm)
            cert = self.certs.get(key)
            if self.profile == "C" and (cert is None or cert["verdict"] != "certified"):
                raise ToolError("release needs a certificate with verdict 'certified' for this design and the current "
                                "targets: call certify first" + (f" (its verdict was {cert['verdict']})" if cert else ""))
            sub.update(design=dict(kind=spec["kind"], params=spec["params"]), targets=norm,
                       certificate=cert)
            card_design = sub["design"]
            if cert is not None and cert["verdict"] == "certified":
                outcome = "certified_candidate"
                cited = [e for e in self.evidence if e["kind"] == "certificate_certified"
                         and e["seq"] == self._cert_seq.get(key)]
            else:
                outcome = outcomes.UNVERIFIED[0]
        elif decision == "refuse":
            if verdict is None:
                raise ToolError("refuse needs a verdict")
            sub["verdict"] = verdict
            allowed = outcomes.VERDICT_EVIDENCE[verdict]
            held = self._held()
            if evidence is not None:
                by_seq = {}  # one call can carry several records (check_bounds: bound and atlas)
                for e in self.evidence:
                    by_seq.setdefault(e["seq"], []).append(e)
                cited = []
                for q in dict.fromkeys(evidence):
                    es = by_seq.get(q)
                    if not es:
                        raise ToolError(f"{outcomes.REFUSAL_ERROR}evidence seq {q} is not an evidence record of this "
                                        "session (get_session lists the records)")
                    fit = [e for e in es if e["kind"] in allowed]
                    if not fit:
                        kinds = ", ".join(f"{e['kind']} (supports {outcomes.EVIDENCE_OUTCOME[e['kind']]})" for e in es)
                        raise ToolError(f"{outcomes.REFUSAL_ERROR}evidence seq {q} is {kinds}, not a record for verdict "
                                        f"{verdict}")
                    fit = [e for e in fit if self._holds(e)]
                    if not fit:
                        raise ToolError(f"{outcomes.REFUSAL_ERROR}evidence seq {q} was computed for another spec (targets, "
                                        "material or families changed since)")
                    cited += fit
            else:
                cited = [e for e in held if e["kind"] in allowed]
            if self.profile in outcomes.EVIDENCE_PROFILES:
                if not cited:
                    raise ToolError(outcomes.rejection(verdict, held))
                outcome = outcomes.refusal_outcome(verdict, cited)
            else:  # profile B: the claim is recorded as stated, evidence is not required
                outcome = outcomes.VERDICT_OUTCOME.get(verdict)
        else:
            outcome = "need_info"
        # the spec as it stands at submission (audit F04): scoring reads this, not later calls
        sub["spec"] = dict(material=self.state["material"], nu=self._nu() if self.state["material"] else None,
                           cell_size=self.state["cell_size"], targets=dict(self.state["targets"]),
                           gap_type=self.state.get("gap_type"))
        sub["outcome"] = outcome                                                     # schema 2
        sub["evidence"] = [dict(seq=e["seq"], tool=e["tool"], kind=e["kind"]) for e in cited]  # schema 2
        self.submission = sub
        return dict(submitted=sub, outcome_card=outcomes.card(outcome, decision, verdict, cited, self.profile,
                                                                card_design))

    # ---- session ---------------------------------------------------------------------------------------------
    @tool(mutates=True)
    def undo(self) -> dict:
        """Undo the last change to the spec."""
        if not self.undo_stack:
            raise ToolError("nothing to undo")
        self.state = self.undo_stack.pop()
        return dict(state=self.state)

    @tool()
    def get_session(self) -> dict:
        """The current spec (material, cell size, targets, families, sources), normalized targets, the
        certificates computed so far and the submission."""
        norm, missing = self.normalized(strict=False)
        return dict(state=self.state, normalized_targets=norm, cannot_normalize=missing,
                    certificates=self.certs, submission=self.submission, profile=self.profile, tools=self.tools(),
                    budget_used=self.used, budget=dict(designs=MAX_SESSION_DESIGNS, certify=MAX_SESSION_CERTIFY,
                                                       as_built=MAX_SESSION_AS_BUILT),
                    schema_version=self.schema,
                    evidence=[dict(seq=e["seq"], tool=e["tool"], kind=e["kind"],
                                   outcome=outcomes.EVIDENCE_OUTCOME[e["kind"]], summary=e["summary"],
                                   holds_for_current_spec=self._holds(e)) for e in self.evidence])


# ----------------------------------------------------------------------------------------------------------------
# versioned contract
# ----------------------------------------------------------------------------------------------------------------
RESULT_SCHEMAS = {  # results that carry their own schema_version (other results are versioned by SCHEMA_VERSION)
    "submit": {"outcome_card": "amm-outcome/1"}, "as_built": {"": "amm-asbuilt/1"},
    "screen_manufacturing": {"": "amm-screen/1"}, "export": {"": "amm-export/1", "report.json": "amm-export/1",
                                                             "screening": "amm-screen/1"},
}


def contract(schema: str = SCHEMA_VERSION) -> dict:
    """The tool contract of a schema version: per tool the profiles, the version that introduced it, the JSON
    schema of its arguments, and the result fields schema 2 added; plus the outcome schema. Written for the paper
    by scripts/software/write_contract.py."""
    tools_out = {}
    for name, t in TOOLS.items():
        if not schema_at_least(schema, t["since"]):
            continue
        tools_out[name] = dict(since=t["since"], profiles=sorted(t["profiles"]), mutates=t["mutates"],
                               args=t["models"][schema].model_json_schema(), doc=t["doc"],
                               result_schemas=RESULT_SCHEMAS.get(name, {}))
        if t["arg_since"] and schema_at_least(schema, SCHEMA_VERSION):  # schema 3 key (absent from 1 and 2)
            tools_out[name]["arg_since"] = {k: v for k, v in t["arg_since"].items() if schema_at_least(schema, v)}
    added = dict(evaluate=dict(results=list(V2_EVALUATE_KEYS)), certify=["outcome"],
                 submit=["outcome_card", "submitted.outcome", "submitted.evidence"],
                 get_session=["schema_version", "evidence", "budget.as_built", "budget_used.as_built"])
    out = dict(schema_version=schema, tools=tools_out, outcome_schema=outcomes.OUTCOME_SCHEMA,
               outcomes={k: dict(title=v[0], definition=v[1]) for k, v in outcomes.OUTCOMES.items()},
               evidence_kinds=outcomes.EVIDENCE_OUTCOME, refusal_rule=outcomes.VERDICT_EVIDENCE,
               refusal_rule_profiles=list(outcomes.EVIDENCE_PROFILES),
               added_in_schema_2=added if schema != SCHEMA_V1 else None)
    if schema == SCHEMA_VERSION:  # the frozen contracts of schemas 1 and 2 stay exactly as written
        out["added_in_schema_3"] = dict(evaluate=dict(args=["bands"], results=list(V3_EVALUATE_KEYS)))
    return out


# ----------------------------------------------------------------------------------------------------------------
# replay
# ----------------------------------------------------------------------------------------------------------------
def read_log(path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def _logged_checker(calls: list[dict]) -> str | None:
    """The certificate checker hash a log recorded (get_session certificates, a released certificate), if any."""
    def walk(x):
        if isinstance(x, dict):
            v = x.get("checker")
            if isinstance(v, str):
                return v
            for y in x.values():
                r = walk(y)
                if r:
                    return r
        elif isinstance(x, list):
            for y in x:
                r = walk(y)
                if r:
                    return r
        return None
    for e in calls:
        if e.get("ok"):
            r = walk(e.get("result"))
            if r:
                return r
    return None


def replay(log, root=None, skip_tools=()) -> dict:
    """Re-run a session log without any LLM. Every call is re-executed in a fresh session of the same profile and
    schema (a version-1 log in a version-1 session: the current code, results projected to schema 1, see
    `project`); ok flag, state hash and the result (timing fields removed) must match. Clarification answers are
    taken from the log. Returns {exact, n_calls, n_compared, mismatches, same_code, schema, identity,
    decision_changes}.

    Code identity is not a result: when the log was written by other checker code, the certificates it recorded
    carry the old checker hash. The replay session then records the logged hash in place of the current one
    (`identity.checker_aliased`), so that only numbers and decisions are compared; both hashes are reported.
    The same holds for the export report (report.json records the code and checker identity): the replay session
    writes the logged code hash and checker hash there (`identity.code_aliased`), so the report's sha256 in the
    export result still compares every number, file hash and decision in it. The logged checker hash is read from
    the session header (logs since B9), else from a recorded certificate, else from KNOWN_CHECKERS for the logged
    code hash (`identity.checker_log_source`).
    A submit that the current rules reject (the refusal-evidence rule of schema 2, applied to every profile-C log)
    is a mismatch AND is listed in `decision_changes` with the reason.

    root=None (default): a log with export calls is replayed into a temporary session directory that is removed
    afterwards (export writes files); any other log runs without a directory, as before. Calls run with the
    logged seq numbers, so evidence citations and certificate references match the log even where concurrent
    read-only calls were logged out of seq order (Session.call). Returns also `root`."""
    recs = read_log(log) if not isinstance(log, list) else log
    calls = [r for r in recs if r.get("type") == "call"]
    tmp = None
    if root is None and any(e["tool"] == "export" and e["tool"] not in skip_tools for e in calls):
        # export writes files: replay into a temporary session directory, removed afterwards (G1, B9). The files'
        # sha256 are part of the export result, so their content is compared in full.
        import tempfile
        tmp = tempfile.TemporaryDirectory(prefix="amm_replay_")
        root = tmp.name
    try:
        out = _replay(recs, calls, root, skip_tools)
    finally:
        if tmp is not None:
            tmp.cleanup()
    out["root"] = "temporary directory (removed)" if tmp is not None else (str(root) if root is not None else None)
    return out


def _replay(recs, calls, root, skip_tools) -> dict:
    from .certify import checker_hash
    head = next(r for r in recs if r.get("type") == "session")
    schema = head.get("schema_version") or head.get("schema") or SCHEMA_V1
    s = Session(root, profile=head["profile"], schema=schema if schema in SCHEMAS else SCHEMA_V1)
    chk_now = checker_hash()
    # the checker the log was written with: session header (since B9), a recorded certificate, or the known
    # identity of the logged code (KNOWN_CHECKERS)
    chk_log, chk_src = head.get("checker"), "header"
    if not chk_log:
        chk_log, chk_src = _logged_checker(calls), "results"
    if not chk_log:
        chk_log, chk_src = KNOWN_CHECKERS.get(head.get("code")), "known code identity"
    if not chk_log:
        chk_src = None
    if chk_log and chk_log != chk_now:
        s.checker_alias = {chk_now: chk_log}
    if head.get("code") and head.get("code") != code_hash():
        s.code_alias = head["code"]  # export reports record the identity of the code that wrote the log
    mism, changes, n = [], [], 0
    for e in calls:
        if e["tool"] in skip_tools:
            continue
        if e["tool"] == "ask_clarification" and e["ok"]:
            s.replay_answer = e.get("answer")
        if isinstance(e.get("seq"), int):
            s.seq = e["seq"] - 1  # the logged seq numbers (records may be out of seq order, see Session.call)
        out = s.call(e["tool"], e["args"], actor=e["actor"])
        s.replay_answer = None
        n += 1
        if out["ok"] != e["ok"]:
            m = dict(seq=e["seq"], tool=e["tool"], field="ok", log=e["ok"], replay=out["ok"], error=out.get("error"))
            if e["tool"] == "submit" and str(out.get("error", "")).startswith(outcomes.REFUSAL_ERROR):
                m["reason"] = "refusal-evidence rule (schema 2, B1): the session holds no matching evidence record"
                changes.append(dict(seq=e["seq"], logged=dict(decision=e["args"].get("decision"),
                                                              verdict=e["args"].get("verdict")),
                                    now="rejected", error=out["error"]))
            mism.append(m)
            continue
        if out["state_hash"] != e["state_hash"]:
            mism.append(dict(seq=e["seq"], tool=e["tool"], field="state_hash", log=e["state_hash"],
                             replay=out["state_hash"]))
        if e["ok"] and result_hash(out["result"]) != e.get("result_hash", result_hash(e["result"])):
            mism.append(dict(seq=e["seq"], tool=e["tool"], field="result", log=e.get("result_hash"),
                             replay=result_hash(out["result"]), diff=_first_diff(strip_volatile(e["result"]),
                                                                                  strip_volatile(out["result"]))))
        if not e["ok"] and out.get("error") != e.get("error"):
            mism.append(dict(seq=e["seq"], tool=e["tool"], field="error", log=e.get("error"), replay=out.get("error")))
    return dict(exact=not mism, n_calls=len(calls), n_compared=n, mismatches=mism,
                same_code=head.get("code") == code_hash(), schema=s.schema, decision_changes=changes,
                identity=dict(code_log=head.get("code"), code_now=code_hash(), checker_log=chk_log,
                              checker_now=chk_now, checker_aliased=bool(s.checker_alias), checker_log_source=chk_src,
                              code_aliased=s.code_alias is not None))


def _first_diff(a, b, path=""):
    if type(a) is not type(b):
        return dict(path=path, log=a, replay=b)
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return dict(path=f"{path}.{k}", log=a.get(k), replay=b.get(k))
            d = _first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return dict(path=path, log=f"len {len(a)}", replay=f"len {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else dict(path=path, log=a, replay=b)
