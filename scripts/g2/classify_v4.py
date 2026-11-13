"""G2 with the three-way certificate verdict (certified / refuted / undetermined), from the saved re-run records.

No new solves: the static guard bounds and the Bloch reports in results/g2/rerun_v3/ are re-scored with
amm.certify.static_verdict and amm.certify.gap_verdict. Claim truth per target comes from
results/g2/classification_v3.json (references at least as fine as the certificate; see classify_v3.py).

Error classes (per cell and per target):
  false certification   certified, claim false            (soundness; must be 0)
  false refutation      refuted, claim true               (the false alarm of G2; must be 0)
  abstention            undetermined, claim true or undetermined
  correct refutation    refuted, claim false
For each abstention on a true static claim, the claim's distance from the reference limit is compared with the
guard band (safety x remaining error at the finest rung): the guard is complete if every true claim outside its
band is certified.
Output: results/g2/classification_v4.json and a table.
"""
import glob, json
from collections import Counter

import amm  # noqa: F401
from amm import certify

truth = {(r["kind"], json.dumps(r["params"], sort_keys=True)): r for r in json.load(open("results/g2/classification_v3.json"))}
out = []
for f in sorted(glob.glob("results/g2/rerun_v3/*.json")):
    r3 = json.load(open(f))
    spec, tg = r3["spec"], r3["targets"]
    t = truth.get((spec["kind"], json.dumps(spec["params"], sort_keys=True)))
    if t is None:
        continue
    st = r3["static"]
    sv = certify.static_verdict(st.get("convergence"), tg, bool(st.get("numerics_ok")))
    per = dict(sv["targets"])
    gv = None
    if "gap" in tg:
        gv = certify.gap_verdict(r3["bloch"])
        per["gap"] = gv["verdict"]
    vs = set(per.values())
    verdict = "certified" if vs == {"certified"} else ("refuted" if "refuted" in vs else "undetermined")
    rows = []
    for key, v in per.items():
        tr = t["claims"][key]["truth"]
        cls = {("certified", "false"): "FALSE CERTIFICATION", ("refuted", "true"): "FALSE REFUTATION",
               ("refuted", "false"): "correct refutation", ("certified", "true"): "certified",
               ("refuted", "undetermined"): "refuted (truth undetermined)",
               ("certified", "undetermined"): "certified (truth undetermined)"}.get((v, tr), "abstention")
        row = dict(key=key, verdict=v, truth=tr, cls=cls)
        if key in certify.STATIC_KEYS and v == "undetermined" and tr == "true":
            q, kind = certify.STATIC_KEYS[key]
            b = st["convergence"][q]
            lim = t["claims"][key]["bracket"][0 if kind == "min" else 1]
            tgt = tg[key]
            row.update(claim_distance=abs(lim / tgt - 1),
                       band=(certify.STATIC_SAFETY * b["remaining"] / abs(b["extrapolated"]))
                       if b.get("remaining") is not None else None,
                       converged=b.get("converged"), rung=st["used"])
        rows.append(row)
    cell_truth = t["claim_truth"]
    out.append(dict(kind=spec["kind"], params=spec["params"], verdict=verdict, truth=cell_truth,
                    old_cls=t["cls"], targets=rows, gap_reason=(gv or {}).get("reason")))

json.dump(out, open("results/g2/classification_v4.json", "w"), indent=1, default=float)
cells = Counter((c["verdict"], c["truth"]) for c in out)
print(len(out), "cells; (verdict, claim truth):", dict(cells))
tcls = Counter(r["cls"] for c in out for r in c["targets"])
print("targets:", dict(tcls))
print("false certifications:", [(c["kind"], c["params"], r["key"]) for c in out for r in c["targets"]
                                if r["cls"] == "FALSE CERTIFICATION"])
print("false refutations:", [(c["kind"], c["params"], r["key"]) for c in out for r in c["targets"]
                             if r["cls"] == "FALSE REFUTATION"])
print("\nabstentions on true static claims (claim distance vs guard band):")
for c in out:
    for r in c["targets"]:
        if "claim_distance" in r:
            band = f"{r['band']:.3f}" if r["band"] is not None else "n/a (not converged)"
            print(f"  {c['kind']:<16} {json.dumps(c['params']):<30} {r['key']:<9} distance {r['claim_distance']:.3f} "
                  f"band {band} rung {r['rung']}  {'OUTSIDE BAND' if r['band'] is not None and r['claim_distance'] > r['band'] else ''}")
print("\ncell table (old class -> new verdict):")
for c in out:
    if c["old_cls"] != "accepted" or c["verdict"] != "certified":
        print(f"  {c['old_cls'][:34]:<34} -> {c['verdict']:<12} truth {c['truth']:<12} {c['kind']:<16} "
              f"{json.dumps(c['params'])} {[(r['key'], r['verdict']) for r in c['targets'] if r['verdict'] != 'certified']}"
              f" {c['gap_reason'] or ''}")
