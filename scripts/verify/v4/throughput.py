"""V4 item 1: search-tier throughput (cells per second) against batch size, cold and warm, on the GPU.

    python scripts/verify/v4/throughput.py            # driver: one fresh process per (family, batch, threads)
    python scripts/verify/v4/throughput.py --child FAMILY B   # one measurement process

Evaluator: amm.evaluate.evaluate_batch(specs, nu=0.3, keep_bands=True, **amm.atlas.SEARCH_TIER), the call the
search tool and the atlas build make (static n = 20 on CPU PARDISO in a 4-worker thread pool, Bloch n = 10 dense
complex64 on the GPU, 21 k-points, 24 eigenvalues). The evaluate tool itself caps a call at 16 designs; batches of
64 are library calls.
Per process: import time (amm.evaluate + torch); the COLD call = the first evaluate_batch call of the process on B
specs (includes CUDA context creation, cuSOLVER/cuBLAS loading, MKL initialization, finite-cell tables); then two
WARM calls on two further sets of B distinct specs. Specs are random (seeded) inside the family box.
Run under the GPU lock: python scripts/ops/gpulock_run.py v4 -- python scripts/verify/v4/throughput.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402  (imports amm before torch)

FAMILIES = {"tpms": "gyroid (network)", "struts": "bcc (R = 0)", "resonator": "cube_bars"}
BATCHES = (1, 4, 16, 64)
RAWF = common.RAW / "throughput.jsonl"


def specs_for(family: str, n: int, seed: int) -> list[dict]:
    import numpy as np
    from amm import atlas
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < n:
        if family == "tpms":
            out.append(atlas.make_spec("gyroid", dict(density=rng.uniform(0.12, 0.45)), "network"))
        elif family == "struts":
            out.append(atlas.make_spec("bcc", dict(r=rng.uniform(0.05, 0.12), R=0.0)))
        else:
            c = rng.uniform(0.40, 0.80)
            w = rng.uniform(0.08, min(0.30, c - 0.04))
            out.append(atlas.make_spec("cube_bars", dict(c=c, w=w)))
    return out


def child(family: str, B: int):
    t = time.perf_counter()
    from amm import atlas, evaluate
    import torch
    import_s = time.perf_counter() - t
    rows = []
    n_warm = max(2, 16 // B)
    # call 0 cold; calls 1..n_warm warm on new spec sets; last call warm on the cold call's specs (same-spec check)
    plan = [("cold", 0)] + [("warm", i) for i in range(1, n_warm + 1)] + [("warm_same_as_cold", 0)]
    for i, (label, sset) in enumerate(plan):
        specs = specs_for(family, B, seed=1000 * B + sset)
        torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        out = evaluate.evaluate_batch(specs, nu=0.3, keep_bands=True, **atlas.SEARCH_TIER)
        torch.cuda.synchronize()
        wall = time.perf_counter() - t
        rows.append(dict(call=i, phase=label, wall_s=round(wall, 3), cells_per_s=round(B / wall, 4),
                         s_per_cell=round(wall / B, 4),
                         sum_static_s=round(sum(r.get("static_s", 0) or 0 for r in out), 3),
                         sum_bloch_s=round(sum(r.get("bloch_s", 0) or 0 for r in out), 3),
                         n_valid=sum(bool(r.get("valid")) for r in out),
                         n_bloch=sum(bool(r.get("bloch_valid")) for r in out),
                         gpu_peak_alloc_mb=round(torch.cuda.max_memory_allocated() / 2**20, 1),
                         gpu_peak_reserved_mb=round(torch.cuda.max_memory_reserved() / 2**20, 1), **common.mem()))
    common.emit(dict(family=family, kind=FAMILIES[family], batch=B, import_s=round(import_s, 3), calls=rows,
                     env=common.env_record()))


def driver():
    done = {(r["family"], r["batch"], r["env"]["MKL_NUM_THREADS"]) for r in common.read_jsonl(RAWF)}
    plan = [(f, B, 16) for f in FAMILIES for B in BATCHES] + [(f, 16, 4) for f in FAMILIES]
    for f, B, th in plan:
        if (f, B, str(th)) in done:
            continue
        r = common.run_child([__file__, "--child", f, str(B)], dict(MKL_NUM_THREADS=th, OMP_NUM_THREADS=th))
        common.append_jsonl(RAWF, r)
        c = r["calls"]
        warm = sorted(x["cells_per_s"] for x in c if x["phase"] == "warm")
        print(f"{f:9s} B={B:3d} thr={th:2d}: import {r['import_s']:.1f} s, cold {c[0]['cells_per_s']:.3f} cells/s, "
              f"warm median {warm[len(warm) // 2]:.3f} cells/s, same-spec warm {c[-1]['cells_per_s']:.3f}, "
              f"gpu {max(x['gpu_peak_alloc_mb'] for x in c)} MB", flush=True)


if __name__ == "__main__":
    if "--child" in sys.argv:
        i = sys.argv.index("--child")
        child(sys.argv[i + 1], int(sys.argv[i + 2]))
    else:
        driver()
