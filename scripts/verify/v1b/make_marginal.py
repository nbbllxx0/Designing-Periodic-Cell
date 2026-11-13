"""V1b: marginal claims from the pass-1 amm certificates, by the rule fixed in results/verification/v1b/NOTES.md
section 0.6 (written before any comparison):
  static min target on Q:  t = L - 0.01 (ext - L);  density_max: t = U + 0.01 (U - ext);
  gap: f_lo = s_lo + 0.01 (s_hi - s_lo), f_hi = s_hi - 0.01 (s_hi - s_lo).
Only the target keys of the nominal claim are pressed (static keys of the nominal targets; gap if nominal has one).
    make_marginal.py   -> results/verification/v1b/marginal_claims.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v1b"
CELLS = ("tpms_schwarzp_sheet_d0.2895_nu0.342", "strut_bcc_R0.27_r0.06_nu0.342", "thin_sl_c0.357_w0.109_nu0.3")
KEYS = {"E100_min": "E100", "G_min": "G", "bulk_min": "bulk", "density_max": "density"}


def main():
    cells = {c["id"]: c for c in json.loads((OUT / "cells.json").read_text(encoding="utf-8"))["cells"]}
    claims = {}
    for cid in CELLS:
        cert = json.loads((OUT / f"{cid}_amm.json").read_text(encoding="utf-8"))
        q = cert["blocks"]["static"]["convergence"]["quantities"]
        nom = cells[cid]["targets"]
        t, why = {}, {}
        for key, val in nom.items():
            if key in KEYS:
                b = q[KEYS[key]]
                if key.endswith("_min"):
                    t[key] = b["lower"] - 0.01 * (b["extrapolated"] - b["lower"])
                else:
                    t[key] = b["upper"] + 0.01 * (b["upper"] - b["extrapolated"])
                why[key] = dict(nominal=val, lower=b["lower"], ext=b["extrapolated"], upper=b["upper"])
            elif key == "gap":
                s_lo, s_hi = cert["blocks"]["bloch"]["convergence"]["safe_interval"]
                w = s_hi - s_lo
                t["gap"] = {"f_lo": s_lo + 0.01 * w, "f_hi": s_hi - 0.01 * w}
                why["gap"] = dict(nominal=val, safe_interval=[s_lo, s_hi])
        claims[cid] = dict(targets=t, derived_from=why, pass1_verdict=cert["verdict"])
    (OUT / "marginal_claims.json").write_text(json.dumps(dict(rule="NOTES.md 0.6", claims=claims), indent=1),
                                              encoding="utf-8")
    print(json.dumps(claims, indent=1))


if __name__ == "__main__":
    main()
