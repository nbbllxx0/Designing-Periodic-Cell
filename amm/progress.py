"""Optional progress reports and cooperative cancellation for the long solver calls (B9, 2026-11-08).

The solvers call `checkpoint(stage, **info)` at natural boundaries: every static solve and rung of a certificate,
every Bloch k-point of the inertia counts and every gap-edge solve, every round of the adversarial k search, every
design of a search-tier batch and every batch of a search. With no hook installed (the default) a checkpoint
returns at once and does nothing else, so results and timings are those of the code without hooks.

A caller installs a hook for the calls made inside a `with hooks(progress=..., cancel=...)` block (or passes
`progress=` / `cancel=` to `amm.tools.Session.call`, which does the same):
  * progress: a callable that receives one dict {"stage": str, ...} per checkpoint. An Exception raised by the
    callback is swallowed (a broken progress display must never change a result or turn into a fail-closed
    verdict); a BaseException propagates.
  * cancel: an object with `is_set()` (e.g. `threading.Event`). When it is set, the next checkpoint raises
    `Cancelled`. `Cancelled` is a BaseException, not an Exception, so the fail-closed `except Exception` handlers
    of the certificate do not turn a cancel into an "undetermined" or "refuted" verdict, and `Session.call` rolls
    the call back (nothing logged, seq and budget restored).

The hook is held in a context variable: it applies to the thread (and context) that installed it. Worker threads
of a solver (the static solves of `evaluate_batch` run in a thread pool) do not see it; their checkpoints are in
the calling thread.
"""
from __future__ import annotations

import contextlib
import contextvars

_HOOK: contextvars.ContextVar = contextvars.ContextVar("amm_progress_hook", default=None)


class Cancelled(BaseException):
    """Raised at a solver checkpoint when the caller's cancel flag is set (see the module docstring)."""


@contextlib.contextmanager
def hooks(progress=None, cancel=None):
    """Install a progress callback and/or a cancel flag for the calls inside the block (None, None: no hook)."""
    if progress is None and cancel is None:
        yield
        return
    tok = _HOOK.set((progress, cancel))
    try:
        yield
    finally:
        _HOOK.reset(tok)


def active() -> bool:
    return _HOOK.get() is not None


def check_cancel(stage: str = "") -> None:
    h = _HOOK.get()
    if h is not None and h[1] is not None and h[1].is_set():
        raise Cancelled(f"cancelled at {stage}" if stage else "cancelled")


def checkpoint(stage: str, **info) -> None:
    """A natural boundary of a long solve: raise Cancelled if the cancel flag is set, else report progress."""
    h = _HOOK.get()
    if h is None:
        return
    progress, cancel = h
    if cancel is not None and cancel.is_set():
        raise Cancelled(f"cancelled at {stage}")
    if progress is not None:
        try:
            progress(dict(stage=stage, **info))
        except Exception:  # noqa: BLE001 -- see the module docstring: a progress display never changes a result
            pass
