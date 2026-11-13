"""V1b post-hoc (deviation 8): eigensolver-free band comparison for the no-gap cells. For each k of the refinement
subset, probe frequencies are placed at the midpoints of the gaps (> 2 % relative) between the distinct eigenvalue
clusters of the finest Q2-FCM spectrum; at each probe the number of eigenvalues below it is counted by the PARDISO
inertia of the real 2N form of K(k) - sigma M(k), for Q2-FCM (own driver) at n1, n2, n3 and for amm's model (amm's
assembly and amm's PARDISO wrapper) at n = 20, 30, 40. The counts are compared with the counts implied by each
code's Lanczos spectrum (detects lost or spurious copies of degenerate eigenvalues) and between the codes.

    inertia_bands.py <cell id> [--flagged]   -> results/verification/v1b/<id>_inertia_bands.json
--flagged: only the k whose band rows in compare_<id>.json have a crossing flag or a finest-level difference above
5 % (the TPMS sheet run over all 8 k would have taken about an hour).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MKL_NUM_THREADS", "6")
os.environ.setdefault("OMP_NUM_THREADS", "6")
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
import q2fcm  # noqa: E402
from amm import bloch, certify  # noqa: E402
from amm.pardiso import Pardiso  # noqa: E402

OUT = ROOT / "results" / "verification" / "v1b"
PI = np.pi


def clusters(f, rtol=1e-4):
    f = np.sort(np.asarray(f))
    return np.split(f, np.flatnonzero(np.diff(f) > rtol * f[1:]) + 1)


def probes_of(f, gap=0.02):
    cl = clusters(f)
    return [0.5 * (a[-1] + b[0]) for a, b in zip(cl[:-1], cl[1:]) if (b[0] - a[-1]) > gap * b[0]]


def implied(f, p):
    return int(np.sum(np.asarray(f) < p))


def q2_count(m, k, fc):
    K0, M0 = m.matrices()
    ph = np.exp(1j * (m._lattice_offsets().astype(float) @ np.asarray(k, float)))
    ps = q2fcm.Pardiso(-2)
    st = ps.factor(m._real2n_upper(K0 * ph - m.sigma(fc) * (M0 * ph)))
    ps.free()
    return st["n_neg"] // 2, st["n_perturbed"], st["n_neg"] % 2


def amm_count(mesh, ps, k, fc):
    Kd = mesh.csr_data(mesh.element_values("K", k)).astype(complex)
    Md = mesh.csr_data(mesh.element_values("M", k)).astype(complex)
    st = ps.factor(mesh.real2n_upper(Kd - bloch.f_to_sigma(fc, mesh.nu) * Md))
    return st["n_neg"] // 2, st["n_perturbed"]


def main(cid, flagged=False):
    cells = {c["id"]: c for c in json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]}
    cell = cells[cid]
    q = json.loads((OUT / "q2" / f"{cid}_bloch.json").read_text(encoding="utf-8"))
    a = json.loads((OUT / f"{cid}_amm_k.json").read_text(encoding="utf-8"))
    lv = [str(n) for n in q["levels"]]
    sub = [(r["set"], r["i"], r["k"]) for r in q["levels_data"][lv[-1]]["rows"]]
    if flagged:
        cmp_rows = json.loads((OUT / f"compare_{cid}.json").read_text(encoding="utf-8"))["bands"]["rows"]
        keys = {(r["set"], r["i"]) for r in cmp_rows if r.get("crossing_q2") or r.get("crossing_amm")
                or abs((r.get("finest") or {}).get("rel", 0)) > 0.05}
        sub = [x for x in sub if x[:2] in keys]
    fin = {(r["set"], r["i"]): r["f"] for r in q["levels_data"][lv[-1]]["rows"]}
    probes = {key[:2]: probes_of(fin[key[:2]]) for key in sub}
    t0 = time.perf_counter()
    rows = {f"{s}:{i}": dict(set=s, i=i, k=k, probes=probes[(s, i)], q2={}, amm={}) for s, i, k in sub}
    d = q2fcm.Design(cell["spec"])
    for n in lv:
        m = q2fcm.Q2FCM(d, int(n), cell["nu"], log=lambda s: None)
        lrows = {(r["set"], r["i"]): r for r in q["levels_data"][n]["rows"]}
        for s, i, k in sub:
            f = lrows[(s, i)]["f"]
            res = []
            for p in probes[(s, i)]:
                c, pert, odd = q2_count(m, np.array(k) * PI, p)
                res.append(dict(probe=p, count=int(c), lanczos=implied(f, p), perturbed=int(pert), odd=int(odd)))
            rows[f"{s}:{i}"]["q2"][n] = res
        print(cid, "q2 n", n, round(time.perf_counter() - t0, 1), "s", flush=True)
        del m
    for n in ("20", "30", "40"):
        mesh, _ = certify._mesh(cell["spec"], int(n), cell["nu"])
        ps = Pardiso(mtype=-2)
        arows = {(r["set"], r["i"]): r for r in a["levels"][n]["rows"]}
        for s, i, k in sub:
            if (s, i) not in arows:
                continue
            f = arows[(s, i)]["f"]
            res = []
            for p in probes[(s, i)]:
                c, pert = amm_count(mesh, ps, np.array(k) * PI, p)
                res.append(dict(probe=p, count=int(c), lanczos=implied(f, p), perturbed=int(pert)))
            rows[f"{s}:{i}"]["amm"][n] = res
        ps.free()
        print(cid, "amm n", n, round(time.perf_counter() - t0, 1), "s", flush=True)
    out = dict(id=cid, flagged_only=flagged, q2_levels=q["levels"], amm_levels=[20, 30, 40], rows=list(rows.values()),
               seconds=round(time.perf_counter() - t0, 1))
    # summaries
    lz_q = [(r["set"], r["i"], n, e) for r in out["rows"] for n, L in r["q2"].items() for e in L if e["count"] != e["lanczos"]]
    lz_a = [(r["set"], r["i"], n, e) for r in out["rows"] for n, L in r["amm"].items() for e in L if e["count"] != e["lanczos"]]
    cross = [(r["set"], r["i"], e1["probe"], e1["count"], e2["count"]) for r in out["rows"] if "40" in r["amm"]
             for e1, e2 in zip(r["q2"][lv[-1]], r["amm"]["40"]) if e1["count"] != e2["count"]]
    out["summary"] = dict(n_probes=sum(len(r["probes"]) for r in out["rows"]),
                          q2_lanczos_vs_inertia_mismatch=[dict(set=s, i=i, n=n, **e) for s, i, n, e in lz_q],
                          amm_lanczos_vs_inertia_mismatch=[dict(set=s, i=i, n=n, **e) for s, i, n, e in lz_a],
                          q2_finest_vs_amm40_count_mismatch=[dict(set=s, i=i, probe=p, q2=c1, amm=c2)
                                                             for s, i, p, c1, c2 in cross])
    (OUT / f"{cid}_inertia_bands.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1], "--flagged" in sys.argv)
