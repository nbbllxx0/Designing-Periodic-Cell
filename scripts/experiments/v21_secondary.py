"""V21 secondary outcomes (PROTOCOL.md, "Secondary outcomes"), computed after `v21_heldout.py analyse`.

Reads results/verification/v21_heldout/results.json and the DOLFINx raw levels; writes secondary.json:
  yield (certified true / true), abstention reasons by claim truth, the fraction of the reference gap that the
  safe interval gives up, k coverage (edges over amm's 37 k vs all k DOLFINx evaluated, at n = 10 and 15, and the
  DOLFINx n = 10 k search), and the search-tier gap error relative to the reference.
No solves.   python scripts/experiments/v21_secondary.py
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v21_heldout"
RAW = ROOT / "results/verification/dolfinx/raw"
INP = ROOT / "results/verification/dolfinx/inputs"
sys.path.insert(0, str(ROOT / "scripts/verify/dolfinx"))
import compare as cmp  # noqa: E402


def main():
    res = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    cells = json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]
    search = {c["name"]: c for c in cells}
    reasons = collections.Counter()
    n_true = n_true_cert = 0
    given_up, cov, gaperr = [], {}, {}
    for name, c in res["cells"].items():
        if "claims" not in c:
            continue
        for key, r in c["claims"].items():
            if r["truth"] == "true":
                n_true += 1
                n_true_cert += r["verdict"] == "certified"
            if r["verdict"] != "certified":
                reason = (r.get("reason") or "").split(":")[0].split(" (")[0]
                reasons[f"{r['truth']}: {reason}"] += 1
            if "gap_given_up" in r:
                given_up.append(dict(cell=name, claim=key, given_up=r["gap_given_up"]))
        inp = json.loads((INP / f"{name}.json").read_text(encoding="utf-8"))
        nb = inp["below_band"]
        s_amm = inp["ks"]["path"] + inp["ks"]["interior"] + inp["ks"]["adversarial"]
        cv = {}
        for n in (10, 15):
            L = cmp.load(RAW / name / f"q2_n{n}.json")
            ea, ed = cmp.edges(L["records"], nb, s_amm), cmp.edges(L["records"], nb, None)
            cv[str(n)] = dict(d_lo=ed[0] - ea[0], d_hi=ea[1] - ed[1], n_k_all=len(L["records"]))
        srch = cmp.load(RAW / name / "search.json")
        L10 = cmp.load(RAW / name / "q2_n10.json")
        ea = cmp.edges(L10["records"], nb, s_amm)
        cv["search_n10"] = dict(d_lo=srch["search"]["lo"]["best"] - ea[0], d_hi=ea[1] - srch["search"]["hi"]["best"])
        cov[name] = cv
        g = search[name]["search_gap"]
        gaperr[name] = dict(lo_rel=(g["f_lo"] - c["ref_lo"]["ext"]) / c["ref_lo"]["ext"],
                            hi_rel=(g["f_hi"] - c["ref_hi"]["ext"]) / c["ref_hi"]["ext"])
    rel_miss = max(max(v[k]["d_lo"] / res["cells"][n]["ref_lo"]["ext"], v[k]["d_hi"] / res["cells"][n]["ref_hi"]["ext"])
                   for n, v in cov.items() for k in v)
    out = dict(yield_=dict(true=n_true, certified_true=n_true_cert), abstentions=dict(reasons),
               gap_given_up=given_up, k_coverage=cov, k_coverage_max_rel_miss=rel_miss, search_gap_error=gaperr)
    (OUT / "secondary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(dict(yield_=out["yield_"], abstentions=out["abstentions"], gap_given_up=given_up,
                          k_coverage_max_rel_miss=rel_miss, search_gap_error=gaperr), indent=1))


if __name__ == "__main__":
    main()
