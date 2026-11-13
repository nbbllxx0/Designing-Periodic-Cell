"""V22 (2026-11-10): sensitivity of the released verdicts to two rule alternatives raised by confirm round 3
(theory reviewer #2, #3). The released checker (f99ce2b2f65d7630) is NOT changed: the held-out test (V21) validates it
as released. Each alternative is applied to the stored solves and the changed verdicts are counted.

  (a) gap order cap 1 instead of 2   (amm.bloch.P_MAX patched to 1.0 in this process only; rescore_bloch)
  (b) static drift rule: a quantity on the phase-noise branch whose phase means move monotonically toward a target
      (decreasing for a minimum, increasing for a maximum) is treated as unconverged for that target, as the gap
      guard already does for edges.

Sets: the 85 search-benchmark certificates (results/verification/v3/certs), the agent-experiment witness
certificates (bench/v1/work), the engineering certificates (v6, v11), the twelve gaps and comparison edges
(v12_gap_guard_audit.cases), the finer filter checks (v15/filters.json, v16/recheck_316L.json), the V21 held-out
certificates, and, for (b), the 1,500 near-threshold static claims on the 50 cells (results/g2/rerun_v3).
No solves; CPU seconds; no LLM.   python scripts/experiments/v22_rule_sensitivity.py
Output: results/verification/v22/sensitivity.json
"""
import collections
import copy
import glob
import json
import sys
from pathlib import Path

from amm import bloch, certify

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v22"
sys.path.insert(0, str(ROOT / "scripts/experiments"))


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def cert_files():
    sets = {
        "benchmark": [f for f in glob.glob(str(ROOT / "results/verification/v3/certs/*.json")) if not f.endswith(".summary.json")],
        "witnesses": glob.glob(str(ROOT / "bench/v1/work/**/*.json"), recursive=True),
        "engineering": sum((glob.glob(str(ROOT / p)) for p in (
            "results/verification/v6/case1/session_*/certificates/*.json",
            "results/verification/v6/case2/session_*/certificates/*.json",
            "results/verification/v11/robust_mount/session_*/certificates/*.json")), []),
        "heldout": glob.glob(str(ROOT / "results/verification/v21_heldout/certs/*.json")),
    }
    out = {}
    for k, fs in sets.items():
        cs = []
        for f in sorted(fs):
            try:
                c = load(f)
            except Exception:
                continue
            if isinstance(c, dict) and "blocks" in c and "spec" in c:
                cs.append((Path(f).name, c))
        out[k] = cs
    return out


def drift_variant_static(block, targets):
    """Static verdict with rule (b) applied to the stored guard bounds."""
    conv = (block or {}).get("convergence")
    if not conv or not conv.get("quantities"):
        return None
    q = copy.deepcopy(conv["quantities"])
    flagged = []
    for key, (name, kind) in certify.STATIC_KEYS.items():
        if key not in targets or name not in q:
            continue
        b = q[name]
        m = b.get("means")
        if b.get("mode") != "noise" or not m or len(m) < 3:
            continue
        d12, d23 = m[1] - m[0], m[2] - m[1]
        toward = (d12 < 0 and d23 < 0) if kind == "min" else (d12 > 0 and d23 > 0)
        if toward:
            b["converged"] = False
            flagged.append(key)
    v = certify.static_verdict(q, targets, bool(block.get("numerics_ok", True)))
    return v, flagged


def main():
    res = {}
    certs = cert_files()
    # (a) gap order cap 1 on full certificates
    a = {}
    for name, cs in certs.items():
        changed, n = [], 0
        for fn, c in cs:
            if "bloch" not in c["blocks"]:
                continue
            n += 1
            bloch.P_MAX = 2.0
            base = certify.rescore_certificate(c)["verdict"]
            bloch.P_MAX = 1.0
            alt = certify.rescore_certificate(c)["verdict"]
            bloch.P_MAX = 2.0
            if alt != base:
                changed.append(dict(cert=fn, base=base, cap1=alt))
        a[name] = dict(n_with_gap=n, changed=changed)
    # (a) on the twelve gaps and comparison edges (safe interval and pass/fail of the stored edges)
    from v12_gap_guard_audit import cases
    g12 = []
    for cs in cases():
        edges = {int(k): tuple(v) for k, v in cs["edges"].items()}
        out = {}
        for cap in (2.0, 1.0):
            bloch.P_MAX = cap
            r = bloch.gap_convergence(edges, cs["claim"][0], cs["claim"][1], phase_edges=cs.get("phase"))
            out[cap] = dict(passed=bool(r["passed"]), safe=r.get("safe_interval"))
        bloch.P_MAX = 2.0
        g12.append(dict(case=cs["case"], src=cs["src"], cap2=out[2.0], cap1=out[1.0],
                        changed=out[2.0]["passed"] != out[1.0]["passed"]))
    a["twelve_gaps_and_comparisons"] = dict(n=len(g12), changed=[x for x in g12 if x["changed"]], rows=g12)
    # (a) finer filter checks
    fil = []
    try:
        v15 = load(ROOT / "results/verification/v15/filters.json")["cells"]
        for key, cell in v15.items():
            rep = cell["bloch"]
            r = {}
            for cap in (2.0, 1.0):
                bloch.P_MAX = cap
                g = certify.rescore_bloch(rep, cell["spec"])
                r[cap] = dict(verdict=g["verdict"]["verdict"], safe=(g.get("convergence") or {}).get("safe_interval"))
            bloch.P_MAX = 2.0
            fil.append(dict(filter=key, cap2=r[2.0], cap1=r[1.0], changed=r[2.0]["verdict"] != r[1.0]["verdict"]))
    except Exception as e:
        fil.append(dict(error=repr(e)))
    a["finer_filter_checks"] = fil
    res["gap_order_cap_1"] = a

    # (b) static drift rule on full certificates
    b = {}
    for name, cs in certs.items():
        changed, n = [], 0
        for fn, c in cs:
            base = certify.rescore_certificate(c)
            if "static" not in c["blocks"]:
                continue
            n += 1
            r = drift_variant_static(c["blocks"]["static"], c.get("targets") or {})
            if r is None:
                continue
            v, flagged = r
            if base["verdict"] == "certified" and v["verdict"] != "certified":
                changed.append(dict(cert=fn, base=base["verdict"], drift_rule=v["verdict"], flagged=flagged))
        b[name] = dict(n=n, changed=changed)
    # (b) on the 1,500 near-threshold claims (as v13: claims on the reference bracket of each cell)
    truth = {(r["kind"], json.dumps(r["params"], sort_keys=True)): r
             for r in load(ROOT / "results/g2/classification_v3.json")}
    STATIC = {"E100_min": ("E100", "min"), "G_min": ("G", "min"), "density_max": ("density", "max")}
    cnt = collections.Counter()
    for f in sorted(glob.glob(str(ROOT / "results/g2/rerun_v3/*.json"))):
        r3 = load(f)
        sp = r3["spec"]
        t = truth.get((sp["kind"], json.dumps(sp["params"], sort_keys=True)))
        if t is None:
            continue
        st = r3["static"]
        for key, (q, kind) in STATIC.items():
            cl = t["claims"].get(key)
            if cl is None or cl.get("bracket") is None:
                continue
            lo, hi = cl["bracket"]
            for d in (0.005, 0.01, 0.02, 0.03, 0.05):
                for tr in ("true", "false"):
                    tgt = (lo * (1 - d) if tr == "true" else hi * (1 + d)) if kind == "min" else \
                          (hi * (1 + d) if tr == "true" else lo * (1 - d))
                    conv = st.get("convergence")
                    base = certify.static_verdict(conv, {key: tgt}, bool(st.get("numerics_ok")))["targets"][key]
                    blk = dict(convergence=dict(quantities=conv) if conv else None, numerics_ok=st.get("numerics_ok"))
                    rv = drift_variant_static(blk, {key: tgt})
                    alt = rv[0]["targets"][key] if rv else base
                    cnt[(tr, base, alt)] += 1
    b["near_threshold_1500"] = {f"{k[0]}: {k[1]} -> {k[2]}": v for k, v in sorted(cnt.items())}
    res["static_drift_rule"] = b
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sensitivity.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    short = {
        "cap1": {k: (len(v["changed"]) if isinstance(v, dict) and "changed" in v else v) for k, v in a.items() if k != "finer_filter_checks"},
        "cap1_filters": [(x.get("filter"), x.get("changed"), x.get("cap1")) for x in fil],
        "drift": {k: (len(v["changed"]), v["n"]) for k, v in b.items() if k != "near_threshold_1500"},
        "drift_1500": b["near_threshold_1500"],
    }
    print(json.dumps(short, indent=1, default=float))


if __name__ == "__main__":
    main()
