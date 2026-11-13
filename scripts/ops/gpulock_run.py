"""Run a command while holding the shared solver lock (same protocol as scripts/bench/e4.py GpuLock).

    python scripts/ops/gpulock_run.py <who> -- <command> [args...]

The lock file C:/AI/AgenticMetamaterials_workspaces/gpu.lock is created exclusively with {pid, who, t}; a lock left
by a dead process is removed; otherwise the call waits (15 s polls). The lock is released when the command ends.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

WS_ROOT = Path(__file__).resolve().parents[2].parent / "AgenticMetamaterials_workspaces"


def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                             timeout=30).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001
        return True


class GpuLock:
    def __init__(self, who: str, name: str = "gpu.lock"):
        self.path, self.who = WS_ROOT / name, who

    def __enter__(self):
        WS_ROOT.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps(dict(pid=os.getpid(), who=self.who, t=time.time())).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    info = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    info = {}
                if info.get("pid") and not _pid_alive(int(info["pid"])):
                    self.path.unlink(missing_ok=True)
                    continue
                time.sleep(2)  # short polls: other runners take the lock in short bursts

    def __exit__(self, *a):
        # Release only our own lock. An unconditional unlink let any exiting holder delete another process's lock
        # (found by V2 on 2026-11-08: V2 and V6 then held the solver at the same time).
        try:
            info = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return
        if info.get("pid") == os.getpid():
            self.path.unlink(missing_ok=True)


def main(argv):
    who = argv[0]
    cmd = argv[argv.index("--") + 1:]
    with GpuLock(who):
        return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
