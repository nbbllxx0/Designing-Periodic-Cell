"""Wait until the shared solver lock file is free (10 ms polls), then run scripts/ops/gpulock_run.py, which takes
the lock with its usual exclusive create. Only a faster start for gpulock_run (its own polls are 2 s, and other
runners re-take the lock within that window); the lock protocol itself is unchanged.

    python scripts/verify/v2/lockwait.py <who> -- <command> [args...]
"""
import os, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT.parent / "AgenticMetamaterials_workspaces" / "gpu.lock"
while LOCK.exists():
    time.sleep(0.01)
sys.exit(subprocess.call([sys.executable, "-B", str(ROOT / "scripts" / "ops" / "gpulock_run.py")] + sys.argv[1:]))
