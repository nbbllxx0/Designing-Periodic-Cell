"""V19 (2026-11-10): the finer filter gap checks (V15) and the PA12 export recheck (V16) re-judged after the order-test
fix of the confirm audit (amm.bloch._order: the convergence order is now judged on the order equation in h, not on
raw steps; on the equal-h-step ladder n = 30/40/60 the raw-step test had excluded orders p <= 1, which the stated
range 0.25-8 admits). No solve: amm.certify.rescore_bloch re-applies the released rules to the stored counts, edges
and phase edges. Every other stored result was re-run under the fix with no verdict change (v14 rescore, G2
classification, near-threshold test, checker decision value): only the 316L upper edge moves.

    python scripts/experiments/v19_order_rule_rejudge.py
Output: results/verification/v19/rejudge.json. CPU seconds; no GPU, no LLM.
"""
import json
from pathlib import Path

from amm import bloch, certify

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v19"
V15 = ROOT / "results/verification/v15/filters.json"
V16 = ROOT / "results/verification/v16/recheck_PA12.json"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    v15 = json.loads(V15.read_text(encoding="utf-8"))
    out = dict(checker=certify.checker_hash(), source_checker_v15=v15["settings"]["checker"], filters={})
    for name, c in v15["cells"].items():
        g = certify.rescore_bloch(c["bloch"], c["spec"])
        cv = g["convergence"]
        gv = g["verdict"]["verdict"]
        st = c["static_verdict"]
        overall = gv if st == "certified" else ("refuted" if "refuted" in (st, gv) else "undetermined")
        out["filters"][name] = dict(before=c["overall"], after=overall, gap_verdict=g["verdict"],
                                    safe_interval=cv.get("safe_interval"), lower_edge=cv.get("lower_edge"),
                                    upper_edge=cv.get("upper_edge"), edges=cv.get("edges"))
        print(name, c["overall"], "->", overall, cv.get("safe_interval"))
    # PA12 export recheck: re-apply the edge guard to its stored edges and phase edges
    r = json.loads(V16.read_text(encoding="utf-8"))["gap"]
    edges = {int(n): tuple(v) for n, v in r["edges"].items()}
    tg = json.loads(V16.read_text(encoding="utf-8"))["targets"]["gap"]
    new = bloch.gap_convergence(edges, tg["f_lo"], tg["f_hi"], phase_edges=r["phase_edges"])
    out["PA12_export"] = dict(before_safe=r["safe_interval"], after_safe=new["safe_interval"],
                              after_passed=new["passed"], same=bool(new["safe_interval"] == r["safe_interval"]))
    print("PA12 export", out["PA12_export"])
    # 316L against its exact-geometry reference (V18; V1c classification rule)
    import sys
    sys.path.insert(0, str(ROOT / "scripts/verify/dolfinx"))
    import compare as cmp  # noqa: E402
    ref = json.loads((ROOT / "results/verification/v18/references.json").read_text(encoding="utf-8"))["316L"]["gap"]
    s_lo, s_hi = out["filters"]["316L"]["safe_interval"]
    out["filters"]["316L"]["reference_grading"] = dict(
        verdict_lo=cmp.classify_lo(s_lo, ref["ref_lo"]["ext"], ref["ref_lo"]["u"]),
        verdict_hi=cmp.classify_hi(s_hi, ref["ref_hi"]["ext"], ref["ref_hi"]["u"]),
        margin_over_2u=dict(lo=(s_lo - ref["ref_lo"]["ext"]) / (2 * ref["ref_lo"]["u"]),
                            hi=(ref["ref_hi"]["ext"] - s_hi) / (2 * ref["ref_hi"]["u"])))
    print("316L vs reference", out["filters"]["316L"]["reference_grading"])
    (OUT / "rejudge.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
