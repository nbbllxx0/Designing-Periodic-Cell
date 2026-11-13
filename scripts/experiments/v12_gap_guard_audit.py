"""V12 (audit-loop round 2, 2026-11-09): re-evaluate the gap guard of every certified gap from its stored edges.

No new solves. For the twelve certified gaps of the paper (eight DOLFINx-comparison cells, the extra quadratic
finite-cell resonator, three engineering designs), read the stored edge sequence at n = 20, 30, 40 and the
phase edges at n = 30, then report per edge:
  * the fitted convergence order p, the order used, the branch (order fit or phase-noise), the phase spread P,
    and whether the sequence drifts in one direction;
  * the safe interval and the verdict recomputed with the order cap lowered from 2 (current) to 1;
  * for the comparison cells, the distance between the safe edge and the reference edge, in % of the reference gap.
Reviewer items: theory #2 (order cap), #3 (noise branch), domain #9 (guard width).

    python scripts/experiments/v12_gap_guard_audit.py
Writes results/verification/v12/gap_guard_audit.json and prints a table. CPU only, seconds, no LLM.
"""
import json
from pathlib import Path

import amm  # noqa: F401
from amm import bloch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v12"
VER = ROOT / "results/verification"


def cases():
    out = []
    for f in sorted((VER / "dolfinx").glob("*.json")):
        if f.name.startswith("summary"):
            continue
        d = json.loads(f.read_text())
        if "amm_edges" not in d:
            continue
        ref = [d["ref_lo"].get("ext", d["ref_lo"].get("R")), d["ref_hi"].get("ext", d["ref_hi"].get("R"))]
        out.append(dict(case=d["case"], src="DOLFINx comparison", claim=d["claim"], edges=d["amm_edges"],
                        phase=d["amm_phase_edges"], safe_stored=d["amm_safe"], ref=ref))
    g = json.loads((VER / "v1b/summary.json").read_text())["thin_sl_c0.357_w0.109_nu0.3"]["gap"]
    out.append(dict(case="thin_sl_c0.357_w0.109_nu0.3", src="finite-cell comparison", claim=g["claim"],
                    edges=g["amm_edges"], phase=g.get("amm_phase_edges"), safe_stored=g["safe_interval"],
                    ref=[g["ref_lo"]["R"], g["ref_hi"]["R"]]))
    for name, cert in (("mount_PA12", "v6/case1/session_design/certificates/7db650ec44d50a1d_08d26401ae0bf0dc.json"),
                       ("filter_PA12", "v6/case2/session_PA12/certificates/e5519f4fdbef64db_e212dc39bc22b626.json"),
                       ("filter_316L", "v6/case2/session_316L/certificates/f1d00ed043a926f1_0dc7c12bea6f73f4.json")):
        b = json.loads((VER / cert).read_text())["blocks"]["bloch"]
        c = b["convergence"]
        out.append(dict(case=name, src="engineering certificate", claim=[b["claim"]["f_lo"], b["claim"]["f_hi"]],
                        edges=c["edges"], phase=c.get("phase_edges"), safe_stored=c["safe_interval"], ref=None))
    return out


def edge_report(ns, f, ph, side, p_max):
    old = bloch.P_MAX
    bloch.P_MAX = p_max
    try:
        safe, info = bloch._edge_guard(ns, f, ph, bloch.CONVERGENCE_SAFETY, side)
    finally:
        bloch.P_MAX = old
    d12, d23 = f[1] - f[0], f[2] - f[1]
    branch = "none (fails closed)" if safe is None else ("order fit" if info.get("p") is not None else "phase noise")
    return dict(safe=safe, p=info.get("p"), p_used=info.get("p_used"), branch=branch,
                phase_spread=info.get("phase_spread"), noise_flag=info.get("noise"),
                monotone=bool(d12 * d23 > 0), seq=f)


def main():
    rows = []
    for c in cases():
        items = sorted(((int(n), v) for n, v in c["edges"].items()))[-3:]
        ns = [n for n, _ in items]
        lo = [v[0] for _, v in items]
        hi = [v[1] for _, v in items]
        ph_lo = [e[0] for e in c["phase"]] if c["phase"] else []
        ph_hi = [e[1] for e in c["phase"]] if c["phase"] else []
        r = dict(case=c["case"], src=c["src"], claim=c["claim"], levels=ns, safe_stored=c["safe_stored"])
        for cap in (2.0, 1.0):
            L = edge_report(ns, lo, ph_lo, "lo", cap)
            H = edge_report(ns, hi, ph_hi, "hi", cap)
            ok = (L["safe"] is not None and H["safe"] is not None and L["safe"] < H["safe"]
                  and c["claim"][0] >= L["safe"] and c["claim"][1] <= H["safe"])
            r[f"cap{int(cap)}"] = dict(lo=L, hi=H, safe=[L["safe"], H["safe"]], certified=bool(ok))
        if c["ref"]:
            gap = c["ref"][1] - c["ref"][0]
            s = r["cap2"]["safe"]
            r["guard_width_pct_of_ref_gap"] = [100 * (s[0] - c["ref"][0]) / gap, 100 * (c["ref"][1] - s[1]) / gap]
            r["ref"] = c["ref"]
        rows.append(r)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gap_guard_audit.json").write_text(json.dumps(rows, indent=1))
    print(f"{'case':32s} {'p_lo':>6s} {'br_lo':12s} {'P_lo%':>6s} {'p_hi':>6s} {'br_hi':12s} {'P_hi%':>6s} "
          f"{'cap2':>5s} {'cap1':>5s} {'w_lo%':>6s} {'w_hi%':>6s}")
    for r in rows:
        L, H = r["cap2"]["lo"], r["cap2"]["hi"]
        rel = lambda e: 100 * (e["phase_spread"] or 0) / e["seq"][-1]
        p = lambda x: f"{x:.2f}" if x is not None else "-"
        w = r.get("guard_width_pct_of_ref_gap", [None, None])
        print(f"{r['case']:32s} {p(L['p']):>6s} {L['branch'][:12]:12s} {rel(L):6.2f} {p(H['p']):>6s} "
              f"{H['branch'][:12]:12s} {rel(H):6.2f} {str(r['cap2']['certified'])[0]:>5s} "
              f"{str(r['cap1']['certified'])[0]:>5s} {p(w[0]):>6s} {p(w[1]):>6s}")
    print("stored vs recomputed safe (cap 2) max abs diff:",
          max(abs(a - b) for r in rows for a, b in zip(r["safe_stored"], r["cap2"]["safe"]) if a is not None and b is not None))


if __name__ == "__main__":
    main()
