"""G2 fix, gap side: gap edges at grid phases 0, 0.25, 0.5 for n = 20, 30, 40, at the k-points the certificate
kept (results/g2/rerun_v3/*.json, edge_k_kept), for the cells whose counts pass. Tests whether phase means of the
edges converge regularly (as the static phase means do). Output: results/g2/gap_phase_edges.json."""
import glob, json
import numpy as np
import amm  # noqa: F401
from amm import bloch, certify

out = {}
for p in sorted(glob.glob("results/g2/rerun_v3/*.json")):
    r = json.load(open(p))
    b = r.get("bloch")
    if not (b and b.get("convergence")):
        continue
    gap = r["targets"]["gap"]
    ks = {s: [np.pi * np.array(k) for k in b["edge_k_kept"][s]] for s in ("lo", "hi")}
    rows = {}
    for n in (20, 30, 40):
        for ph in (0.0, 0.25, 0.5):
            m, _ = certify._mesh(r["spec"], n, 0.3, phase=ph)
            ic = bloch.InertiaCounter(m)
            lo = max(ic.edge(k, gap["f_lo"], "below") for k in ks["lo"])
            hi = min(ic.edge(k, gap["f_hi"], "above") for k in ks["hi"])
            ic.free()
            rows[f"{n}@{ph}"] = [lo, hi]
            print(json.dumps(dict(kind=r["spec"]["kind"], params=r["spec"]["params"], key=f"{n}@{ph}", e=[lo, hi])), flush=True)
    out[certify.spec_hash(r["spec"])] = dict(spec=r["spec"], target=gap, rows=rows)
    json.dump(out, open("results/g2/gap_phase_edges.json", "w"), indent=1)
