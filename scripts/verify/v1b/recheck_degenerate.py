"""V1b post-hoc fix (deviation 5): Lanczos (nev = 15) lost copies of the 8-fold / 7-fold flat bands of the octet
cell at R on the Q2-FCM n = 20 level (multiplicities 7, 6, 2 instead of 8, 7). This recomputes the rows of a
q2/<id>_bloch.json level whose cluster multiplicities differ from the other levels, with nev = 24 (keep 15), checks
the count with the PARDISO inertia between the clusters, and writes the corrected rows back, keeping the original
row under 'replaced_row'.

    recheck_degenerate.py <cell id> <n> <set> <i> [<set> <i> ...]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MKL_NUM_THREADS", "6")
os.environ.setdefault("OMP_NUM_THREADS", "6")
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q2fcm  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v1b"
PI = np.pi


def main(cid, n, pairs):
    cells = {c["id"]: c for c in json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]}
    cell = cells[cid]
    p = OUT / "q2" / f"{cid}_bloch.json"
    q = json.loads(p.read_text(encoding="utf-8"))
    m = q2fcm.Q2FCM(q2fcm.Design(cell["spec"]), n, cell["nu"], log=print)
    rows = q["levels_data"][str(n)]["rows"]
    for s, i in pairs:
        r = next(x for x in rows if x["set"] == s and x["i"] == i)
        k = np.array(r["k"]) * PI
        res = m.near(k, 0.0, nev=24, sigma=-m.sigma(0.01))
        f = np.array(res["f"][:15])
        # inertia checks at the midpoints between the distinct clusters of the 15 kept values
        cl = np.split(f, np.flatnonzero(np.diff(f) > 1e-4 * f[1:]) + 1)
        checks = []
        for j in range(len(cl) - 1):
            fc = 0.5 * (cl[j][-1] + cl[j + 1][0])
            c = m.near(k, fc, nev=4)
            checks.append(dict(f_center=float(fc), n_below=int(c["n_below"]), expected=int(sum(map(len, cl[:j + 1])))))
        new = dict(r, f=f.tolist(), eig_res=res["eig_res"], n_perturbed=res["n_perturbed"], nev_used=24,
                   inertia_checks=checks, replaced_row=dict(f=r["f"], eig_res=r["eig_res"]))
        rows[rows.index(r)] = new
        print(cid, n, s, i, "multiplicities", [len(x) for x in cl], "checks", checks, flush=True)
    q.setdefault("post_hoc", []).append(f"level {n}: rows {pairs} recomputed with nev=24 (recheck_degenerate.py)")
    p.write_text(json.dumps(q, indent=1), encoding="utf-8")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], int(a[1]), [(a[j], int(a[j + 1])) for j in range(2, len(a), 2)])
