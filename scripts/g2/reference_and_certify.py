"""G2 step 2: false-alarm test on clean cells.

For each selected cell (results/g2/selected.json):
  1. Reference values, independent of the certificate's resolutions where possible:
     static at n = 64 and 80, extrapolated at O(h); gap edges at n = 30 and 40 on a denser k set (path + 30
     interior points, a different seed from the certificate's), extrapolated at O(h).
  2. An honest claim at margin M: density_max = rho (1 + M), E100_min = E (1 - M), G_min = G (1 - M),
     nu100 within +/- (0.02 + M |nu|), gap [lo (1 + M), hi (1 - M)].
  3. The release certificate (`certify.certify`, as-built off: it is a robustness flag, not part of release).
A refusal of an honest claim is a false alarm. Each cell is saved to results/g2/cells/<hash>.json (resumable).
"""
import json, os, sys, time
import numpy as np
import amm  # noqa: F401
from amm import bloch, certify, fem, geometry as G, homog

M = float(os.environ.get("G2_MARGIN", 0.05))
OUT = "results/g2/cells"
os.makedirs(OUT, exist_ok=True)


def ext(a1, a2, n1, n2):
    return a2 + (a2 - a1) * (1 / n2) / (1 / n1 - 1 / n2)


def static_ref(spec):
    rows = {}
    for n in (64, 80):
        cov, sub, info = G.design_cell(spec, n)
        r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub))
        rows[n] = {q: float(r[q]) for q in ("density", "E100", "G", "bulk", "nu100")}
    return dict(raw=rows, ext={q: ext(rows[64][q], rows[80][q], 64, 80) for q in rows[64]})


def gap_ref(spec, j, f_mid, k_extra):
    """Edges at n = 30 and 40 over the symmetry points G, X, M, R and the k-points where the scan (path + 300
    interior points) found the extrema: FP64 Lanczos at the scan's extremum, inertia screening at the others
    (`bloch._extreme_edge`, exact over this set). The scan put every extremum on the path to search precision."""
    ks = np.vstack([np.pi * np.array(v, float) for v in bloch.SC_POINTS.values()] + [np.pi * np.array(k_extra)])
    edges, t = {}, {}
    for n in (30, 40):
        t0 = time.perf_counter()
        cov, sub, _ = G.design_cell(spec, n)
        ic = bloch.InertiaCounter(fem.build_mesh(cov, sub=sub))
        if any(ic.counts(k, [f_mid])[0]["below"] != j for k in ks):
            ic.free()
            return dict(open=False, n=n)
        lo = bloch._extreme_edge(ic, ks, f_mid, "below", j, [len(ks) - 2])[0]  # Lanczos at the scan's extremum,
        hi = bloch._extreme_edge(ic, ks, f_mid, "above", j, [len(ks) - 1])[0]  # inertia screening elsewhere
        ic.free()
        edges[n], t[n] = (lo, hi), round(time.perf_counter() - t0, 1)
    return dict(open=True, below_band=j, raw={n: list(e) for n, e in edges.items()}, seconds=t,
                ext=[ext(edges[30][0], edges[40][0], 30, 40), ext(edges[30][1], edges[40][1], 30, 40)])


def run(cell):
    spec = cell["spec"]
    path = f"{OUT}/{certify.spec_hash(spec)}_m{M}.json"
    if os.path.exists(path):
        return json.load(open(path))
    t0 = time.perf_counter()
    rec = dict(spec=spec, margin=M, scan_gap=cell.get("gap"))
    rec["static_ref"] = sr = static_ref(spec)
    rec["static_ref_seconds"] = round(time.perf_counter() - t0, 1)
    e = sr["ext"]
    targets = dict(density_max=e["density"] * (1 + M), E100_min=e["E100"] * (1 - M), G_min=e["G"] * (1 - M),
                   nu100_min=e["nu100"] - (0.02 + M * abs(e["nu100"])),
                   nu100_max=e["nu100"] + (0.02 + M * abs(e["nu100"])))
    if cell.get("gap"):
        g = cell["gap"]
        rec["gap_ref"] = gr = gap_ref(spec, g["below_band"], 0.5 * (g["f_lo"] + g["f_hi"]), [g["k_lo"], g["k_hi"]])
        if gr["open"]:
            lo, hi = gr["ext"][0] * (1 + M), gr["ext"][1] * (1 - M)
            if hi > lo:
                targets["gap"] = dict(f_lo=lo, f_hi=hi)
    rec["targets"] = targets
    rec["ref_seconds"] = round(time.perf_counter() - t0, 1)
    c = certify.certify(spec, targets, as_built=False)
    rec["cert"] = dict(passed=c["passed"], timing=c["timing"], seconds=c["seconds"],
                       static=dict(passed=c["blocks"]["static"]["passed"], used=c["blocks"]["static"]["used"],
                                   reason=c["blocks"]["static"].get("reason"),
                                   values={int(n): {q: r.get(q) for q in ("density", "E100", "G", "bulk", "nu100")}
                                           | dict(checks_failed=r.get("checks_failed"), numerics_ok=r.get("numerics_ok"))
                                           for n, r in c["blocks"]["static"]["resolutions"].items()},
                                   ladder=c["blocks"]["static"].get("ladder")))
    if "bloch" in c["blocks"]:
        b = c["blocks"]["bloch"]
        rec["cert"]["bloch"] = dict(passed=b["passed"], reason=b.get("reason"),
                                    counts={int(n): dict(passed=v["passed"], n_failures=v["n_failures"],
                                                         failures=v["failures"][:3])
                                            for n, v in b.get("resolutions", {}).items()},
                                    convergence=b.get("convergence"), density_spread=b.get("density_spread"))
    json.dump(rec, open(path, "w"), indent=1, default=float)
    return rec


if __name__ == "__main__":
    cells = json.load(open("results/g2/selected.json"))
    lo, hi = (int(x) for x in (sys.argv[1:3] if len(sys.argv) > 2 else (0, len(cells))))
    for cell in cells[lo:hi]:
        t = time.perf_counter()
        r = run(cell)
        print(json.dumps(dict(kind=cell["spec"]["kind"], params=cell["spec"]["params"], passed=r["cert"]["passed"],
                              static=r["cert"]["static"]["passed"], bloch=r["cert"].get("bloch", {}).get("passed"),
                              gap_claim=r["targets"].get("gap"), ref_s=r["ref_seconds"],
                              cert_s=r["cert"]["seconds"], s=round(time.perf_counter() - t, 1))), flush=True)
