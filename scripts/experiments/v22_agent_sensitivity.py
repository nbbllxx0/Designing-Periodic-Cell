"""V22b (2026-11-10): agent-experiment effect without the specifications whose witness certificates are no longer
certified under the released rules (results/verification/v14/witnesses.json: briefs G07, G14, M05). Stored scores only
(results/bench/e4/scores.json, confirmatory partition); per-specification means of `correct` in arms B and C, paired
difference, 95% cluster bootstrap over specifications (10,000 resamples, seed 20261110). No runs, no LLM.
Output: results/verification/v22/agent_sensitivity.json"""
import collections, json, statistics as st
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
s = [x for x in json.loads((ROOT / "results/bench/e4/scores.json").read_text()) if x["partition"] == "confirmatory"]
lost = sorted({c["brief"] for c in json.loads((ROOT / "results/verification/v14/witnesses.json").read_text())["summary"]["changed"]})
def eff(excl):
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for x in s:
        if x["correct"] in (True, False) and x["spec_key"] not in excl:
            by[x["spec_key"]][x["arm"]].append(bool(x["correct"]))
    ks = sorted(k for k, v in by.items() if v["B"] and v["C"])
    d = np.array([st.mean(by[k]["C"]) - st.mean(by[k]["B"]) for k in ks])
    rng = np.random.default_rng(20261110)
    bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(10000)]
    return dict(n_specs=len(ks), B=st.mean(st.mean(by[k]["B"]) for k in ks), C=st.mean(st.mean(by[k]["C"]) for k in ks),
                diff=float(d.mean()), ci95=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])
excl = {x["spec_key"] for x in s if x["brief"] in lost}
out = dict(lost_witness_briefs=lost, all=eff(set()), without_lost=eff(excl))
(ROOT / "results/verification/v22").mkdir(parents=True, exist_ok=True)
(ROOT / "results/verification/v22/agent_sensitivity.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
