"""Live mode: the GUI over the real amm.tools.Session (imported here only; mock mode never imports this module).

  * Every solving call (evaluate, search, certify, as_built) runs on the one worker thread of the JobQueue and
    holds the shared solver lock while it runs (`GpuLock`, the protocol of scripts/ops/gpulock_run.py and
    scripts/bench/e4.py: C:/AI/AgenticMetamaterials_workspaces/gpu.lock created exclusively with {pid, who, t};
    a lock left by a dead process is removed). The lock is taken per job and released when the job ends, so the
    GUI never holds the GPU while it is idle and other runners (benchmarks, tests) interleave with it.
    export and screen_manufacturing are CPU-only (geometry, marching cubes, morphology): queued, no lock.
  * Progress and cancellation through amm's own hook (amm.progress, B9 2026-11-08; until then this module wrapped
    amm functions at run time): every job calls `Session.call(..., progress=, cancel=)` with the job's cancel
    event. The solvers report at their natural boundaries (static solves and rungs, Bloch k-points, edge solves,
    search batches), published as "progress" events on the SSE stream; a cancelled job stops at the next boundary
    with amm.progress.Cancelled (a BaseException, so amm's fail-closed handlers cannot turn it into a verdict),
    and amm rolls the call back (seq and budget restored, nothing logged). Here it becomes `JobCancelled`.
  * Band data for the GUI: live evaluate calls ask for the bands (`evaluate(bands=True)`, schema amm-tools/3), so
    the band diagram shows the bands of the logged evaluate call, read from its record, with no extra solve.
  * Read-only tools (amm.tools.CONCURRENT_READ: get_session, check_bounds, atlas_suggest, list_families) answer
    while a solve runs (amm answers them from the session as it was when the solve started); spec changes still
    answer "session busy" instead of blocking the HTTP thread.
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from . import backend as bk, mockdata
from .backend import JobCancelled

ROOT = Path(__file__).resolve().parents[1]
WS_ROOT = ROOT.parent / "AgenticMetamaterials_workspaces"
LOCK_PATH = Path(os.environ.get("AMM_GPU_LOCK", str(WS_ROOT / "gpu.lock")))
GPU_TOOLS = ("evaluate", "search", "certify", "as_built")


# ================================================================================================================
# shared solver lock
# ================================================================================================================
def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                             timeout=30).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001 -- unknown: treat as alive (never steal a live lock)
        return True


class GpuLock:
    """The shared solver lock, same file protocol as scripts/ops/gpulock_run.GpuLock, plus: the wait can be
    cancelled, and release removes the file only if this process wrote it."""

    def __init__(self, who: str, path: Path | None = None, poll: float = 2.0):
        self.path, self.who, self.poll = Path(path or LOCK_PATH), who, poll
        self.held = False
        self._mx = threading.Lock()

    def owner(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def acquire(self, cancel: threading.Event | None = None, on_wait=None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        t0, last = time.time(), 0.0
        while True:
            if cancel is not None and cancel.is_set():
                raise JobCancelled("cancelled while waiting for the solver lock")
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps(dict(pid=os.getpid(), who=self.who, t=time.time())).encode())
                os.close(fd)
                with self._mx:
                    self.held = True
                return
            except FileExistsError:
                info = self.owner()
                if info.get("pid") and int(info["pid"]) != os.getpid() and not _pid_alive(int(info["pid"])):
                    self.path.unlink(missing_ok=True)  # left by a dead process
                    continue
                if on_wait is not None and time.time() - last > 5:
                    last = time.time()
                    on_wait(dict(info, waited_s=round(time.time() - t0, 1)))
                (cancel.wait(self.poll) if cancel is not None else time.sleep(self.poll))

    def release(self) -> None:
        with self._mx:
            if not self.held:
                return
            self.held = False
        if self.owner().get("pid") == os.getpid():
            self.path.unlink(missing_ok=True)

    @contextlib.contextmanager
    def hold(self, cancel=None, on_wait=None):
        self.acquire(cancel, on_wait)
        try:
            yield self
        finally:
            self.release()


# ================================================================================================================
# progress of a running job (amm.progress callback)
# ================================================================================================================
# amm checkpoint stage -> the counter shown in the jobs bar
STAGE_COUNTS = {"certificate: static solve": "static solves", "certificate: Bloch inertia counts": "inertia counts",
                "certificate: gap-edge solve (Lanczos)": "edge solves", "certificate: gap-edge screening": "edge screens",
                "certificate: adversarial k search (GPU)": "adversarial k rounds", "as-built check": "as-built cases",
                "search tier: design": "search-tier designs", "search: batch": "search batches"}


class JobCtx:
    """The job a progress report belongs to; `on_progress` is the amm.progress callback of its call."""

    def __init__(self, queue: bk.JobQueue, job: dict):
        self.queue, self.job = queue, job
        self.cancel = queue.cancel_event(job["id"])
        self.counts: dict[str, int] = {}
        self.t0 = time.time()
        self.stage = ""

    def _publish(self, last: str, force: bool = False, **extra):
        self.queue.progress(self.job["id"], dict(stage=self.stage, last=last, counts=dict(self.counts),
                                                 elapsed_s=round(time.time() - self.t0, 1), **extra), force=force)

    def on_progress(self, info: dict):
        stage = info.get("stage", "")
        what = STAGE_COUNTS.get(stage)
        detail = ", ".join(f"{k} {v}" for k, v in info.items() if k != "stage")
        if what is None:  # a block or rung boundary: a new stage
            self.stage = stage + (f" ({detail})" if detail else "")
            self._publish(self.stage, force=True)
            return
        self.counts[what] = self.counts.get(what, 0) + 1
        self._publish(stage + (f" ({detail})" if detail else ""))

    def say(self, stage: str, **extra):
        self.stage = stage
        self._publish(stage, force=True, **extra)


# ================================================================================================================
# live backend
# ================================================================================================================
class LiveBackend(bk.Backend):
    """amm.tools.Session behind the Backend interface. Spec tools, check_bounds and atlas_suggest run at once (CPU,
    fast); evaluate, search, certify, as_built, export and screen_manufacturing run on the worker queue."""
    mode = "live"

    def __init__(self, root: Path, profile: str = "C", lock_path: Path | None = None, who: str | None = None):
        from amm import progress as amm_progress, tools as amm_tools  # noqa: PLC0415 -- live mode only
        self._amm, self._amm_progress = amm_tools, amm_progress
        self.lock = GpuLock(who or f"amm-gui-live pid {os.getpid()}", lock_path)
        super().__init__(root)
        self.new_session(profile)

    # ---- session ------------------------------------------------------------------------------------------------
    def new_session(self, profile: str = "C") -> dict:
        if self.queue.current is not None:
            raise ValueError("a solver job is running: cancel it or wait before starting a new session")
        root = self.root_dir / f"live-{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(2).hex()}"
        self.session = _LiveAdapter(self._amm.Session(root, profile=profile))
        self.session_meta = dict(kind="new", profile=profile, code=self._amm.code_hash())
        self.bus.publish(dict(type="session", seq=0, reset=True))
        return self.summary()

    def load_recorded(self, sid: str) -> dict:
        raise ValueError("live mode starts new sessions; replay a recorded log with amm.tools.replay")

    def _direct(self, name, args, actor):
        s = self.session._s
        if name in self._amm.CONCURRENT_READ:  # answered at once, also while a solve runs (amm.tools.Session.call)
            return s.call(name, args, actor)
        if not s._lock.acquire(timeout=0.5):
            cur = self.queue.jobs.get(self.queue.current or "", {})
            return dict(ok=False, error=f"session busy: {cur.get('tool', 'a solver call')} is running on the worker "
                        "(spec changes would not apply to it); wait for it or cancel it")
        try:
            return s.call(name, args, actor)
        finally:
            s._lock.release()

    # ---- queued calls -------------------------------------------------------------------------------------------
    def cancellable(self, job: dict) -> bool:
        return job["tool"] in GPU_TOOLS

    def _run_heavy(self, job):
        s = self.session._s
        ctx = JobCtx(self.queue, job)
        gpu = job["tool"] in GPU_TOOLS
        args = dict(job["args"])
        if job["tool"] == "evaluate" and self._amm.schema_at_least(s.schema, "amm-tools/3"):
            args.setdefault("bands", True)  # the band diagram of this call (logged with the call)
        if gpu:
            ctx.say("waiting for the shared solver lock")
            lock_cm = self.lock.hold(ctx.cancel, on_wait=lambda info: ctx.say(
                f"waiting for the shared solver lock (held by {info.get('who', '?')}, pid {info.get('pid')}; "
                f"{info['waited_s']:g} s)"))
        else:
            lock_cm = contextlib.nullcontext()
        with lock_cm:
            ctx.say(f"running {job['tool']}" + (" (solver lock held)" if gpu else " (CPU)"))
            try:
                # amm rolls a cancelled call back itself (no record, seq and budget restored)
                return s.call(job["tool"], args, job["actor"], progress=ctx.on_progress,
                              cancel=ctx.cancel if self.cancellable(job) else None)
            except self._amm_progress.Cancelled as ex:
                raise JobCancelled(str(ex)) from ex

    def shutdown(self):
        cur = self.queue.current
        if cur:
            self.queue.cancel(cur)
            self.queue.wait(cur, 30)
        self.lock.release()

    # ---- views ----------------------------------------------------------------------------------------------------
    def design_spec(self, design: dict) -> dict:
        try:
            return self.session._s._design_spec(self._amm.Design(**design))
        except Exception as ex:  # noqa: BLE001 -- pydantic or ToolError: a message for the GUI
            raise ValueError(str(ex))

    def _details_search(self, spec):
        s = self.session._s
        m = s._material()
        if m is None:
            return dict(available=False, reason="set a material first (its Poisson ratio enters every solve)")
        nu = float(m["nu"])
        key = bk.canon([spec, nu])
        ev = s._evaluated.get(key)
        if ev is not None:
            seq = self._last_seq_of("evaluate", spec)
            d = ev.get("derived") or {}
            row = dict(density=ev.get("density"), valid=ev.get("valid"), C11=d.get("C11"), C12=d.get("C12"),
                       C44=d.get("C44"))
            b = self._last_bands(spec, ev)
            if b is not None:
                row.update(bands=b["f_star"], bloch_valid=True)
            v = bk._search_view(row, source=dict(kind="evaluate", nu=nu, seq=seq, note=(
                f"evaluate call #{seq} of this session (search tier, not certified)" if seq else
                "evaluate call of this session (search tier, not certified)")))
            if ev.get("C") is not None:
                v["tensor"] = dict(C=ev["C"], C_MPa=ev.get("C_MPa"), derived=d, kind="full",
                                   source=f"evaluate #{seq}: full homogenized tensor (6x6 Voigt), search tier")
            v["gaps_tool"] = ev.get("gaps")
            return v
        hit = mockdata.nearest_atlas_row(spec["kind"], spec["params"], nu)
        if hit is None:
            return dict(available=False, reason=f"not evaluated yet (no atlas at nu_s = {nu:g}): press Evaluate")
        v = bk._search_view(hit[0], source=dict(kind="atlas", nu=nu, atlas_params=hit[0]["spec"]["params"],
                                                param_distance=hit[1], note=(
            "not evaluated yet: nearest precomputed atlas cell (search tier); press Evaluate for this design")))
        v["tensor"] = bk.cubic_tensor_view(hit[0], "atlas cell: cubic reconstruction from C11, C12, C44 "
                                                   "(atlas rows store the cubic constants only)")
        return v

    def _last_bands(self, spec: dict, ev: dict) -> dict | None:
        """The band structure of the last evaluate call of this session that returned it for this design, with the
        same search-tier row as `ev` (the session's stored row: same material and Poisson ratio)."""
        want = bk.canon(dict(kind=spec["kind"], params=spec["params"]))
        for r in reversed(self.records()):
            if r.get("type") == "call" and r.get("tool") == "evaluate" and r.get("ok"):
                for x in (r.get("result") or {}).get("results", []):
                    if (bk.canon(x.get("design")) == want and x.get("bands") and x.get("gaps") == ev.get("gaps")
                            and x.get("density") == ev.get("density")):
                        return x["bands"]
        return None

    def _last_seq_of(self, tool: str, spec: dict) -> int | None:
        want = bk.canon(dict(kind=spec["kind"], params=spec["params"]))
        for r in reversed(self.records()):
            if r.get("type") == "call" and r.get("tool") == tool and r.get("ok"):
                for x in (r.get("result") or {}).get("results", []):
                    if bk.canon(x.get("design")) == want:
                        return r["seq"]
        return None

    def export(self, design=None, tiles=3, n=40):
        raise ValueError("live mode exports through the amm export tool (POST /api/tools/export), which writes the "
                         "certified-geometry STL files and report.json")


class _LiveAdapter:
    """The attributes of amm.tools.Session that the backend reads, plus `records` from its log file."""

    def __init__(self, s):
        self._s = s

    def __getattr__(self, k):
        return getattr(self._s, k)

    @property
    def records(self):
        p = self._s.log_path
        return mockdata.read_log(p) if p is not None and p.exists() else []

    def cert_key(self, spec, targets):
        return self._s._cert_key(spec, targets)

    def _material(self):
        return self._s._material()

    def _holds(self, e):
        return self._s._holds(e)

