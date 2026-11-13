"""V1b: amm certificates for the six cells of results/verification/v1b/cells.json with the CURRENT amm code.

    run_amm.py nominal            the cells' nominal targets            -> <id>_amm.json
    run_amm.py marginal           claims of marginal_claims.json        -> <id>_amm_marginal.json

Run under the shared solver lock (the Bloch block uses the GPU for the adversarial k search):
    python scripts/ops/gpulock_run.py "V1b amm" -- python scripts/verify/v1b/run_amm.py nominal
Thread limit: MKL_NUM_THREADS=12 (set before amm is imported; amm only sets a default).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MKL_NUM_THREADS", "12")
os.environ.setdefault("OMP_NUM_THREADS", "12")
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from amm import certify  # noqa: E402

OUT = ROOT / "results" / "verification" / "v1b"


def cells():
    return json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]


def run(mode: str, only=None):
    jobs = []
    if mode == "nominal":
        jobs = [(c, c["targets"], OUT / f"{c['id']}_amm.json") for c in cells()]
    else:
        mc = json.loads((OUT / "marginal_claims.json").read_text(encoding="utf-8"))["claims"]
        by = {c["id"]: c for c in cells()}
        jobs = [(by[i], m["targets"], OUT / f"{i}_amm_marginal.json") for i, m in mc.items()]
    for cell, targets, f in jobs:
        if only and cell["id"] not in only:
            continue
        if f.exists():
            print("cached", f.name, flush=True)
            continue
        t0 = time.perf_counter()
        c = certify.certify(cell["spec"], targets, nu=cell["nu"])
        c["v1b"] = dict(id=cell["id"], mode=mode, wall_s=round(time.perf_counter() - t0, 1),
                        mkl_threads=os.environ.get("MKL_NUM_THREADS"))
        f.write_text(json.dumps(c, default=float), encoding="utf-8")
        g = c["blocks"].get("bloch", {})
        print(cell["id"], mode, c["verdict"], c["blocks"]["static"]["verdict"]["verdict"],
              (g.get("verdict") or {}).get("verdict"), (g.get("convergence") or {}).get("safe_interval"),
              round(time.perf_counter() - t0, 1), "s", flush=True)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2:] or None)
