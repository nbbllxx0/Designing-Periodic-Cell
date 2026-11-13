"""V12 (audit-loop round 2, 2026-11-09): decision value of the checker over the error-corrected search tier
(empirical reviewer).

For the 50 verification cells (results/g2/cells, claims 5 % inside a first-pass reference; four gap claims are
false), evaluate every claim at the search tier (amm.atlas.SEARCH_TIER, nu_s = 0.3) and classify it with the
calibrated error model:
  pass        pessimistic slack > 0 (the atlas oracle's FEASIBLE rule)
  fail        optimistic slack < 0
  borderline  otherwise
and with the nominal slack alone (pass if > 0). Compare with the checker's verdict per claim and with the truth
from the converged reference brackets (results/g2/classification_v5.json).

Caveat recorded in the output: the error model was fitted on these 50 cells (scripts/atlas/calibrate.py) plus 23
others, with a safety factor 1.25, so the pessimistic search verdict is in-sample here and favours the search tier.

    python scripts/ops/gpulock_run.py v12 -- python scripts/experiments/v12_checker_decision_value.py
Writes results/verification/v12/checker_decision_value.json. GPU (n = 10 bands), a few minutes; no LLM.
"""
import collections
import glob
import json
import time
from pathlib import Path

import amm  # noqa: F401
from amm import atlas, evaluate

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v12"


def main():
    t0 = time.perf_counter()
    cls = {(r["kind"], json.dumps(r["params"], sort_keys=True)): r
           for r in json.loads((ROOT / "results/g2/classification_v5.json").read_text())}
    cells = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(ROOT / "results/g2/cells/*_m0.05.json")))]
    rows = evaluate.evaluate_batch([d["spec"] for d in cells], nu=0.3, keep_bands=True, **atlas.SEARCH_TIER)
    model = atlas.error_model()
    claims = []
    for d, row in zip(cells, rows):
        sp = d["spec"]
        c = cls[(sp["kind"], json.dumps(sp["params"], sort_keys=True))]
        err = atlas.err_for(sp, model)
        s = {case: atlas.slacks(row, d["targets"], err, case) for case in ("nominal", "pess", "opt")}
        for t in c["targets"]:
            k = t["key"]
            sn, sp_, so = s["nominal"][k], s["pess"][k], s["opt"][k]
            search = "pass" if sp_ > 0 else ("fail" if so < 0 else "borderline")
            claims.append(dict(kind=sp["kind"], params=sp["params"], key=k, truth=t["truth"], checker=t["verdict"],
                               slack_nominal=sn, slack_pess=sp_, slack_opt=so, search_nominal="pass" if sn > 0
                               else "fail", search_corrected=search))
    tab = collections.Counter((x["truth"], x["search_corrected"], x["checker"]) for x in claims)
    nom = collections.Counter((x["truth"], x["search_nominal"], x["checker"]) for x in claims)
    summary = dict(
        n_cells=len(cells), n_claims=len(claims),
        corrected_vs_checker=[dict(truth=a, search=b, checker=c, n=n) for (a, b, c), n in sorted(tab.items())],
        nominal_vs_checker=[dict(truth=a, search=b, checker=c, n=n) for (a, b, c), n in sorted(nom.items())],
        false_claims_passed_nominal=sum(x["truth"] == "false" and x["search_nominal"] == "pass" for x in claims),
        false_claims_passed_corrected=sum(x["truth"] == "false" and x["search_corrected"] == "pass" for x in claims),
        true_claims_borderline_corrected=sum(x["truth"] == "true" and x["search_corrected"] == "borderline"
                                             for x in claims),
        borderline_certified=sum(x["search_corrected"] == "borderline" and x["checker"] == "certified"
                                 for x in claims),
        caveat="error model fitted on these 50 cells plus 23 others (safety factor 1.25): in-sample for the search tier",
        seconds=round(time.perf_counter() - t0, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "checker_decision_value.json").write_text(json.dumps(dict(summary=summary, claims=claims), indent=1,
                                                                default=float))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

