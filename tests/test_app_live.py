"""GUI backend in LIVE mode (app/live.py): the real amm.tools.Session behind the GUI, the shared solver lock, progress
and cancellation through amm's own hook (amm.progress, B9), the evaluate bands, export and screening downloads.

The lock tests run anywhere (CPU, a temporary lock file). The end-to-end test needs a CUDA device and the shared solver
lock C:/AI/AgenticMetamaterials_workspaces/gpu.lock: it is skipped without a GPU, and skipped when another runner holds
the lock; under scripts/ops/gpulock_run.py (the lock held by an ancestor of this process) it runs with a private lock
file, since the GPU is already ours. About 20 s of GPU time.

Run: python -m pytest -q tests/test_app_live.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import backend as bk, live  # noqa: E402  (app.live imports amm only inside LiveBackend)

pytestmark = [pytest.mark.repo]


def _cuda() -> bool:
    try:
        import amm  # noqa: F401  (amm before torch: MKL's OpenMP runtime first)
        import torch
        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


def _lock_mode() -> str:
    """free: nobody holds the solver lock; ours: an ancestor of this process holds it (gpulock_run); busy: another
    live process holds it."""
    p = live.LOCK_PATH
    if not p.exists():
        return "free"
    try:
        pid = int(json.loads(p.read_text(encoding="utf-8")).get("pid") or 0)
    except Exception:  # noqa: BLE001
        return "busy"
    import psutil
    if pid == os.getpid() or pid in {q.pid for q in psutil.Process().parents()}:
        return "ours"
    return "free" if pid and not psutil.pid_exists(pid) else "busy"


# ---- the shared solver lock (CPU only, temporary lock file) -------------------------------------------------------
def test_gpu_lock_protocol(tmp_path):
    path = tmp_path / "gpu.lock"
    a = live.GpuLock("test A", path, poll=0.05)
    a.acquire()
    info = json.loads(path.read_text(encoding="utf-8"))
    assert info["pid"] == os.getpid() and info["who"] == "test A" and a.held
    # a second holder waits; its wait can be cancelled
    b = live.GpuLock("test B", path, poll=0.05)
    cancel = threading.Event()
    waits = []
    th = threading.Timer(0.3, cancel.set)
    th.start()
    with pytest.raises(bk.JobCancelled):
        b.acquire(cancel, on_wait=waits.append)
    assert waits and waits[0]["who"] == "test A" and not b.held
    # release removes only our own file
    path.write_text(json.dumps(dict(pid=999999, who="someone else", t=0)), encoding="utf-8")
    a.release()
    assert path.exists() and not a.held
    # a lock left by a dead process is removed (same rule as scripts/ops/gpulock_run.py)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    path.write_text(json.dumps(dict(pid=dead.pid, who="dead runner", t=0)), encoding="utf-8")
    with b.hold():
        assert json.loads(path.read_text(encoding="utf-8"))["who"] == "test B"
    assert not path.exists()


def test_progress_hook_and_cancel(tmp_path):
    """B9: the GUI uses amm's own progress/cancel hook; nothing in amm is wrapped any more. Inside a job, amm's
    checkpoints report to the job's progress, and a cancelled job stops with amm.progress.Cancelled, a
    BaseException (amm's fail-closed `except Exception` cannot swallow it), which the live backend turns into
    JobCancelled."""
    from amm import certify, homog, progress
    assert not hasattr(homog.homogenize, "_amm_gui_hook") and not hasattr(live, "install_hooks")
    q = bk.JobQueue(lambda job: None, bk.EventBus())
    job = q.submit("certify", {}, "test")
    ctx = live.JobCtx(q, job)
    spec = dict(family="struts", kind="sc", params=dict(r=0.12, R=0.0))
    with progress.hooks(progress=ctx.on_progress, cancel=ctx.cancel):
        certify._static_row(spec, 8, 0.3, {}, {})
    assert q.jobs[job["id"]]["progress"]["counts"] == {"static solves": 1}
    q._cancel[job["id"]].set()
    with progress.hooks(progress=ctx.on_progress, cancel=ctx.cancel), pytest.raises(progress.Cancelled):
        certify._static_row(spec, 8, 0.3, {}, {})
    assert not issubclass(progress.Cancelled, Exception) and not issubclass(bk.JobCancelled, Exception)


# ---- live backend end to end (GPU, under the shared solver lock) ---------------------------------------------------
@pytest.mark.gpu
@pytest.mark.slow
def test_live_backend_end_to_end(tmp_path):
    if not _cuda():
        pytest.skip("no CUDA device")
    mode = _lock_mode()
    if mode == "busy":
        pytest.skip("the shared solver lock is held by another runner")
    lock_path = tmp_path / "private.lock" if mode == "ours" else None  # under gpulock_run the GPU is already ours
    be = live.LiveBackend(tmp_path / "sessions", lock_path=lock_path)
    ev = []
    be.bus.listeners.append(ev.append)
    c = be.call
    assert c("set_material", dict(name="316L"))["ok"]
    assert c("set_constraints", dict(cell_size=5, cell_size_unit="mm"))["ok"]
    assert c("set_target", dict(density_max=0.3, E100_min=dict(value=5, unit="GPa")))["ok"]
    assert c("check_bounds", {})["result"]["verdict"] in ("FEASIBLE", "BORDERLINE")
    d = dict(kind="sc", params=dict(r=0.13087, R=0.210909))
    # evaluate: on the worker, under the lock; full C* and the bands of THIS call in the result panels
    j = c("evaluate", dict(designs=[d]), wait=True, timeout=600)["job"]
    assert j["status"] == "done", j
    row = j["output"]["result"]["results"][0]
    assert np.asarray(row["C"]).shape == (6, 6) and row["derived"]["E100"] > 0
    assert j["args"].get("bands") is None and np.asarray(row["bands"]["f_star"]).ndim == 2  # B9: bands=True added
    det = be.details(d)
    assert det["search"]["source"]["kind"] == "evaluate" and det["search"]["bands"]
    assert det["search"]["tensor"]["kind"] == "full"
    assert not be.lock.held and not be.lock.path.exists()
    # a running certify is cancelled at the next solver checkpoint and rolled back (nothing logged)
    seq, used = be.session._s.seq, dict(be.session._s.used)
    j = c("certify", dict(design=d))["job"]
    for _ in range(600):
        p = be.queue.jobs[j["id"]].get("progress") or {}
        if (p.get("counts") or {}).get("static solves", 0) >= 2:
            break
        time.sleep(0.1)
    # B9 (G4): read-only tools answer while the certificate runs, from the session as it was before it
    t0 = time.time()
    gs = c("get_session", {})
    assert gs["ok"] and gs["result"]["budget_used"] == used and time.time() - t0 < 5
    assert c("check_bounds", {})["ok"]
    assert c("set_target", dict(density_max=0.3))["error"].startswith("session busy")
    assert be.queue.cancel(j["id"])
    done = be.queue.wait(j["id"], 300)
    assert done["status"] == "cancelled", done
    assert be.session._s.seq == seq + 3 and be.session._s.used == used  # certify's number left as a gap
    assert not be.lock.held and not be.lock.path.exists()
    assert any(e["type"] == "progress" for e in ev)
    # B2: screening and export through the amm tools; files downloadable
    j = c("screen_manufacturing", dict(design=d, tiles=2, resolution=32), wait=True, timeout=600)["job"]
    assert j["status"] == "done" and j["output"]["result"]["schema_version"] == "amm-screen/1"
    j = c("export", dict(design=d, tiles=2, resolution=32, tile_resolution=16), wait=True, timeout=600)["job"]
    assert j["status"] == "done", j
    s = be.summary()
    ex = s["exports"][0]
    assert ex["tool"] == "export" and set(ex["files"]) == {"cell", "tiled", "report"}
    stl = be.session_file(ex["files"]["cell"]["path"]).read_bytes()
    assert len(stl) == 84 + 50 * int.from_bytes(stl[80:84], "little")
    data, name = be.export_zip(ex["result"]["name"])
    assert data[:2] == b"PK" and name.endswith(".zip")
    with pytest.raises(KeyError):
        be.session_file("../session.jsonl")
    assert s["outcome"]["schema"] == "amm-outcome/1"
    # the GUI session replays exactly (the cancelled call left no trace)
    from amm import tools
    lk = live.GpuLock("test_app_live replay", lock_path) if lock_path else live.GpuLock("test_app_live replay")
    with lk.hold():
        rep = tools.replay(be.session._s.log_path, root=tempfile.mkdtemp())
    assert rep["exact"], rep["mismatches"][:3]
    be.shutdown()
    assert not be.lock.held
