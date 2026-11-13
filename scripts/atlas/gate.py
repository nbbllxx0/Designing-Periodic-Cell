"""Week 3 gate ("feasibility map complete"): completeness, oracle consistency, search tool, search -> certify.

  1. completeness: every kind's grid evaluated at nu = 0.3 (and the other Poisson ratios when present)
  2. oracle consistency against the 50 G2 claims whose truth is known (classification_v3.json): a TRUE claim must
     never be NOT_FOUND_IN_FAMILIES; a FALSE claim must never be FEASIBLE
  3. search on TRUE G2 claims (atlas-seeded, expected objective = median-corrected values, budget 32): found / not found, time
  4. search on targets beyond the atlas envelope (constructed from the atlas maximum): must not find
  5. search -> certify on a few found designs (the certificate is the arbiter, not the search tier)
Usage: gate.py [1-5 ...]  -> results/atlas/gate.json (merged per step), log on stdout.
"""
import glob, json, os, sys, time
import numpy as np

import amm  # noqa: F401
from amm import atlas, certify, geometry, search

STEPS = [int(x) for x in sys.argv[1:]] or [1, 2, 3, 4, 5]
OUT = "results/atlas/gate.json"
res = json.load(open(OUT)) if os.path.exists(OUT) else {}
rows = atlas.load("results/atlas/atlas_nu0.3.jsonl")
truth = {(r["kind"], json.dumps(r["params"], sort_keys=True)): r for r in json.load(open("results/g2/classification_v3.json"))}
g2 = [json.load(open(f)) for f in sorted(glob.glob("results/g2/cells/*_m0.05.json"))]


def claim_truth(d):
    return truth[(d["spec"]["kind"], json.dumps(d["spec"]["params"], sort_keys=True))]["claim_truth"]


def save():
    json.dump(res, open(OUT, "w"), indent=1, default=float)


if 1 in STEPS:
    grid = atlas.grid_specs()
    out = {}
    for nu_path in sorted(glob.glob("results/atlas/atlas_nu*.jsonl")):
        rs = atlas.load(nu_path)
        have = {certify.spec_hash(r["spec"]) for r in rs}
        per = {}
        for k in [k for ks in geometry.FAMILIES.values() for k in ks]:
            g = [s for s in grid if s["kind"] == k]
            d = [r for r in rs if r["spec"]["kind"] == k]
            per[k] = dict(grid=len(g), done=sum(certify.spec_hash(s) in have for s in g),
                          valid=sum(bool(r.get("valid")) for r in d),
                          with_gap=sum(bool(atlas.row_gaps(r, 0.02)) for r in d))
        out[os.path.basename(nu_path)] = dict(per_kind=per, complete=all(v["done"] == v["grid"] for v in per.values()))
    res["1_completeness"] = out
    save()
    print(json.dumps({k: v["complete"] for k, v in out.items()}))

if 2 in STEPS:
    t0 = time.perf_counter()
    tab = []
    for d in g2:
        o = atlas.oracle(rows, d["targets"])
        tab.append(dict(spec=d["spec"], truth=claim_truth(d), verdict=o["verdict"],
                        best_pess=o["best"][0]["slack_pess"] if o["best"] else None))
    bad = [t for t in tab if (t["truth"] == "true" and t["verdict"] == "NOT_FOUND_IN_FAMILIES")
           or (t["truth"] == "false" and t["verdict"] == "FEASIBLE")]
    from collections import Counter
    res["2_oracle"] = dict(table=tab, inconsistent=bad, counts={f"{t}/{v}": n for (t, v), n in
                                                                Counter((x["truth"], x["verdict"]) for x in tab).items()},
                           seconds=round(time.perf_counter() - t0, 1))
    save()
    print("oracle vs G2 truth:", res["2_oracle"]["counts"], "inconsistent:", len(bad))

if 3 in STEPS:
    sel = [d for d in g2 if claim_truth(d) == "true"]
    gap_cells = [d for d in sel if "gap" in d["targets"]]
    static_cells = [d for d in sel if "gap" not in d["targets"]][::4]
    out = []
    for d in gap_cells + static_cells:
        r = search.search(d["targets"], atlas_rows=rows, budget=32, q=8, seed=0)
        b = r["best"][0]
        out.append(dict(source=d["spec"], targets=d["targets"], found=r["found"], best=b["spec"],
                        found_pessimistic=r["found_pessimistic"], slack_expected=b["slack_expected"],
                        slack_pess=b["slack_pess"], slack_nominal=b["slack_nominal"], from_atlas=b["from_atlas"],
                        calibrated=b["calibrated"], arms=r["arms"], seconds=r["seconds"]))
        print(json.dumps(dict(src=d["spec"]["kind"], p=d["spec"]["params"], gap="gap" in d["targets"],
                              found=r["found"], best=b["spec"]["kind"], bp=b["spec"]["params"],
                              exp=round(b["slack_expected"], 3), pess=round(b["slack_pess"], 3),
                              nom=round(b["slack_nominal"], 3), s=r["seconds"])),
              flush=True)
    res["3_search_true_claims"] = out
    save()

if 4 in STEPS:
    # beyond the envelope: at a density cap, ask for more E100 than any atlas cell has at or below that density,
    # by 30 %; and a gap wider than any atlas gap at its mid-frequency by 30 %
    ok = [r for r in rows if r.get("valid")]
    briefs = []
    for dmax in (0.15, 0.3, 0.45):
        e = max(r["E100"] for r in ok if r["density"] <= dmax)
        briefs.append({"density_max": dmax, "E100_min": 1.3 * e})
    # gap: centred at fc, 1.3 x the widest relative width of any atlas gap containing fc (kept below rel 1.6 so
    # that f_lo stays positive and the target is not trivially refuted by the f = 0 rule of the bounds tool)
    gl = [(r, g) for r in ok for g in atlas.row_gaps(r, 0.02)]
    for fc in (0.75, 0.85):
        w = max(2 * min(fc - g["f_lo"], g["f_hi"] - fc) / fc for r, g in gl if g["f_lo"] <= fc <= g["f_hi"])
        rel = min(1.3 * w, 1.6)
        briefs.append({"gap": {"f_lo": fc * (1 - rel / 2), "f_hi": fc * (1 + rel / 2)}})
    out = []
    for t in briefs:
        o = atlas.oracle(rows, t)
        r = search.search(t, atlas_rows=rows, budget=32, q=8, seed=0, objective="opt")
        out.append(dict(targets=t, oracle=o["verdict"], search_found_optimistic=r["found"],
                        best_opt=r["best"][0]["slack_opt"], best_nominal=r["best"][0]["slack_nominal"],
                        seconds=r["seconds"]))
        print(json.dumps(out[-1], default=float), flush=True)
    res["4_beyond_envelope"] = out
    save()

if 5 in STEPS:
    found = [x for x in res.get("3_search_true_claims", []) if x["found"]]
    pick = [x for x in found if "gap" in x["targets"]][:2] + [x for x in found if "gap" not in x["targets"]][:3]
    out = []
    for x in pick:
        t0 = time.perf_counter()
        c = certify.certify(x["best"], x["targets"])
        os.makedirs("results/atlas/certs", exist_ok=True)
        json.dump(c, open(f"results/atlas/certs/{c['spec_hash']}.json", "w"), indent=1, default=float)
        b = c["blocks"]
        out.append(dict(spec=x["best"], targets=x["targets"], slack_pess=x["slack_pess"], passed=c["passed"],
                        robust=c["robust"], static_passed=b["static"]["passed"],
                        bloch_passed=b.get("bloch", {}).get("passed"),
                        reason=(b["static"].get("checks_failed") or []) + [b.get("bloch", {}).get("reason")],
                        bloch=dict(resolutions={n: dict(passed=r.get("passed"), n_failures=r.get("n_failures"), failures=(r.get("failures") or [])[:3])
                                                for n, r in b.get("bloch", {}).get("resolutions", {}).items()},
                                   convergence=b.get("bloch", {}).get("convergence"), edge_failure=b.get("bloch", {}).get("edge_failure")) if "bloch" in b else None,
                        seconds=c["seconds"]))
        print(json.dumps(out[-1], default=float), flush=True)
    res["5_search_then_certify"] = out
    save()
