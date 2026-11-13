"""V12 (audit-loop round 2, 2026-11-09): pooled checker outcomes and abstention causes (domain and editor reviewers).

Reads the 85 unique certificates of the search benchmark (results/verification/v3/certs) and the certificates of
the robust-mount rerun (results/verification/v11/robust_mount), and tallies verdicts and, for every certificate that
is not certified, the deciding block and its recorded reason.

    python scripts/experiments/v12_pooled_outcomes.py
Writes results/verification/v12/pooled_outcomes.json. Reads stored records only; no solver, no LLM.
"""
import collections
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v12"
SETS = {"benchmark": "results/verification/v3/certs/*.json",
        "robust_mount": "results/verification/v11/robust_mount/**/certificates/*.json"}


def cause(d):
    b = d["blocks"]
    out = []
    st = b.get("static", {}).get("verdict", {})
    if isinstance(st, dict) and st.get("verdict") not in (None, "certified"):
        bad = sorted(k for k, v in st.get("targets", {}).items() if v != "certified")
        out.append(f"static {st.get('verdict')}: {', '.join(bad)}")
    bl = b.get("bloch", {}).get("verdict", {})
    if isinstance(bl, dict) and bl.get("verdict") not in (None, "certified"):
        out.append(f"gap {bl.get('verdict')}: {bl.get('reason')}")
    return "; ".join(out) or "none recorded"


def main():
    res = {}
    for name, pat in SETS.items():
        fs = sorted(f for f in glob.glob(str(ROOT / pat), recursive=True) if not f.endswith(".summary.json"))
        recs = [json.loads(Path(f).read_text()) for f in fs]
        verdicts = collections.Counter(d["verdict"] for d in recs)
        causes = collections.Counter(cause(d) for d in recs if d["verdict"] != "certified")
        res[name] = dict(n=len(recs), verdicts=dict(verdicts), causes=dict(causes.most_common()))
        print(name, json.dumps(res[name], indent=1))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pooled_outcomes.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
