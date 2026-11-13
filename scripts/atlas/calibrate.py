"""Week 3: error of the search tier (amm.atlas.SEARCH_TIER) against converged references, on the 50 G2 cells.

References (results/g2/classification_v3.json): for density, E100, G and nu100 the bracket of limit candidates
from phase means at n = 48-96 (midpoint; the half-width is the reference's own uncertainty); for gap edges the
bracket from n = 30, 40, 50. The G2 cells were chosen before the atlas existed and are not atlas grid points.
Usage: calibrate.py [--model-only]  (--model-only rebuilds the error model from calibration.json)
Output: results/atlas/calibration.json, results/atlas/error_model.json and a summary: relative error search/ref - 1 per quantity and family,
and for gap edges the error relative to the gap's mid frequency (the unit of the atlas gap slack).
"""
import glob, json, sys
import numpy as np
import amm  # noqa: F401
from amm import atlas, certify, evaluate

if "--model-only" in sys.argv:
    out = json.load(open("results/atlas/calibration.json"))
else:
  ref = {}
  for r in json.load(open("results/g2/classification_v3.json")):
      ref[(r["kind"], json.dumps(r["params"], sort_keys=True))] = r
  cells = [json.load(open(f)) for f in sorted(glob.glob("results/g2/cells/*_m0.05.json"))]
  specs = [d["spec"] for d in cells]
  rows = evaluate.evaluate_batch(specs, nu=0.3, keep_bands=True, **atlas.SEARCH_TIER)
  out = []
  for d, row in zip(cells, rows):
      sp = d["spec"]
      c = ref[(sp["kind"], json.dumps(sp["params"], sort_keys=True))]["claims"]
      rec = dict(spec=sp, family=sp["family"], err={}, ref_halfwidth={})
      for key, q in (("density_max", "density"), ("E100_min", "E100"), ("G_min", "G"), ("nu100_min", "nu100")):
          if key in c and row.get(q) is not None:
              lo, hi = c[key]["bracket"]
              m = 0.5 * (lo + hi)
              rec["err"][q] = row[q] / m - 1 if q != "nu100" else row[q] - m  # nu: absolute error
              rec["ref_halfwidth"][q] = 0.5 * (hi - lo) / abs(m) if q != "nu100" else 0.5 * (hi - lo)
      if "gap" in c and "lower_edge" in c["gap"]:
          bb = d.get("scan_gap", {}).get("below_band")
          gl = atlas.row_gaps(row)
          g = next((x for x in gl if x["below_band"] == bb), None)
          lo_r = 0.5 * (c["gap"]["lower_edge"]["lo"] + c["gap"]["lower_edge"]["hi"])
          hi_r = 0.5 * (c["gap"]["upper_edge"]["lo"] + c["gap"]["upper_edge"]["hi"])
          mid = 0.5 * (lo_r + hi_r)
          if g is None:
              rec["gap_missing_at_search_tier"] = True
          else:
              rec["err"]["gap_lo"] = (g["f_lo"] - lo_r) / mid
              rec["err"]["gap_hi"] = (g["f_hi"] - hi_r) / mid
      out.append(rec)
  json.dump(out, open("results/atlas/calibration.json", "w"), indent=1, default=float)

# extra references (scripts/atlas/extend_calibration.py): held-out phase-ladder cells and the thin end
import os
EXTRA = "results/atlas/calibration_extra.json"
if os.path.exists(EXTRA):
    have = {certify.spec_hash(r["spec"]) for r in out}
    ex = [r for h, r in json.load(open(EXTRA)).items() if h not in have and ("static" in r or "gap" in r)]
    if ex:
        srows = evaluate.evaluate_batch([r["spec"] for r in ex], nu=0.3, keep_bands=True, **atlas.SEARCH_TIER)
        for r, row in zip(ex, srows):
            rec = dict(spec=r["spec"], family=r["spec"]["family"], set=r["set"], err={}, ref_halfwidth={})
            for q, (lo, hi) in r.get("static", {}).items():
                if q == "bulk" or row.get(q) is None:
                    continue
                m = 0.5 * (lo + hi)
                rec["err"][q] = row[q] / m - 1 if q != "nu100" else row[q] - m
                rec["ref_halfwidth"][q] = 0.5 * (hi - lo) / abs(m) if q != "nu100" else 0.5 * (hi - lo)
            g = r.get("gap", {})
            raw = {int(n): e for n, e in g.get("raw", {}).items()}
            if "lower_edge" in g and 30 in raw and 40 in raw and max(
                    abs(raw[40][i] - raw[30][i]) for i in (0, 1)) > 0.25 * 0.5 * sum(raw[40]):
                rec["gap_note"] = "reference edges jump between n = 30 and 40 (a band enters the gap): not used"
            elif "lower_edge" in g:
                sg = next((x for x in atlas.row_gaps(row) if x["below_band"] == g["below_band"]), None)
                lo_r, hi_r = np.mean(g["lower_edge"]), np.mean(g["upper_edge"])
                if sg is not None:
                    rec["err"]["gap_lo"] = (sg["f_lo"] - lo_r) / (0.5 * (lo_r + hi_r))
                    rec["err"]["gap_hi"] = (sg["f_hi"] - hi_r) / (0.5 * (lo_r + hi_r))
            elif g:
                rec["gap_note"] = g.get("note")
            out.append(rec)
        json.dump(out, open("results/atlas/calibration.json", "w"), indent=1, default=float)
for r in out:
    r.setdefault("set", "g2")
print("calibration cells:", {s: sum(r["set"] == s for r in out) for s in ("g2", "heldout", "thin")})

print("relative error search/ref - 1 (nu100 and gap edges: absolute / relative to f_mid)")
for q in ("density", "E100", "G", "nu100", "gap_lo", "gap_hi"):
    for fam in ("tpms", "struts", "resonator", "all"):
        e = np.array([r["err"][q] for r in out if q in r["err"] and fam in (r["family"], "all")])
        if len(e):
            print(f"  {q:<7} {fam:<9} n={len(e):>2}  median {np.median(e):+.4f}  min {e.min():+.4f}  max {e.max():+.4f}"
                  f"  max|e| {np.abs(e).max():.4f}")
print("gap references not used:", [(r["spec"]["kind"], r["spec"]["params"], r["gap_note"]) for r in out if r.get("gap_note")])
print("gap missing at the search tier:", [(r["spec"]["kind"], r["spec"]["params"]) for r in out
                                          if r.get("gap_missing_at_search_tier")])

# error model for the atlas oracle (amm.atlas.ERROR_MODEL_PATH): true = search / (1 + e), e in [lo, hi] per family
# and quantity. Stiffness and gap edges converge from above (G2; every calibration error here is positive), so
# lo = 0; hi = SAFETY x the largest observed error. Density and nu100: symmetric, SAFETY x max |e|.
# Gap edges: few cells per family, so one range over all families.
SAFETY = 1.25
# two bins per family: "regular" (thinnest-feature parameter >= THIN_BELOW, the G2 calibration domain) and "thin";
# the thin end's errors are several times larger, so one family-wide range would make FEASIBLE nearly unreachable
THIN_BELOW = {"tpms": 0.15, "struts": 0.06, "resonator": 0.10}
model = dict(safety=SAFETY, n_cells=len(out), source="results/atlas/calibration.json", thin_below=THIN_BELOW,
             ranges={}, ranges_thin={})


def build(cells):
    m = {}
    for q in ("density", "E100", "G", "nu100"):
        e = np.array([r["err"][q] for r in cells if q in r["err"]])
        if q in ("E100", "G"):
            assert e.min() >= 0, (q, e.min())  # the one-sided model rests on this
            m[q] = [0.0, SAFETY * float(e.max())]
        else:
            m[q] = [-SAFETY * float(np.abs(e).max()), SAFETY * float(np.abs(e).max())]
    m["bulk"] = m["E100"] if m["E100"][1] >= m["G"][1] else m["G"]  # not referenced: the wider stiffness range
    for q in ("gap_lo", "gap_hi"):
        e = np.array([r["err"][q] for r in cells if q in r["err"]])
        assert e.min() >= 0, (q, e.min())
        m[q] = [0.0, SAFETY * float(e.max())]
    m["n"] = {q: sum(q in r["err"] for r in cells) for q in ("E100", "gap_lo")}
    m["median"] = {q: float(np.median([r["err"][q] for r in cells if q in r["err"]]))
                   for q in ("density", "E100", "G", "nu100", "gap_lo", "gap_hi")
                   if any(q in r["err"] for r in cells)}
    return m


gap_all = [r for r in out if "gap_lo" in r["err"]]
for fam in ("tpms", "struts", "resonator"):
    fp = atlas.FEATURE_PARAM[fam]
    cells = [r for r in out if r["family"] == fam]
    reg = [r for r in cells if r["spec"]["params"][fp] >= THIN_BELOW[fam] - 1e-9]
    # gap edges: too few cells per family; regular = all families' regular cells, thin = every gap cell
    gap_reg = [r for r in gap_all if r["spec"]["params"][atlas.FEATURE_PARAM[r["family"]]]
               >= THIN_BELOW[r["family"]] - 1e-9]
    mr, mt = build(reg + gap_reg), build(cells + gap_all)
    br, bt = build(reg), build(cells)
    for q in ("density", "E100", "G", "nu100", "bulk"):  # static ranges and medians from this family only
        mr[q], mt[q] = br[q], bt[q]
        if q in br["median"]:
            mr["median"][q], mt["median"][q] = br["median"][q], bt["median"][q]
    mr["median"]["bulk"] = max(mr["median"]["E100"], mr["median"]["G"])
    mt["median"]["bulk"] = max(mt["median"]["E100"], mt["median"]["G"])
    model["ranges"][fam], model["ranges_thin"][fam] = mr, mt
def dom_key(sp):  # TPMS: per mode (network TPMS stop percolating at a higher density than sheets)
    return f"tpms:{sp['params']['mode']}" if sp["family"] == "tpms" else sp["family"]


static_ok = [r for r in out if "E100" in r["err"]]
model["domain"] = {}
for r in static_ok:
    k, p = dom_key(r["spec"]), atlas.FEATURE_PARAM[r["family"]]
    v = r["spec"]["params"][p]
    model["domain"][k] = {p: min(v, model["domain"].get(k, {p: v})[p])}
model["domain_note"] = "error ranges hold for cells whose thinnest-feature parameter is >= this value (min covered)"
json.dump(model, open("results/atlas/error_model.json", "w"), indent=1)
print("domain:", model["domain"])
for k in ("ranges", "ranges_thin"):
    print(k, json.dumps({f: {q: round(v[1], 3) for q, v in m.items() if q not in ("n", "median")} for f, m in model[k].items()}))
    print(k, "median", json.dumps({f: {q: round(v, 3) for q, v in m["median"].items()} for f, m in model[k].items()}))
