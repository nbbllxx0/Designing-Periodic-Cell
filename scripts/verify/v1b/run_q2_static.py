"""V1b: independent Q2-FCM homogenization of the six cells at several resolutions (no amm import).

    run_q2_static.py [n ...] [--cells id,id]      -> results/verification/v1b/q2/<id>_static_n<n>.json
CPU only; MKL threads from the environment (default 12).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MKL_NUM_THREADS", "12")
os.environ.setdefault("OMP_NUM_THREADS", "12")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import q2fcm  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v1b"


def main(argv):
    only = None
    if "--cells" in argv:
        i = argv.index("--cells")
        only = set(argv[i + 1].split(","))
        argv = argv[:i] + argv[i + 2:]
    ns = [int(a) for a in argv] or [16, 24, 32]
    (OUT / "q2").mkdir(parents=True, exist_ok=True)
    cells = json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]
    for c in cells:
        if only and c["id"] not in only:
            continue
        d = q2fcm.Design(c["spec"])
        for n in ns:
            f = OUT / "q2" / f"{c['id']}_static_n{n}.json"
            if f.exists():
                continue
            t0 = time.perf_counter()
            m = q2fcm.Q2FCM(d, n, c["nu"])
            r = m.homogenize()
            r.update(id=c["id"], nu=c["nu"], threshold=d.thr, wall_s=round(time.perf_counter() - t0, 1),
                     full_element_check=m.full_check, alpha=q2fcm.ALPHA, mkl_threads=os.environ.get("MKL_NUM_THREADS"))
            if n == ns[0]:
                r["density_fine256"] = d.density_fine(256)
            f.write_text(json.dumps(r, indent=1), encoding="utf-8")
            print(c["id"], n, f"E100={r['E100']:.6g} G={r['G']:.6g} bulk={r['bulk']:.6g} rho={r['density']:.6f}",
                  f"ndof={r['n_dofs']} res={r['residual']:.1e} {r['wall_s']}s", flush=True)
            del m


if __name__ == "__main__":
    main(sys.argv[1:])
