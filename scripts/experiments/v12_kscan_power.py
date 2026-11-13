"""V12 (audit-loop round 2, 2026-11-09): power of the dense wave-vector control (theory reviewer #4).

The V11 scan counted modes only at the claim endpoints, which sit well inside the safe intervals. This scan asks
how far the 37 sampled wave vectors of a certificate miss the band extrema at equal resolution, and whether any
dense-grid mode at n = 20 enters the guarded safe interval.

For the twelve certified gaps, on the same 1,771-point wedge grid (step pi/20, faces and edges included), n = 20,
grid phase 0: count eigenvalues below lo20 (1 + 1e-6) and hi20 (1 - 1e-6), where lo20 / hi20 are the certificate's
n = 20 edge estimates over its 37 sampled k (max of band j, min of band j+1). A count below the band index at
lo20 means band j exceeds lo20 at that k; a count above it at hi20 means band j+1 lies below hi20. At such points
the band value is solved (shift-invert Lanczos) and compared with the guarded safe edge (safe_lo >= lo20 and
safe_hi <= hi20 by construction, so a dense-grid band beyond a safe edge is a sampling miss at this resolution).

    python scripts/experiments/v12_kscan_power.py [--steps 20] [--n 20] [--only CASE]
Writes results/verification/v12/kscan_power_n20_S20.json. CPU only (PARDISO), no LLM.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

import amm  # noqa: F401
from amm import bloch
from amm.certify import _mesh

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/experiments"))
from v11_gap_kscan import cases, wedge  # noqa: E402

OUT = ROOT / "results/verification/v12"


def n20_edges_and_safe():
    rows = json.loads((OUT / "gap_guard_audit.json").read_text())
    safe = {r["case"]: r["cap2"]["safe"] for r in rows}
    edges = {}
    ver = ROOT / "results/verification"
    for f in (ver / "dolfinx").glob("*.json"):
        if f.name.startswith("summary"):
            continue
        d = json.loads(f.read_text())
        if "amm_edges" in d:
            edges[d["case"]] = d["amm_edges"]["20"]
    g = json.loads((ver / "v1b/summary.json").read_text())["thin_sl_c0.357_w0.109_nu0.3"]["gap"]
    edges["thin_sl_c0.357_w0.109_nu0.3"] = g["amm_edges"]["20"]
    for c in cases():
        if c.get("cert"):
            b = json.loads((ver / c["cert"]).read_text())["blocks"]["bloch"]["convergence"]
            edges[c["case"]] = b["edges"]["20"]
    return edges, safe


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--only", default=None)
    ap.add_argument("--resume", action="store_true", help="keep rows already in the output file, run the rest")
    a = ap.parse_args()
    edges, safe = n20_edges_and_safe()
    ks = wedge(a.steps)
    tag = f"_{a.only}" if a.only else ""
    out_f = OUT / f"kscan_power_n{a.n}_S{a.steps}{tag}.json"
    rows = json.loads(out_f.read_text()) if a.resume and out_f.exists() else []
    done = {r["case"] for r in rows}
    for c in cases():
        if (a.only and c["case"] != a.only) or c["case"] in done:
            continue
        lo20, hi20 = edges[c["case"]]
        s_lo, s_hi = safe[c["case"]]
        m, _ = _mesh(c["spec"], a.n, c["nu"])
        ic = bloch.InertiaCounter(m)
        nb = c["below_band"]
        if nb is None:  # V1b case: band index from the count at Gamma, as in v11_gap_kscan.py
            nb = ic.counts(np.zeros(3), [c["claim"][0]])[0]["below"]
        t0 = time.perf_counter()
        f_a, f_b = lo20 * (1 + 1e-6), hi20 * (1 - 1e-6)
        miss_lo, miss_hi, odd = [], [], 0
        for k in ks:
            ca, cb = ic.counts(k, [f_a, f_b])
            odd += ca["odd"] + cb["odd"] + ca["perturbed"] + cb["perturbed"]
            if ca["below"] < nb:  # band j above lo20 here
                v = ic.edge(k, c["claim"][0], "below")
                miss_lo.append(dict(k_over_pi=np.round(k / np.pi, 4).tolist(), band_j=v))
            if cb["below"] > nb:  # band j+1 below hi20 here
                v = ic.edge(k, c["claim"][1], "above")
                miss_hi.append(dict(k_over_pi=np.round(k / np.pi, 4).tolist(), band_j1=v))
        ic.free()
        top = max([x["band_j"] for x in miss_lo if x["band_j"] is not None], default=None)
        bot = min([x["band_j1"] for x in miss_hi if x["band_j1"] is not None], default=None)
        row = dict(case=c["case"], src=c["src"], n=a.n, steps=a.steps, n_k=len(ks), below_band=nb,
                   claim=c["claim"], lo20_37pt=lo20, hi20_37pt=hi20, safe=[s_lo, s_hi],
                   n_miss_lo=len(miss_lo), n_miss_hi=len(miss_hi),
                   dense_max_band_j=top, dense_min_band_j1=bot,
                   excess_lo_pct=(100 * (top - lo20) / lo20) if top else 0.0,
                   excess_hi_pct=(100 * (hi20 - bot) / hi20) if bot else 0.0,
                   beyond_safe_lo=bool(top is not None and top > s_lo),
                   beyond_safe_hi=bool(bot is not None and bot < s_hi),
                   miss_lo=miss_lo[:20], miss_hi=miss_hi[:20], numerical_flags=int(odd),
                   seconds=round(time.perf_counter() - t0, 1))
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("case", "n_miss_lo", "n_miss_hi", "excess_lo_pct", "excess_hi_pct",
                                               "beyond_safe_lo", "beyond_safe_hi", "numerical_flags", "seconds")}),
              flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        out_f.write_text(json.dumps(rows, indent=1))  # after every case, so a later failure keeps finished rows
