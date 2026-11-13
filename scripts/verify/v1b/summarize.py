"""V1b: markdown tables (per-cell results, worst discrepancies, tallies) from results/verification/v1b/summary.json,
printed to stdout for NOTES.md and written to results/verification/v1b/tables.md.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v1b"


def pct(x, d=2):
    return "n/a" if x is None else f"{100 * x:+.{d}f} %"


def main():
    S = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    L = []
    L.append("### Static (Q2-FCM reference from the three finest levels; delta = (amm estimate - R)/R)\n")
    L.append("| cell | Q | R +- 2u | amm est. | delta | amm [lower, upper] | lower | upper | consistent | scikit-fem n16 (per.) | KUBC >= lower |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    tally = dict(sound=0, marginal=0, unsound=0)
    worst = []
    for cid, r in S.items():
        st = r.get("static")
        if not st:
            continue
        for q in ("E100", "G", "bulk", "density", "nu100"):
            e = st["quantities"][q]
            R, u = e["ref"]["R"], e["ref"]["u"]
            sk = e.get("skfem_delta")
            L.append(f"| {cid} | {q} | {R:.5g} +- {2 * u:.2g} | {e['amm_ext']:.5g} | {pct(e['delta'])} | "
                     f"[{e['amm_lower']:.5g}, {e['amm_upper']:.5g}] | {e['lower_status']} | {e['upper_status']} | "
                     f"{e['consistent']} | {pct(sk) if sk is not None else 'n/a'}"
                     f"{'' if e.get('skfem_agrees') is None else (' ok' if e['skfem_agrees'] else ' DIFF')} | "
                     f"{e.get('kubc_ge_amm_lower', 'n/a')} |")
            for s_ in (e["lower_status"], e["upper_status"]):
                tally[s_] += 1
            worst.append((abs(e["delta"]), cid, f"static {q}", e["delta"], e["consistent"]))
    L.append("")
    L.append("### Gap edges (Q2-FCM reference over the refinement k subset; amm safe interval from the certificate)\n")
    L.append("| cell | nb | Q2 levels | R_lo +- 2u | R_hi +- 2u | amm ext (lo, hi) | delta ext | safe [s_lo, s_hi] | lo | hi | conservatism (lo, hi) | k coverage (dlo, dhi) | extreme k set (lo, hi) | band-index mismatch | earlier reference (levels: lo, hi) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for cid, r in S.items():
        g = r.get("gap")
        if not g:
            continue
        rl, rh = g["ref_lo"], g["ref_hi"]
        kc = g["k_coverage"]
        L.append(f"| {cid} | {g['below_band']} | {rl['levels']} | {rl['R']:.5f} +- {2 * rl['u']:.1e} | "
                 f"{rh['R']:.5f} +- {2 * rh['u']:.1e} | ({g['amm_ext'][0]:.5f}, {g['amm_ext'][1]:.5f}) | "
                 f"({pct(g['delta_ext'][0])}, {pct(g['delta_ext'][1])}) | ({g['safe_interval'][0]:.5f}, "
                 f"{g['safe_interval'][1]:.5f}) | {g['lo_status']} | {g['hi_status']} | "
                 f"({pct(g['conservatism'][0], 1)}, {pct(g['conservatism'][1], 1)}) | "
                 f"({kc['delta_lo']:.1e}, {kc['delta_hi']:.1e}) | {g['extreme_k_finest']['lo']}, "
                 f"{g['extreme_k_finest']['hi']} | {len(g['band_index_mismatch'])} | "
                 + (f"{g['ref_prev']['levels']}: {g['ref_prev']['lo_status']}, {g['ref_prev']['hi_status']} |"
                    if g.get("ref_prev") else "- |"))
        for s_ in (g["lo_status"], g["hi_status"]):
            tally[s_] += 1
        for j, side in enumerate(("lo", "hi")):
            worst.append((abs(g["delta_ext"][j]), cid, f"gap {side} edge (extrapolated)", g["delta_ext"][j],
                          g["consistent_ext"][j]))
        px = [e for e in g.get("per_k_extrapolated") or [] if "lo" in e]
        for e in px:
            for side in ("lo", "hi"):
                worst.append((abs(e[side]["delta"]), cid, f"per-k {side} at {e['set']} {e['k']}", e[side]["delta"],
                              e[side]["consistent"]))
    L.append("")
    L.append("### Per-k (gap cells)\n")
    L.append("| cell | sampled: amm n20 - Q2 n1, lo (% , min..max) | hi | extrapolated per-k max abs delta (lo, hi) | consistent |")
    L.append("|---|---|---|---|---|")
    for cid, r in S.items():
        g = r.get("gap")
        if not g or not g.get("per_k_sampled"):
            continue
        rows = [e for e in g["per_k_sampled"]["rows"] if "d_lo_sampled" in e]
        lo = [e["d_lo_sampled"] / g["ref_lo"]["R"] for e in rows]
        hi = [e["d_hi_sampled"] / g["ref_hi"]["R"] for e in rows]
        px = [e for e in g.get("per_k_extrapolated") or [] if "lo" in e]
        L.append(f"| {cid} | {100 * min(lo):+.2f}..{100 * max(lo):+.2f} ({len(rows)} k) | {100 * min(hi):+.2f}..{100 * max(hi):+.2f} | "
                 f"({100 * max(abs(e['lo']['delta']) for e in px):.2f} %, {100 * max(abs(e['hi']['delta']) for e in px):.2f} %) | "
                 f"{sum(e['lo']['consistent'] and e['hi']['consistent'] for e in px)}/{len(px)} |" if px and rows else f"| {cid} | n/a | | | |")
    L.append("")
    L.append("### Claims (nominal and marginal)\n")
    L.append("| cell | claim | key | target | independent status | amm margin |")
    L.append("|---|---|---|---|---|---|")
    ctally = dict(agrees=0, inconclusive=0, disagrees=0)
    for cid, r in S.items():
        for c in (r.get("static") or {}).get("claims", []):
            L.append(f"| {cid} | {c['claim']} | {c['key']} | {c['target']:.6g} | {c['status']} | {pct(c['margin_rel'])} |")
            ctally[c["status"]] += 1
        for c in (r.get("gap") or {}).get("claims", []):
            L.append(f"| {cid} | {c['claim']} | gap | {c['f_lo']:.5f}-{c['f_hi']:.5f} | {c['status']} | "
                     f"lo {pct(c['margin_to_safe'][0])}, hi {pct(c['margin_to_safe'][1])} |")
            ctally[c["status"]] += 1
    L.append("")
    bands = [(cid, r["bands"]) for cid, r in S.items() if r.get("bands")]
    if bands:
        L.append("### Band comparison (no-gap cells; bands 4-15 at G, X, M, R + 4 interior k; 1-15 off Gamma)\n")
        L.append("| cell | max abs delta (extrapolated, all) | consistent | rows with mode crossing | max abs delta (no crossing) | consistent (no crossing) | finest levels amm n40 vs Q2 n3, rel range | sampled amm n20 vs Q2 n1, rel range |")
        L.append("|---|---|---|---|---|---|---|---|")
        for cid, b in bands:
            sv = [x for e in b["sampled"]["rows"] for x in e["rel"]]
            fr = b.get("finest_rel_range") or [None, None]
            L.append(f"| {cid} | {pct(b['max_abs_delta'])} | {b['n_consistent']}/{b['n_rows']} | {b.get('n_crossing')} | "
                     f"{pct(b.get('max_abs_delta_no_crossing'))} | {b.get('n_consistent_no_crossing')}/{b.get('n_rows_no_crossing')} | "
                     f"{pct(fr[0])}..{pct(fr[1])} | {pct(min(sv) if sv else None)}..{pct(max(sv) if sv else None)} |")
        L.append("")
    ib = [(cid, json.loads((OUT / f"{cid}_inertia_bands.json").read_text(encoding="utf-8")))
          for cid in S if (OUT / f"{cid}_inertia_bands.json").exists()]
    if ib:
        L.append("### Eigensolver-free band counts (PARDISO inertia at probe frequencies between clusters; deviation 8)\n")
        L.append("| cell | k checked | probes | Q2 Lanczos != inertia | amm-model Lanczos != inertia | count Q2 n3 != amm n40 |")
        L.append("|---|---|---|---|---|---|")
        for cid, d in ib:
            sm = {k: ([e for e in v if e["probe"] > 1e-3] if isinstance(v, list) else v)  # Gamma: probe between
                  for k, v in d["summary"].items()}                                       # split rigid modes
            mx = sm["q2_finest_vs_amm40_count_mismatch"]
            ks = "flagged: " + ", ".join(f"{r['set']}:{r['i']}" for r in d["rows"]) if d.get("flagged_only") else f"all {len(d['rows'])}"
            def lz(v):
                if not v:
                    return "0"
                by = {}
                for e in v:
                    by.setdefault(e["n"], []).append(e["lanczos"] - e["count"])
                return "; ".join(f"n{n}: {len(x)} probes, Lanczos {min(x):+d}..{max(x):+d} copies" for n, x in by.items())
            fq, fa = lz(sm["q2_lanczos_vs_inertia_mismatch"]), lz(sm["amm_lanczos_vs_inertia_mismatch"])
            fx = (f"{len(mx)} probes (amm fewer modes below the probe in {sum(e['amm'] < e['q2'] for e in mx)})"
                  if mx else "0")
            L.append(f"| {cid} | {ks} | {sm['n_probes']} | {fq} | {fa} | {fx} |")
        L.append("")
    worst.sort(reverse=True)
    seen, uniq = set(), []
    for w in worst:  # the same k (e.g. Gamma) appears in several k-sets: list it once
        key = (w[1], w[2].split(" at ")[0], w[2][w[2].find("["):] if " at " in w[2] else w[2], round(w[3], 6))
        if key not in seen:
            seen.add(key), uniq.append(w)
    worst = uniq
    L.append("### Worst two-sided discrepancies (|delta|)\n")
    L.append("| cell | quantity | delta | consistent within 2 sqrt(u^2 + e^2) |")
    L.append("|---|---|---|---|")
    for w in worst[:10]:
        L.append(f"| {w[1]} | {w[2]} | {pct(w[3])} | {w[4]} |")
    L.append("")
    L.append(f"Bound/edge statuses: {tally}. Claim statuses: {ctally}.")
    txt = "\n".join(L)
    (OUT / "tables.md").write_text(txt + "\n", encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
