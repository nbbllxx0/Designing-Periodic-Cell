"""V1b: independent Q2-FCM Bloch bands of one cell at path, amm interior/adversarial and own adversarial k-points.

    run_q2_bloch.py <cell id>     -> results/verification/v1b/q2/<id>_bloch.json

Gap cells (the amm certificate <id>_amm.json carries a gap claim): band nb (top below the gap) and nb+1 (bottom
above) at every k, nb = the certificate's below_band, the Q2 inertia count at the claim centre recorded per k.
k-sets and levels: results/verification/v1b/NOTES.md section 0.3. No-gap cells: the lowest 15 bands.
The amm certificate is read only for its claim, band index and adversarial k (data); no amm code is imported.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q2fcm  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v1b"
PI = np.pi
SYM = {"G": (0, 0, 0), "X": (1, 0, 0), "M": (1, 1, 0), "R": (1, 1, 1)}


def amm_path(npts=4):
    """Same points as amm's kpath(4): legs G-X-M-G-R-X, npts per leg (end excluded), plus the final X."""
    order = ["G", "X", "M", "G", "R", "X"]
    ks = []
    for a, b in zip(order[:-1], order[1:]):
        A, B = PI * np.array(SYM[a], float), PI * np.array(SYM[b], float)
        for t in np.linspace(0, 1, npts, endpoint=False):
            ks.append(A + t * (B - A))
    ks.append(PI * np.array(SYM["X"], float))
    return np.array(ks)


def amm_interior(n=10, seed=0):
    """Same points as amm's ibz_interior(10, 0) (documented formula, recomputed here)."""
    rng = np.random.default_rng(seed)
    return np.sort(rng.uniform(0, PI, size=(n, 3)), axis=1)[:, ::-1]


def to_ibz(k):
    k = np.mod(np.asarray(k, float) + PI, 2 * PI) - PI
    return np.sort(np.abs(k), axis=-1)[..., ::-1]


DIRS = np.array([d for d in np.ndindex(3, 3, 3) if d != (1, 1, 1)], float) - 1.0
DIRS /= np.linalg.norm(DIRS, axis=1, keepdims=True)


def bands_at(model, k, fc, nb, tol=1e-9):
    """(n_below, band nb, band nb+1, record) at k; band values None if not among the computed eigenvalues."""
    r = model.near(k, fc, nev=8, tol=tol)
    f = np.array(r["f"])
    below, above = np.sort(f[f < fc]), np.sort(f[f >= fc])
    nbk = r["n_below"]
    # eigenvalue j (1-based) below fc: below[-(nbk - j + 1)]; above fc: above[j - nbk - 1]
    def band(j):
        if j <= nbk:
            i = len(below) - (nbk - j + 1)
            return float(below[i]) if 0 <= i < len(below) else None
        i = j - nbk - 1
        return float(above[i]) if 0 <= i < len(above) else None
    return nbk, band(nb), band(nb + 1), r


def gap_cell(cell, cert, levels, n_search, log):
    g = cert["blocks"]["bloch"]
    claim = g["claim"]
    nb = int(claim["below_band"])
    fc = 0.5 * (claim["f_lo"] + claim["f_hi"])
    d = q2fcm.Design(cell["spec"])
    out = dict(id=cell["id"], kind="gap", below_band=nb, claim=[claim["f_lo"], claim["f_hi"]], f_center=fc,
               levels=list(levels), n_search=n_search, alpha=q2fcm.ALPHA)
    t0 = time.perf_counter()
    # ---- own adversarial search on a coarse model
    ms = q2fcm.Q2FCM(d, n_search, cell["nu"], log=log)
    path8 = []
    order = ["G", "X", "M", "G", "R", "X"]
    for a, b in zip(order[:-1], order[1:]):
        A, B = PI * np.array(SYM[a], float), PI * np.array(SYM[b], float)
        for t in np.linspace(0, 1, 8, endpoint=False):
            path8.append(A + t * (B - A))
    path8.append(PI * np.array(SYM["X"], float))
    rng = np.random.default_rng(20261108)
    cand = np.vstack([np.array(path8), np.sort(rng.uniform(0, PI, (60, 3)), axis=1)[:, ::-1]])
    ev = []
    for k in cand:
        nbk, lo, hi, _ = bands_at(ms, k, fc, nb, tol=1e-7)
        ev.append((lo, hi))
    ev = np.array([[np.nan if v is None else v for v in e] for e in ev])
    search = {}
    n_eval = len(cand)
    for col, sgn, name in ((0, -1.0, "lo"), (1, 1.0, "hi")):  # maximize band nb, minimize band nb+1
        vals = sgn * ev[:, col]
        starts = np.argsort(np.where(np.isnan(vals), np.inf, vals))[:2]
        best = []
        for s in starts:
            cur, val, step = cand[s].copy(), ev[s, col], 0.15 * PI
            for _ in range(4):
                trial = to_ibz(cur[None, :] + step * DIRS)
                tv = []
                for k in trial:
                    _, lo, hi, _ = bands_at(ms, k, fc, nb, tol=1e-7)
                    v = lo if col == 0 else hi
                    tv.append(np.nan if v is None else v)
                n_eval += len(trial)
                tv = np.array(tv)
                j = int(np.nanargmin(sgn * tv)) if not np.all(np.isnan(tv)) else None
                if j is not None and sgn * tv[j] < sgn * val:
                    cur, val = trial[j], tv[j]
                step /= 2
            best.append(dict(k=(cur / PI).tolist(), value=float(val)))
        search[name] = best
    out["search"] = dict(n=n_search, n_evaluations=n_eval, best=search, seconds=round(time.perf_counter() - t0, 1),
                         path_random_extreme=[float(np.nanmax(ev[:, 0])), float(np.nanmin(ev[:, 1]))])
    del ms
    log(f"  search done {out['search']['seconds']}s {search}")
    # ---- k sets
    adv = np.array(g.get("adversarial", {}).get("ks") or [], float).reshape(-1, 3) * PI
    rngf = np.random.default_rng(20261109)
    full_bz = rngf.uniform(-PI, PI, (4, 3))
    sets = {"amm_path": amm_path(), "amm_interior": amm_interior(), "amm_adversarial": adv,
            "own_adversarial": np.array([b["k"] for v in search.values() for b in v]) * PI, "full_zone": full_bz}
    out["k_sets"] = {k: (v / PI).tolist() for k, v in sets.items()}
    # ---- levels
    out["levels_data"] = {}
    subset = None
    for li, n in enumerate(levels):
        t1 = time.perf_counter()
        m = q2fcm.Q2FCM(d, n, cell["nu"], log=log)
        rows = []
        if li == 0:
            items = [(name, i, k) for name, ks in sets.items() for i, k in enumerate(ks)]
        else:
            items = subset
        for name, i, k in items:
            nbk, lo, hi, r = bands_at(m, k, fc, nb)
            rows.append(dict(set=name, i=i, k=(np.asarray(k) / PI).tolist(), n_below=nbk, lo=lo, hi=hi,
                             f=r["f"], eig_res=r["eig_res"], n_perturbed=r["n_perturbed"], odd=r["odd"]))
        out["levels_data"][str(n)] = dict(rows=rows, ndof=m.ndof, density=m.density,
                                          seconds=round(time.perf_counter() - t1, 1))
        log(f"  level n={n}: {len(rows)} k, {round(time.perf_counter() - t1, 1)}s")
        if li == 0:
            lo_v = np.array([np.nan if r["lo"] is None else r["lo"] for r in rows])
            hi_v = np.array([np.nan if r["hi"] is None else r["hi"] for r in rows])
            pick = set(np.argsort(-np.nan_to_num(lo_v, nan=-np.inf))[:3].tolist())
            pick |= set(np.argsort(np.nan_to_num(hi_v, nan=np.inf))[:3].tolist())
            pick |= {j for j, r in enumerate(rows) if r["set"] == "amm_path" and r["i"] in (0, 4, 8, 16)}  # G X M R
            subset = [items[j] for j in sorted(pick)]
        del m
    out["seconds"] = round(time.perf_counter() - t0, 1)
    return out


def band_cell(cell, levels, log, nev=15):
    d = q2fcm.Design(cell["spec"])
    ks_all = np.vstack([amm_path(), amm_interior()])
    names = [("amm_path", i) for i in range(21)] + [("amm_interior", i) for i in range(10)]
    sub = [0, 4, 8, 16, 21, 22, 23, 24]  # G, X, M, R and the first 4 interior points
    out = dict(id=cell["id"], kind="bands", nev=nev, levels=list(levels), levels_data={})
    t0 = time.perf_counter()
    for li, n in enumerate(levels):
        t1 = time.perf_counter()
        m = q2fcm.Q2FCM(d, n, cell["nu"], log=log)
        idx = range(len(ks_all)) if li == 0 else sub
        rows = []
        for j in idx:
            r = m.lowest(ks_all[j], nev=nev)
            rows.append(dict(set=names[j][0], i=names[j][1], k=(ks_all[j] / PI).tolist(), f=r["f"],
                             eig_res=r["eig_res"], n_perturbed=r["n_perturbed"]))
        out["levels_data"][str(n)] = dict(rows=rows, ndof=m.ndof, density=m.density,
                                          seconds=round(time.perf_counter() - t1, 1))
        log(f"  level n={n}: {len(rows)} k, {round(time.perf_counter() - t1, 1)}s")
        del m
    out["seconds"] = round(time.perf_counter() - t0, 1)
    return out


LEVELS = {"resonator": (16, 20, 24)}
SEARCH_N = {"resonator": 8}


def main(cid):
    cells = {c["id"]: c for c in json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]}
    cell = cells[cid]
    f = OUT / "q2" / f"{cid}_bloch.json"
    (OUT / "q2").mkdir(parents=True, exist_ok=True)
    if f.exists():
        print("cached", f)
        return
    cert = json.loads((OUT / f"{cid}_amm.json").read_text(encoding="utf-8"))
    levels = LEVELS.get(cell["family"], (12, 16, 20))
    log = lambda s: print(cid, s, flush=True)
    if "bloch" in cert["blocks"]:
        res = gap_cell(cell, cert, levels, SEARCH_N.get(cell["family"], 6), log)
    else:
        res = band_cell(cell, levels, log)
    res["mkl_threads"] = os.environ.get("MKL_NUM_THREADS")
    f.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(cid, "done", res["seconds"], "s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
