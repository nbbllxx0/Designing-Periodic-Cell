"""Process-level numerical runtime: MKL threads, MKL reproducibility mode, and the MKL-before-torch ordering.

Why the order matters. pypardiso (MKL) and torch both ship Intel's OpenMP runtime libiomp5md.dll. If torch's copy
initializes first, MKL later aborts with "OMP: Error #15". If MKL initializes first, one runtime is initialized
and both libraries share it. Importing pypardiso is not enough: MKL starts its OpenMP runtime on the first solve,
so the initialization is a 1x1 PARDISO solve (`ensure_mkl`).

Ordering guarantee (B3, 2026-11-07). Until then `import amm` ran that solve at import. Now nothing is solved at
import; `import amm` only sets the environment defaults below and installs `_TorchGuard`, a `sys.meta_path` finder
that sees every later import statement before any finder loads a module. The first time `torch` (or any `torch.*`
module, also when imported by botorch or gpytorch) is about to be imported, the guard runs `ensure_mkl()` and only
then lets the normal import machinery load torch. So, in a process that imports `amm` before torch, MKL's OpenMP
runtime is initialized before torch's DLLs load, exactly as before; a process that never imports torch initializes
MKL at its first PARDISO use (`amm.pardiso.Pardiso` calls `ensure_mkl()` before creating a solver, which keeps the
same sequence of MKL calls as the old import-time warm-up: the 1x1 solve, then the real solves). If torch was
loaded first, the order cannot be fixed any more: the old code then aborted the process at `import amm`
("OMP: Error #15", checked 2026-11-07 with the pre-B3 code); now `import amm` succeeds and the first MKL use raises
a RuntimeError that says what to do (import amm before torch). tests/test_runtime.py checks the order in fresh
interpreters.

MKL_CBWR=AUTO,STRICT (conditional numerical reproducibility): without it threaded PARDISO results differ in the last
bits between processes, which breaks exact replay of agent sessions (amm.tools.replay). AUTO,STRICT keeps the fastest
code path for this CPU; cost about 4 % on a static solve (results/probe/NOTES.md). MKL reads the variable when it
initializes, so it is set here at import (before any solve) and by the launchers (amm.llm). `cbwr_status()` reports
what took (AUTO|STRICT = 0x10002 = 65538, off = 1).
PARDISO is memory-bound here: 16 threads (the 8 P-cores with HT on the i9-13900KF) beat 32 (1.07 vs 1.43 s per n=30
factorization, 2026-11-03). Override with MKL_NUM_THREADS.
"""
from __future__ import annotations

import os
import sys
import threading

STATE = dict(initialized=False, trigger=None, torch_loaded_before=None, cbwr_status=None)
_LOCK = threading.RLock()


def set_env_defaults():
    os.environ.setdefault("MKL_NUM_THREADS", "16")
    os.environ.setdefault("MKL_CBWR", "AUTO,STRICT")


def ensure_mkl(trigger: str = "explicit") -> dict:
    """Initialize MKL's OpenMP runtime once (a 1x1 PARDISO solve) and record the reproducibility mode. Idempotent.
    Returns STATE. Without pypardiso installed it does nothing (initialized stays False)."""
    if STATE["initialized"]:
        return STATE
    with _LOCK:
        if STATE["initialized"]:
            return STATE
        torch_before = "torch" in sys.modules
        if torch_before and os.environ.get("AMM_ALLOW_TORCH_FIRST") != "1":
            raise RuntimeError(
                "amm: torch was imported before MKL was initialized; MKL would abort with 'OMP: Error #15' "
                "(two OpenMP runtimes). Import amm (or any amm module) before torch, botorch or gpytorch. "
                "Set AMM_ALLOW_TORCH_FIRST=1 to try anyway.")
        try:
            import numpy as np
            import pypardiso
            import scipy.sparse as sp
        except ImportError:
            return STATE
        pypardiso.spsolve(sp.csr_matrix(np.ones((1, 1))), np.ones(1))
        try:
            status = int(pypardiso.ps.libmkl.MKL_CBWR_Get(-1))  # MKL_CBWR_ALL of the mkl_rt PARDISO runs on
        except Exception:  # noqa: BLE001
            status = None
        STATE.update(initialized=True, trigger=trigger, torch_loaded_before=torch_before, cbwr_status=status)
        return STATE


def cbwr_status() -> int | None:
    return ensure_mkl("cbwr_status")["cbwr_status"]


class _TorchGuard:
    """meta_path finder: runs ensure_mkl() before the first torch import, then steps aside."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "torch" or fullname.startswith("torch."):
            remove_guard()
            ensure_mkl(f"import {fullname}")
        return None  # never loads anything itself

    def invalidate_caches(self):
        pass


_GUARD = _TorchGuard()


def install_guard():
    if "torch" in sys.modules:  # too late for the guard; ensure_mkl() will raise a clear error at the first MKL use
        return
    if _GUARD not in sys.meta_path:
        sys.meta_path.insert(0, _GUARD)


def remove_guard():
    try:
        sys.meta_path.remove(_GUARD)
    except ValueError:
        pass
