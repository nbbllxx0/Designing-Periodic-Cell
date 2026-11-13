"""V4 (performance) shared helpers: output paths, environment record, memory probes, CSV/JSONL writing.

Import this module before torch (it imports amm first, so MKL initializes before torch's OpenMP runtime).
Nothing in amm/ is changed; amm is used as installed in the checkout.
"""
from __future__ import annotations

import csv
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import amm  # noqa: F401  (MKL before torch)

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v4"
RAW = OUT / "raw"
PY = sys.executable


def env_record() -> dict:
    """Software, hardware and thread settings of this process (written next to every raw result)."""
    import ctypes

    import numpy
    import pypardiso
    import scipy
    from amm import certify, tools
    rec = dict(python=sys.version.split()[0], platform=platform.platform(), amm=amm.__version__,
               checker=certify.checker_hash(), code=tools.code_hash(), numpy=numpy.__version__,
               scipy=scipy.__version__, pypardiso=getattr(pypardiso, "__version__", None),
               MKL_NUM_THREADS=os.environ.get("MKL_NUM_THREADS"), OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS"),
               MKL_CBWR=os.environ.get("MKL_CBWR"), cpu=platform.processor(), logical_cpus=os.cpu_count())
    try:
        buf = ctypes.create_string_buffer(256)
        pypardiso.ps.libmkl.MKL_Get_Version_String(buf, 256)
        rec["mkl"] = buf.value.decode()
    except Exception:  # noqa: BLE001
        rec["mkl"] = None
    if "torch" in sys.modules:
        import torch
        rec.update(torch=torch.__version__, cuda=torch.version.cuda,
                   gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                   torch_threads=torch.get_num_threads())
    return rec


def mem() -> dict:
    """Process memory (MB): current working set and the lifetime peak working set (Windows psutil fields)."""
    import psutil
    m = psutil.Process().memory_info()
    return dict(rss_mb=round(m.rss / 2**20, 1), peak_wset_mb=round(getattr(m, "peak_wset", m.rss) / 2**20, 1))


def run_child(args: list[str], env_over: dict | None = None, timeout: float = 3600) -> dict:
    """Run `python <args>` in a fresh process; the child prints one JSON line prefixed by 'RESULT '."""
    env = dict(os.environ)
    env.update({k: str(v) for k, v in (env_over or {}).items()})
    env["PYTHONUNBUFFERED"] = "1"
    t = time.perf_counter()
    p = subprocess.run([PY, "-B", *args], capture_output=True, text=True, env=env, timeout=timeout, cwd=str(ROOT))
    wall = time.perf_counter() - t
    res = None
    for line in p.stdout.splitlines():
        if line.startswith("RESULT "):
            res = json.loads(line[7:])
    if res is None:
        raise RuntimeError(f"child {args} failed (rc {p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")
    res["child_wall_s"] = round(wall, 3)
    return res


def emit(obj):
    print("RESULT " + json.dumps(obj, default=_jd), flush=True)


def _jd(o):
    import numpy as np
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


def append_jsonl(path: Path, rec: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=_jd) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_csv(path: Path, rows: list[dict], cols: list[str] | None = None):
    cols = cols or list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
