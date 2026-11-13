"""Row-by-row cross-check of our periodic homogenizer against the registry catalogue (arXiv 2609.14741).

Reads `external/registry/data/catalogue.csv` (data only; none of the registry's code is imported or run).
Masks are rebuilt here from each row's stored (family, mode, freq, n, level, tie) with the level-set formulas
published in that repo's README/source, then solved with OUR solver using the same element (plain trilinear hex8),
E = 1, nu = 0.3. Output: results/verification/registry_rows.csv and a summary line.
"""
import csv, json, sys, time
from pathlib import Path
import numpy as np
import amm
from amm import fem, homog

ROOT = Path(__file__).resolve().parents[2]
CAT = ROOT / "external/registry/data/catalogue.csv"
OUT = ROOT / "results/verification"
TIE_EPS = 1e-9


def level_set(family, n, freq):
    t = (np.arange(n) + 0.5) / n
    X, Y, Z = np.meshgrid(t, t, t, indexing="ij")
    x, y, z = 2.0 * np.pi * freq[0] * X, 2.0 * np.pi * freq[1] * Y, 2.0 * np.pi * freq[2] * Z
    s, c = np.sin, np.cos
    if family == "gyroid":
        return s(x) * c(y) + s(y) * c(z) + s(z) * c(x)
    if family == "schwarz_p":
        return c(x) + c(y) + c(z)
    if family == "diamond":
        return s(x) * s(y) * s(z) + s(x) * c(y) * c(z) + c(x) * s(y) * c(z) + c(x) * c(y) * s(z)
    if family == "iwp":
        return 2 * (c(x) * c(y) + c(y) * c(z) + c(z) * c(x)) - (c(2 * x) + c(2 * y) + c(2 * z))
    if family == "neovius":
        return 3 * (c(x) + c(y) + c(z)) + 4 * c(x) * c(y) * c(z)
    if family == "fischer_koch_s":
        return c(2 * x) * s(y) * c(z) + c(x) * c(2 * y) * s(z) + s(x) * c(y) * c(2 * z)
    if family == "frd":
        return 4 * c(x) * c(y) * c(z) - (c(2 * x) * c(2 * y) + c(2 * y) * c(2 * z) + c(2 * z) * c(2 * x))
    if family == "split_p":
        return (1.1 * (s(2 * x) * s(z) * c(y) + s(2 * y) * s(x) * c(z) + s(2 * z) * s(y) * c(x))
                - 0.2 * (c(2 * x) * c(2 * y) + c(2 * y) * c(2 * z) + c(2 * z) * c(2 * x)))
    raise ValueError(family)


def mask(row):
    n = int(row["n"]); freq = tuple(int(ch) for ch in row["freq"]); lev = float(row["level"])
    g = level_set(row["family"], n, freq)
    g = np.abs(g) if row["mode"] == "sheet" else g
    off = {"legacy": 0.0, "include": TIE_EPS, "exclude": -TIE_EPS}[row["tie"]]
    return g <= lev + off


def C_of(row):
    keys = ["C11", "C22", "C33", "C12", "C13", "C23", "C44", "C55", "C66"]
    return np.array([float(row[k]) for k in keys])


def C_vec(C):
    return np.array([C[0, 0], C[1, 1], C[2, 2], C[0, 1], C[0, 2], C[1, 2], C[3, 3], C[4, 4], C[5, 5]])


if __name__ == "__main__":
    per_group = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    rows = [r for r in csv.DictReader(open(CAT)) if r["builder"] == "cpu" and float(r["conn_frac"]) == 1.0
            and int(r["n"]) <= 48]
    rng = np.random.default_rng(0)
    groups = {}
    for r in rows:
        groups.setdefault((r["family"], r["mode"]), []).append(r)
    pick = [g[i] for g in groups.values() for i in rng.choice(len(g), min(per_group, len(g)), replace=False)]
    pick.sort(key=lambda r: int(r["uid"]))
    OUT.mkdir(parents=True, exist_ok=True)
    res = []
    for r in pick:
        m = mask(r)
        t = time.perf_counter()
        out = homog.homogenize(mesh=fem.build_mesh(m, element="hex8"))
        ours, cat = C_vec(out["C"]), C_of(r)
        load_bearing = bool(np.linalg.norm(cat) > 1e-10)
        rel = float(np.linalg.norm(ours - cat) / np.linalg.norm(cat)) if load_bearing else float("nan")
        res.append(dict(uid=r["uid"], family=r["family"], mode=r["mode"], freq=r["freq"], n=r["n"], tie=r["tie"],
                        rho_cat=float(r["rho"]), rho_ours=float(m.mean()), C11_cat=cat[0], C11_ours=ours[0],
                        C44_cat=cat[6], C44_ours=ours[6], C_norm_cat=float(np.linalg.norm(cat)),
                        C_norm_ours=float(np.linalg.norm(ours)), load_bearing=load_bearing,
                        rho_mismatch=abs(float(r["rho"]) - float(m.mean())) > 1e-5, rel_err=rel,
                        seconds=round(time.perf_counter() - t, 2)))
        print(f"uid {r['uid']:>5} {r['family']:15s} {r['mode']:7s} {r['freq']} n={r['n']:>3} rho {float(r['rho']):.4f}/{m.mean():.4f} "
              f"rel err {rel:.2e}", flush=True)
    with open(OUT / "registry_rows.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
    lb = [x for x in res if x["load_bearing"]]
    e = np.array([x["rel_err"] for x in lb])
    same_mask = np.array([x["rel_err"] for x in lb if not x["rho_mismatch"]])
    zero = [x for x in res if not x["load_bearing"]]
    summary = dict(rows=len(res), load_bearing=len(lb), max_rel_err=float(e.max()), median_rel_err=float(np.median(e)),
                   n_above_1e_8=int((e > 1e-8).sum()), rho_mismatch_rows=int(sum(x["rho_mismatch"] for x in lb)),
                   max_rel_err_when_density_matches=float(same_mask.max()) if len(same_mask) else None,
                   non_load_bearing_rows=len(zero),
                   non_load_bearing_ours_max_norm=max((x["C_norm_ours"] for x in zero), default=None))
    json.dump(summary, open(OUT / "registry_rows_summary.json", "w"), indent=1)
    print(json.dumps(summary))
