"""G2 analysis: false alarms on honest claims, the margin each cell needs, and overshoot (soundness) checks.

Per cell (results/g2/cells/*.json):
  required margin  m* = smallest claim margin the certificate would accept, from the values it computed:
                   static  1 - min over the used pair / reference (for E100, G), density max / ref - 1;
                   gap     (safe_lo / lo_ref - 1) and (1 - safe_hi / hi_ref).
  overshoot        certified value beyond the reference (min over the pair > reference, or safe interval
                   outside the reference gap): a claim between the two would be accepted although false in the
                   converged limit. Must be <= 0 up to the reference's own uncertainty.
"""
import glob, json
import numpy as np

rows = []
for f in sorted(glob.glob("results/g2/cells/*_m0.05.json")):
    d = json.load(open(f))
    s, ref = d["cert"]["static"], d["static_ref"]["ext"]
    pair = [s["values"][str(n)] if str(n) in s["values"] else s["values"][n] for n in s["used_pair"]]
    r = dict(kind=d["spec"]["kind"], params=d["spec"]["params"], passed=d["cert"]["passed"],
             static_passed=s["passed"], used_pair=s["used_pair"])
    if all(p.get("E100") is not None for p in pair):
        for q in ("E100", "G"):
            lo = min(p[q] for p in pair)
            r[f"m_{q}"] = 1 - lo / ref[q]
            r[f"over_{q}"] = lo / ref[q] - 1 if lo > ref[q] else 0.0
        r["m_density"] = max(p["density"] for p in pair) / ref["density"] - 1
        r["ref_vs_n80_E100"] = ref["E100"] / d["static_ref"]["raw"]["80"]["E100"] - 1
    b = d["cert"].get("bloch")
    gr = d.get("gap_ref")
    if b is not None:
        r["bloch_passed"] = b["passed"]
        r["bloch_reason"] = b.get("reason")
        r["count_failures"] = {n: v["n_failures"] for n, v in b.get("counts", {}).items()}
        c = b.get("convergence")
        if c and gr and gr.get("open"):
            lo_ref, hi_ref = gr["ext"]
            sl, sh = c["safe_interval"]
            r.update(m_gap=max(sl / lo_ref - 1, 1 - sh / hi_ref), safe=[sl, sh], ref_gap=[lo_ref, hi_ref],
                     over_gap=max(lo_ref - sl, sh - hi_ref, 0.0) / (hi_ref - lo_ref))
    elif gr is not None:
        r["gap_ref_open"] = gr.get("open")
    rows.append(r)

n = len(rows)
fa = [r for r in rows if not r["passed"]]
print(f"cells {n}; certificate passed {n - len(fa)}; refused {len(fa)}")
for r in fa:
    print("  REFUSED", r["kind"], r["params"], {k: r.get(k) for k in ("static_passed", "bloch_passed", "bloch_reason",
                                                                       "count_failures", "m_E100", "m_G", "m_gap")})
for key in ("m_E100", "m_G", "m_density", "m_gap"):
    v = np.array([r[key] for r in rows if key in r])
    if len(v):
        print(f"{key}: n={len(v)} median {np.median(v):.4f} p90 {np.quantile(v, 0.9):.4f} max {v.max():.4f}")
for m in (0.01, 0.02, 0.03, 0.05, 0.10):
    ok = sum(all(r.get(k, -1) <= m for k in ("m_E100", "m_G", "m_density", "m_gap")) for r in rows)
    print(f"accepted at margin {m:.2f}: {ok}/{n} (predicted from the certificate's own values)")
for key in ("over_E100", "over_G", "over_gap"):
    v = [(r[key], r["kind"], r["params"]) for r in rows if r.get(key, 0) > 0]
    print(f"{key}: {len(v)} cells overshoot", sorted(v, key=lambda x: -x[0])[:5])
v = np.array([r["ref_vs_n80_E100"] for r in rows if "ref_vs_n80_E100" in r])
print(f"reference extrapolation vs n=80 (E100): median {np.median(v):+.4f}, range {v.min():+.4f} .. {v.max():+.4f}")
json.dump(rows, open("results/g2/summary.json", "w"), indent=1, default=float)
