"""V1b post-hoc (deviation 6): extra Q2-FCM Bloch levels for a gap cell whose reference edge was not asymptotic,
on the refinement subset of q2/<id>_bloch.json (identical k evaluated once). Same evaluation as run_q2_bloch.

    extend_gap_levels.py <cell id> <n> [<n> ...]   -> results/verification/v1b/q2/<id>_bloch_extra.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q2fcm  # noqa: E402
from run_q2_bloch import OUT, PI, bands_at  # noqa: E402


def main(cid, ns):
    cells = {c["id"]: c for c in json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]}
    cell = cells[cid]
    q = json.loads((OUT / "q2" / f"{cid}_bloch.json").read_text(encoding="utf-8"))
    fc, nb = q["f_center"], q["below_band"]
    sub = q["levels_data"][str(q["levels"][-1])]["rows"]
    p = OUT / "q2" / f"{cid}_bloch_extra.json"
    out = json.loads(p.read_text(encoding="utf-8")) if p.exists() else dict(id=cid, levels=[], levels_data={})
    d = q2fcm.Design(cell["spec"])
    for n in ns:
        if str(n) in out["levels_data"]:
            continue
        t1 = time.perf_counter()
        m = q2fcm.Q2FCM(d, n, cell["nu"], log=print)
        cache, rows = {}, []
        for r in sub:
            key = tuple(np.round(r["k"], 12))
            if key not in cache:
                cache[key] = bands_at(m, np.array(r["k"]) * PI, fc, nb)
            nbk, lo, hi, rr = cache[key]
            rows.append(dict(set=r["set"], i=r["i"], k=r["k"], n_below=nbk, lo=lo, hi=hi, f=rr["f"],
                             eig_res=rr["eig_res"], n_perturbed=rr["n_perturbed"], odd=rr["odd"]))
        out["levels_data"][str(n)] = dict(rows=rows, ndof=m.ndof, density=m.density, distinct_k=len(cache),
                                          seconds=round(time.perf_counter() - t1, 1))
        out["levels"] = sorted(set(out["levels"]) | {n})
        print(cid, "extra level", n, len(cache), "distinct k", out["levels_data"][str(n)]["seconds"], "s", flush=True)
        p.write_text(json.dumps(out, indent=1), encoding="utf-8")
        del m


if __name__ == "__main__":
    main(sys.argv[1], [int(a) for a in sys.argv[2:]])
