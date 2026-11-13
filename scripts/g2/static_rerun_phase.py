"""G2 static re-run, second revision: the guarded static block with grid-phase checks (certify.static_block after
the cut-voxel bias found in the first re-run, results/g2/NOTES.md). Same honest claims as reference_and_certify.py.
Soundness reference per cell: n = 80 at grid phases 0 (first pass), 0.25 and 0.5 voxel (phase 0 only for TPMS,
whose phase spread was < 0.12 % at n = 48, results/g2/phase_study_families.log), and n = 96 where the
first re-run computed it. Stiffness converges from above (finite elements and finite-cell partial voxels both
overestimate), so a certified lower bound above the smallest of these values is unsound for certain; the O(h)
extrapolation is reported as an estimate only.
Output: results/g2/static_rerun_phase.json (resumable via results/g2/static_rerun_phase/<hash>.json)."""
import glob, json, os, time
import amm  # noqa: F401
from amm import certify, fem, geometry as G, homog

OUT = "results/g2/static_rerun_phase"
os.makedirs(OUT, exist_ok=True)
QS = ("density", "E100", "G", "bulk", "nu100")
first = {certify.spec_hash(r["spec"]): r for r in json.load(open("results/g2/static_rerun.json"))}
rows = []
for f in sorted(glob.glob("results/g2/cells/*_m0.05.json")):
    d = json.load(open(f))
    spec, h = d["spec"], certify.spec_hash(d["spec"])
    path = f"{OUT}/{h}.json"
    if os.path.exists(path):
        rows.append(json.load(open(path)))
        continue
    targets = {k: v for k, v in d["targets"].items() if k in certify.STATIC_KEYS}
    t0 = time.perf_counter()
    st = certify.static_block(spec, targets)
    t_block = round(time.perf_counter() - t0, 1)
    ref = {"80@0": d["static_ref"]["raw"]["80"]}
    for p in (0.25, 0.5) if spec["family"] != "tpms" else ():  # TPMS: phase spread < 0.12 % at n = 48
        cov, sub, _ = G.design_cell(spec, 80, phase=p)
        r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub))
        ref[f"80@{p}"] = {q: float(r[q]) for q in QS}
    if "ref96" in first.get(h, {}):
        ref["96@0"] = first[h]["ref96"]
    finest_min = {q: min(v[q] for v in ref.values()) for q in ("E100", "G", "bulk")}
    row = dict(spec=spec, targets=targets, passed=st["passed"], used=st["used"], ladder=st["ladder"],
               checks_failed=st.get("checks_failed"), reason=st.get("reason"), block_seconds=t_block,
               reference=ref, finest_min=finest_min, oh_ref=d["static_ref"]["ext"])
    if st.get("convergence"):
        qs = st["convergence"]["quantities"]
        row["guard"] = {q: dict(lower=qs[q]["lower"], upper=qs[q]["upper"], phase_spread=qs[q]["phase_spread"],
                                converged=qs[q]["converged"], monotone=qs[q]["monotone"]) for q in QS}
        row["lower_over_finest_min"] = {q: qs[q]["lower"] / finest_min[q] - 1 for q in finest_min}
    json.dump(row, open(path, "w"), indent=1, default=float)
    rows.append(row)
    print(json.dumps(dict(kind=spec["kind"], params=spec["params"], passed=row["passed"], used=row["used"],
                          over=row.get("lower_over_finest_min"), fails=row["checks_failed"], s=t_block), default=float),
          flush=True)
json.dump(rows, open("results/g2/static_rerun_phase.json", "w"), indent=1, default=float)
