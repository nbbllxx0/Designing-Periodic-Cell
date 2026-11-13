"""V11 (audit round 1, 2026-11-08): rerun the current gap guard on its calibration cell.

Lucklum & Vellekoop (2018) ball 0.79a / beam 0.05a (sphere_ligaments c = 0.395, w = 0.05), nu = 0.35 (derived).
Runs amm.certify.bloch_block (the shipped gap block: counts at n = 20, 30; edges at n = 40; grid phases 0.25, 0.5 at
n = 30; adversarial k from the coarse n = 10 search) on the two claims of the paper's Section 5.2:
  interior  fa/cl 0.055-0.46   and   near-edge  fa/cl 0.055-0.478,
converted with f* = (c_l/c_t) fa/c_l. Records the verdict, safe interval, fitted orders and multipliers.
    python scripts/experiments/v11_lucklum_guard.py
"""
import json, time
from pathlib import Path
import numpy as np
from amm import certify

ROOT = Path(__file__).resolve().parents[2]
NU = 0.35
R = float(np.sqrt(2 * (1 - NU) / (1 - 2 * NU)))  # c_l / c_t
SPEC = dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.395, w=0.05))
CLAIMS = {"interior": (0.055, 0.46), "near_edge": (0.055, 0.478)}

if __name__ == "__main__":
    out = dict(spec=SPEC, nu=NU, cl_over_ct=R, checker=certify.checker_hash(), runs={})
    for name, (lo, hi) in CLAIMS.items():
        t = time.perf_counter()
        g = certify.bloch_block(SPEC, dict(f_lo=lo * R, f_hi=hi * R), nu=NU)
        g = json.loads(json.dumps(g, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
        g["seconds_total"] = round(time.perf_counter() - t, 1)
        g["claim_fa_over_cl"] = [lo, hi]
        c = g.get("convergence", {})
        if c.get("safe_interval"):
            g["safe_interval_fa_over_cl"] = [None if x is None else x / R for x in c["safe_interval"]]
        out["runs"][name] = g
        print(json.dumps(dict(claim=name, passed=g.get("passed"), verdict=g.get("verdict"),
                              safe_fa_over_cl=g.get("safe_interval_fa_over_cl"),
                              lo=c.get("lower_edge"), hi=c.get("upper_edge"), s=g["seconds_total"]), default=str), flush=True)
        (ROOT / "results/verification/v11/lucklum_current_guard.json").write_text(json.dumps(out, indent=1, default=str))
    (ROOT / "results/verification/v11/lucklum_current_guard.json").write_text(json.dumps(out, indent=1))
