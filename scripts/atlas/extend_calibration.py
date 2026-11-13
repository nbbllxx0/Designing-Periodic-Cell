"""Week 3: extend the search-tier calibration to the thin and low-density end of the atlas boxes.

The 50 G2 cells cover TPMS density >= 0.15, strut r >= 0.06 and ligament w >= 0.10; the atlas boxes reach 0.06,
0.04 and 0.06. References here, same standard as results/g2 (classify_v3.py):
  set "heldout"  the 12 held-out phase-ladder cells (results/g2/phase_ladder/): static only, no new solves
  set "thin"     12 new cells at the thin end: static phase means (phases 0, 1/8, 1/4, 3/8, 1/2) at n = 48, 64, 80;
                 for cells with a search-tier gap, gap edges at n = 30, 40, 50
Static bracket: fitted order / O(h) / finest of the phase means; E100, G, bulk capped above by the smallest computed
value (they converge from above). Gap: at n = 30 a trial frequency inside the gap is accepted only if the inertia
count below it equals the gap's band index at every reference k (symmetry points + the search-tier extremum k);
edges by shift-invert Lanczos at those k; the two extreme k per edge are kept for n = 40, 50.
Output: results/atlas/calibration_extra.json (resumable per cell), log on stdout.
"""
import glob, json, os, sys, time
import numpy as np
from scipy.optimize import brentq

import amm  # noqa: F401
from amm import atlas, bloch, certify, evaluate, fem, geometry as G

OUT = "results/atlas/calibration_extra.json"
PH = (0.0, 0.125, 0.25, 0.375, 0.5)
Q = ("density", "E100", "G", "bulk", "nu100")
FROM_ABOVE = ("E100", "G", "bulk")
R = lambda k, **p: dict(family="resonator", kind=k, params=p)
L = lambda k, **p: dict(family="struts", kind=k, params=p)
T = lambda k, d, m: dict(family="tpms", kind=k, params=dict(density=d, mode=m))
THIN = [T("gyroid", 0.08, "sheet"), T("schwarz_p", 0.08, "network"), T("diamond", 0.08, "network"),
        T("iwp", 0.08, "network"),
        L("sc", r=0.04, R=0.2), L("bcc", r=0.04, R=0.0), L("octet", r=0.04, R=0.0), L("sc", r=0.05, R=0.26),
        R("cube_bars", c=0.8, w=0.06), R("cube_bars", c=0.5, w=0.08), R("sphere_ligaments", c=0.35, w=0.06),
        R("sphere_ligaments", c=0.25, w=0.08),
        # added after the first run: network TPMS below density 0.10 (Schwarz P below 0.15) do not percolate
        T("gyroid", 0.08, "network"), T("diamond", 0.10, "network"), T("iwp", 0.10, "network"),
        T("schwarz_p", 0.08, "sheet")]


def order_fit(ns, vs):
    (n1, n2, n3), (v1, v2, v3) = ns[-3:], vs[-3:]
    d12, d23 = v2 - v1, v3 - v2
    if d12 == 0 or d23 == 0 or d12 * d23 < 0 or abs(d23) >= abs(d12):
        return None
    h1, h2, h3 = 1 / n1, 1 / n2, 1 / n3
    try:
        p = brentq(lambda p: (h2 ** p - h3 ** p) / (h1 ** p - h2 ** p) - d23 / d12, 0.25, 8.0)
    except ValueError:
        return None
    return v3 + d23 * h3 ** p / (h2 ** p - h3 ** p)


def bracket(ns, vs, cap=None):
    (n2, n3), (v2, v3) = ns[-2:], vs[-2:]
    c = [v3, v3 + (v3 - v2) * (1 / n3) / (1 / n2 - 1 / n3)]
    f = order_fit(ns, vs) if len(ns) >= 3 else None
    if f is not None:
        c.append(f)
    lo, hi = min(c), max(c)
    if cap is not None:
        hi = min(hi, cap)
        lo = min(lo, hi)
    return [lo, hi]


def static_ref(rows_by_key, ns):
    """rows_by_key: {"n@phase": row}. Phase means per n over the phases present."""
    out = {}
    for q in Q:
        means = [np.mean([r[q] for k, r in rows_by_key.items() if k.startswith(f"{n}@") and r.get(q) is not None])
                 for n in ns]
        cap = min(r[q] for r in rows_by_key.values() if r.get(q) is not None) if q in FROM_ABOVE else None
        out[q] = bracket(list(ns), means, cap)
    return out


def static_rows(spec):
    rows, cache = {}, {}
    for n in (48, 64, 80):
        for p in PH:
            r = certify._static_row(spec, n, 0.3, {}, cache, phase=p)
            if not r.get("numerics_ok"):
                return None, f"n={n} phase={p}: {r.get('checks_failed')}"
            rows[f"{n}@{p}"] = {q: r[q] for q in Q}
    return rows, None


def gap_ref(spec, g, ks_extra):
    ks = [np.pi * np.array(v, float) for v in bloch.SC_POINTS.values()] + list(ks_extra)
    bb = g["below_band"]
    res, kept = {}, None
    for n in (30, 40, 50):
        cov, sub, _ = G.design_cell(spec, n)
        ic = bloch.InertiaCounter(fem.build_mesh(cov, sub=sub))
        if n == 30:
            f = None
            mid = 0.5 * (g["f_lo"] + g["f_hi"])
            for trial in (mid, mid / 1.1, mid / 1.2, mid / 1.35, mid / 1.5, g["f_lo"] * 1.02):
                if all(ic.counts(k, [trial])[0]["below"] == bb for k in ks):
                    f = trial
                    break
            if f is None:
                ic.free()
                return dict(note="no trial frequency inside the gap at n = 30 (gap may close)")
            lo = [ic.edge(k, f, "below") for k in ks]
            hi = [ic.edge(k, f, "above") for k in ks]
            kept = dict(lo=[int(i) for i in np.argsort(lo)[::-1][:2]], hi=[int(i) for i in np.argsort(hi)[:2]], f=f)
        else:
            lo = {i: ic.edge(ks[i], kept["f"], "below") for i in kept["lo"]}
            hi = {i: ic.edge(ks[i], kept["f"], "above") for i in kept["hi"]}
            lo, hi = list(lo.values()), list(hi.values())
        ic.free()
        if any(x is None for x in lo + hi) or max(lo) >= min(hi):
            return dict(note=f"gap closed or edge not found at n = {n}", raw=res)
        res[n] = [max(lo), min(hi)]
    ns = sorted(res)
    return dict(below_band=bb, raw=res, f_trial=kept["f"],
                lower_edge=bracket(ns, [res[n][0] for n in ns]), upper_edge=bracket(ns, [res[n][1] for n in ns]))


recs = json.load(open(OUT)) if os.path.exists(OUT) else {}
which = sys.argv[1] if len(sys.argv) > 1 else "all"
if which in ("heldout", "all"):
    for f in sorted(glob.glob("results/g2/phase_ladder/*.json")):
        d = json.load(open(f))
        h = certify.spec_hash(d["spec"])
        if h in recs:
            continue
        rows = {k: v for k, v in d["rows"].items() if int(k.split("@")[0]) in (48, 64, 80, 96)}
        recs[h] = dict(set="heldout", spec=d["spec"], static=static_ref(rows, (48, 64, 80, 96)))
    json.dump(recs, open(OUT, "w"), indent=1, default=float)
if which in ("thin", "all"):
    for spec in THIN:
        h = certify.spec_hash(spec)
        if h in recs:
            continue
        t0 = time.perf_counter()
        rec = dict(set="thin", spec=spec)
        rows, fail = static_rows(spec)
        if rows is None:
            rec["static_fail"] = fail
        else:
            rec["static"] = static_ref(rows, (48, 64, 80))
            rec["static_rows"] = rows
        s = evaluate.evaluate_batch([spec], nu=0.3, keep_bands=True, **atlas.SEARCH_TIER)[0]
        gl = atlas.row_gaps(s, min_rel=0.05)
        if gl:
            f = np.asarray(s["bands"])
            ks_path, _ = bloch.kpath(atlas.SEARCH_TIER["npts"])
            g = gl[0]
            extra = [ks_path[f[:, g["below_band"] - 1].argmax()], ks_path[f[:, g["below_band"]].argmin()]]
            rec["gap"] = gap_ref(spec, g, extra)
            rec["gap"]["search_gap"] = g
        rec["seconds"] = round(time.perf_counter() - t0, 1)
        recs[h] = rec
        json.dump(recs, open(OUT, "w"), indent=1, default=float)
        print(json.dumps(dict(kind=spec["kind"], params=spec["params"], static=rec.get("static", {}).get("E100"),
                              fail=rec.get("static_fail"), gap=rec.get("gap", {}).get("raw") or rec.get("gap", {}).get("note"),
                              s=rec["seconds"]), default=float), flush=True)
