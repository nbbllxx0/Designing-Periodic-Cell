"""The project's shared solver lock (same protocol as class GpuLock in scripts/bench/e4.py, copied, not imported, so
that nothing from the live scripts/ tree is executed)."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

WS_ROOT = Path(r"C:\AI\AgenticMetamaterials_workspaces")


def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                             timeout=30).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001
        return True


class GpuLock:
    def __init__(self, who: str, name: str = "gpu.lock", wait: bool = True):
        self.path, self.who, self.wait = WS_ROOT / name, who, wait

    def __enter__(self):
        WS_ROOT.mkdir(parents=True, exist_ok=True)
        announced = False
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps(dict(pid=os.getpid(), who=self.who, t=time.time())).encode())
                os.close(fd)
                print(f"lock acquired by {self.who}", flush=True)
                return self
            except FileExistsError:
                try:
                    info = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    info = {}
                if info.get("pid") and not _pid_alive(int(info["pid"])):
                    self.path.unlink(missing_ok=True)
                    continue
                if not self.wait:
                    raise SystemExit(f"{self.path.name} is held by {info}")
                if not announced:
                    print(f"waiting for {self.path.name} held by {info}", flush=True)
                    announced = True
                time.sleep(15)

    def __exit__(self, *a):
        self.path.unlink(missing_ok=True)
