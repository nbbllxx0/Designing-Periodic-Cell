"""V17 (2026-11-10): spread of the two-level extrapolation of the Lucklum-Vellekoop gap edges over the convergence orders
the edge guard admits (fitted p in [0.25, 8], used capped at 2, so 0.25 <= p <= 2), from the stored n = 40 and 60 edges
(results/verification/lucklum2018_ball079_beam005.json). Answers the audit item that the agreement with the published
edges assumes first order. Stored data only; CPU, seconds; no GPU, no LLM.

    python scripts/experiments/v17_lucklum_order_spread.py
Output: results/verification/v17/lucklum_order_spread.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results/verification/lucklum2018_ball079_beam005.json"
OUT = ROOT / "results/verification/v17/lucklum_order_spread.json"
ORDERS = (0.25, 0.5, 1.0, 2.0)


def main():
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    e = {r["n"]: r["gaps_fa_over_cl"][0] for r in rows}
    pub = {"f_lo": rows[0]["paper"]["lo"], "f_hi": rows[0]["paper"]["hi"]}
    out = dict(source=str(SRC.relative_to(ROOT)).replace("\\", "/"), levels=[40, 60], orders=list(ORDERS), edges={})
    for side in ("f_lo", "f_hi"):
        a, b = e[40][side], e[60][side]
        ext = {str(p): b + (b - a) / (1.5 ** p - 1) for p in ORDERS}
        rel = {p: 100 * (x - pub[side]) / pub[side] for p, x in ext.items()}
        out["edges"][side] = dict(n40=a, n60=b, published=pub[side], extrapolated=ext, rel_pct=rel,
                                  rel_pct_range=[min(rel.values()), max(rel.values())])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for side, v in out["edges"].items():
        print(side, {p: round(r, 2) for p, r in v["rel_pct"].items()})


if __name__ == "__main__":
    main()
