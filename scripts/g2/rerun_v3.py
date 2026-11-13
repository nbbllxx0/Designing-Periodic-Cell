"""G2 re-run, third revision: the certificate after the G2 fixes, on the same 50 clean cells and claims.

  static  certify.static_block: grid phases 0, 1/8, 1/4, 3/8, 1/2 at every resolution, phase means with a fitted
          convergence order, ladder (32,48,64) -> (48,64,80) -> (64,80,96).
  bloch   certify.bloch_block: counts at n = 20, 30 on path + random interior + adversarial k (GPU pattern search,
          n = 10); edges at 20, 30, 40 and at phases 0.25, 0.5 of n = 30; order-fitted guard.
Reference data for classification (scripts/g2/classify_v3.py): the certificate's own solves (five phases at every
n of the rungs it tried) plus the n = 80 phase 0, 0.25, 0.5 (phase 0 only for TPMS) and n = 96 solves of the earlier
re-run (results/g2/static_rerun_phase/, `prior`), so no solve is repeated. (A first version re-solved n = 80 at five
phases for every cell; at 28 min per TPMS cell it was stopped after one cell, whose record keeps those rows.)
Output: results/g2/rerun_v3/<hash>.json (resumable), log on stdout.
Usage: rerun_v3.py [static|bloch|all] [shard i/N]
"""
import glob, json, os, sys, time
import amm  # noqa: F401
from amm import certify

OUT = "results/g2/rerun_v3"
os.makedirs(OUT, exist_ok=True)
what = sys.argv[1] if len(sys.argv) > 1 else "all"
shard, nshard = (int(x) for x in sys.argv[2].split("/")) if len(sys.argv) > 2 else (0, 1)
PH = (0.0,) + certify.STATIC_PHASES


def row_values(r):
    return {q: r.get(q) for q in certify.STATIC_QUANTITIES} | dict(numerics_ok=r.get("numerics_ok"))


cells = [json.load(open(f)) for f in sorted(glob.glob("results/g2/cells/*_m0.05.json"))]
cells.sort(key=lambda d: (d["spec"]["family"] != "tpms", d["spec"]["family"] == "resonator"))  # cheap first
for i, d in enumerate(cells):
    if i % nshard != shard:
        continue
    spec, targets = d["spec"], d["targets"]
    h = certify.spec_hash(spec)
    path = f"{OUT}/{h}.json"
    rec = json.load(open(path)) if os.path.exists(path) else dict(spec=spec, targets=targets)
    if what in ("static", "all") and "static" not in rec:
        t0 = time.perf_counter()
        cache = {}
        st = certify.static_block(spec, targets, cache=cache)
        rec["static"] = dict(passed=st["passed"], used=st["used"], ladder=st["ladder"],
                             checks_failed=st["checks_failed"], numerics_ok=st.get("numerics_ok"),
                             reason=st.get("reason"),
                             convergence={q: {k: v for k, v in c.items() if k != "values"}
                                          for q, c in (st.get("convergence") or {}).get("quantities", {}).items()})
        rec["rows"] = {(f"{k}@0.0" if isinstance(k, int) else f"{k[0]}@{k[1]}"): row_values(v)
                       for k, v in cache.items()}
        rec["static_seconds"] = round(time.perf_counter() - t0, 1)
        prior = f"results/g2/static_rerun_phase/{h}.json"
        if os.path.exists(prior):
            rec["prior"] = {k.replace("@0", "@0.0") if k.endswith("@0") else k: v
                            for k, v in json.load(open(prior))["reference"].items()}
        json.dump(rec, open(path, "w"), indent=1, default=float)
        print(json.dumps(dict(block="static", kind=spec["kind"], params=spec["params"], passed=st["passed"],
                              used=st["used"], fails=st["checks_failed"], s=rec["static_seconds"])), flush=True)
    if what in ("bloch", "all") and targets.get("gap") and "bloch" not in rec:
        t0 = time.perf_counter()
        g = certify.bloch_block(spec, targets["gap"])
        rec["bloch"] = g
        rec["bloch_seconds"] = round(time.perf_counter() - t0, 1)
        json.dump(rec, open(path, "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o))
        c = g.get("convergence") or {}
        print(json.dumps(dict(block="bloch", kind=spec["kind"], params=spec["params"], passed=g["passed"],
                              counts={n: r["n_failures"] for n, r in g.get("resolutions", {}).items()},
                              safe=c.get("safe_interval"), reason=g.get("reason") or g.get("edge_failure"),
                              s=rec["bloch_seconds"]), default=float), flush=True)
