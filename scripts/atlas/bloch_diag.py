"""Gap block only, for the gap designs of gate step 5 (gate.json), with the per-resolution failures and the
convergence guard printed. The first step-5 run did not save the full certificates.
Usage: bloch_diag.py -> results/atlas/certs/bloch_<hash>.json, summary on stdout."""
import json, os

import numpy as np

import amm  # noqa: F401
from amm import certify

g = json.load(open("results/atlas/gate.json"))
os.makedirs("results/atlas/certs", exist_ok=True)
for x in g.get("5_search_then_certify", []):
    if "gap" not in x["targets"] or x.get("bloch_passed"):
        continue
    r = certify.bloch_block(x["spec"], x["targets"]["gap"])
    json.dump(r, open(f"results/atlas/certs/bloch_{certify.spec_hash(x['spec'])}.json", "w"), indent=1,
              default=lambda o: o.tolist() if isinstance(o, np.ndarray) else float(o))
    print(json.dumps(dict(spec=x["spec"]["params"], gap=x["targets"]["gap"], passed=r.get("passed"),
                          reason=r.get("reason"), edge_failure=r.get("edge_failure"),
                          resolutions={n: dict(passed=v.get("passed"), n_failures=v.get("n_failures"), failures=(v.get("failures") or [])[:3])
                                       for n, v in r.get("resolutions", {}).items()},
                          convergence=r.get("convergence")), default=float), flush=True)
