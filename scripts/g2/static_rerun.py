"""G2 static re-run with the three-resolution guarded static block (certify.static_block, after the overshoot
found in the first pass). Uses the honest claims and references stored by reference_and_certify.py.
If the block escalates to (48, 64, 80), the stored reference (64, 80) is no longer independent; a finer reference
from n = 80 and 96 is computed for those cells.
Output: results/g2/static_rerun.json
"""
import glob, json, time
import amm  # noqa: F401
from amm import certify, fem, geometry as G, homog

out = []
for f in sorted(glob.glob("results/g2/cells/*_m0.05.json")):
    d = json.load(open(f))
    spec, ref = d["spec"], d["static_ref"]
    targets = {k: v for k, v in d["targets"].items() if k in certify.STATIC_KEYS}
    t0 = time.perf_counter()
    st = certify.static_block(spec, targets)
    row = dict(spec=spec, targets=targets, passed=st["passed"], used=st["used"], ladder=st["ladder"],
               checks_failed=st.get("checks_failed"), reason=st.get("reason"), seconds=None)
    ref_ext = ref["ext"]
    if st["used"] == [48, 64, 80]:
        cov, sub, _ = G.design_cell(spec, 96)
        r96 = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub))
        v80 = ref["raw"]["80"]
        ref_ext = {q: r96[q] + (r96[q] - v80[q]) * (1 / 96) / (1 / 80 - 1 / 96) for q in v80}
        row["ref96"] = {q: float(r96[q]) for q in v80}
    row["ref"] = ref_ext
    if "convergence" in st and st["convergence"]["converged"]:
        qs = st["convergence"]["quantities"]
        row["lower_over_ref"] = {q: qs[q]["lower"] / ref_ext[q] - 1 for q in ("E100", "G", "bulk")}
        row["upper_over_ref_density"] = qs["density"]["upper"] / ref_ext["density"] - 1
    row["seconds"] = round(time.perf_counter() - t0, 1)
    out.append(row)
    print(json.dumps(dict(kind=spec["kind"], params=spec["params"], passed=row["passed"], used=row["used"],
                          lower_over_ref=row.get("lower_over_ref"), fails=row["checks_failed"], s=row["seconds"]),
                     default=float), flush=True)
json.dump(out, open("results/g2/static_rerun.json", "w"), indent=1, default=float)
