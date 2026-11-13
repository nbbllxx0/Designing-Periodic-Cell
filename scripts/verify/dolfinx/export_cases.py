"""V1c host side, step 1: export the cases for the third-party (DOLFINx) Bloch comparison.

Uses the FROZEN E4 code only (results/bench/e4/snapshot/source.zip extracted to FROZEN below; checker
f2e482d81382b400); never the live amm/. Reads reference values from the stored certificates.

Per case writes, under results/verification/dolfinx/inputs/:
  <case>.json  spec, nu, claim, below_band, certificate edges / safe interval, and the k sets
               (path = kpath(4), interior = ibz_interior(10, 0), adversarial = the certificate's ks * pi; exactly
               the certificate's 37 points), plus paths of the occupancy files
and, in the workspace (large, regenerable): fcm_<case>_n<N>.npz with amm's cleaned coverage and sub-sample
occupancy at N in (10, 16, 20, 30, 40), i.e. exactly the arrays amm meshes (geometry.design_cell, phase 0).

Usage: python scripts/verify/dolfinx/export_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
FROZEN = Path(r"C:\AI\AgenticMetamaterials_workspaces\v1c_frozen")
WS_IN = FROZEN / "inputs"
OUT = ROOT / "results" / "verification" / "dolfinx" / "inputs"
sys.path.insert(0, str(FROZEN))
from amm import bloch, certify, geometry  # noqa: E402  (frozen copy)

assert certify.checker_hash() == "f2e482d81382b400", certify.checker_hash()
assert Path(certify.__file__).resolve().is_relative_to(FROZEN), certify.__file__

IND = "results/verification/indep/"
E4 = "results/bench/e4/jobs/"
CASES = [  # name, certificate, role
    ("cb_c0.6_w0.2_nu0.342", IND + "cube_bars_c0.6_w0.2_nu0.342_amm.json", "certified gap case"),
    ("cb_c0.8_w0.3_nu0.3", IND + "cube_bars_c0.8_w0.3_nu0.3_amm.json", "certified gap case"),
    ("cb_c0.5_w0.2_nu0.3", IND + "cube_bars_c0.5_w0.2_nu0.3_g2_amm.json", "certified gap case"),
    ("cb_c0.6_w0.3_nu0.3", IND + "cube_bars_c0.6_w0.3_nu0.3_g2_amm.json", "certified gap case"),
    ("cb_c0.7_w0.3_nu0.3", IND + "cube_bars_c0.7_w0.3_nu0.3_g2_amm.json", "certified gap case"),
    ("tpms_schwarzp_d0.25_nu0.3", "results/verification/dolfinx/amm/tpms_schwarzp_d0.25_nu0.3_bloch.json", "TPMS"),
    ("strut_bcc_R0.27_r0.06_nu0.342",
     E4 + "codex-C-r1-A15/session/certificates/feceec63a345ee84_8306e070463fa197.json", "strut"),
    ("thin_sl_c0.402_w0.061_nu0.3",
     E4 + "codex-C-r1-G10/session/certificates/40d98d0c519c50a5_f8934f3a9d393e14.json", "thin resonator"),
]
RES = (10, 16, 20, 30, 40)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    WS_IN.mkdir(parents=True, exist_ok=True)
    for name, cert_path, role in CASES:
        p = ROOT / cert_path
        if not p.exists():
            print("missing certificate (run amm_cert.py first):", p)
            continue
        cert = json.load(open(p))
        b = cert["blocks"]["bloch"]
        assert cert.get("checker") == "f2e482d81382b400", (name, cert.get("checker"))
        assert b["verdict"]["verdict"] == "certified", (name, b["verdict"])
        nu = cert["solver"]["nu"]
        spec = cert["spec"]
        ks_path, _ = bloch.kpath(4)
        ks_int = bloch.ibz_interior(10, 0)
        ks_adv = np.pi * np.asarray(b["adversarial"]["ks"], float).reshape(-1, 3)
        assert len(ks_path) + len(ks_int) + len(ks_adv) == b["n_k"], (name, b["n_k"])
        conv = b["convergence"]
        case = dict(name=name, role=role, certificate=cert_path, checker=cert["checker"], spec=spec, nu=nu,
                    element=cert["solver"]["element"], below_band=b["claim"]["below_band"],
                    claim=[b["claim"]["f_lo"], b["claim"]["f_hi"]],
                    amm=dict(edges=conv["edges"], phase_edges=conv.get("phase_edges"),
                             safe_interval=conv["safe_interval"], mode=conv["mode"],
                             lower_edge=conv.get("lower_edge"), upper_edge=conv.get("upper_edge"),
                             edge_k=conv.get("edge_search"), edge_k_kept=b.get("edge_k_kept"),
                             adversarial_search_edges=b["adversarial"].get("search_edges")),
                    ks=dict(path=ks_path.tolist(), interior=ks_int.tolist(), adversarial=ks_adv.tolist()),
                    geometry=None, fcm={})
        if spec["kind"] == "cube_bars":
            case["geometry"] = dict(kind="cube_bars", c=spec["params"]["c"], w=spec["params"]["w"])
        for n in RES:
            cov, sub, info = geometry.design_cell(spec, n)
            assert all(info["percolates"]) and info["removed_fraction"] <= 0.01, (name, n, info)
            f = WS_IN / f"fcm_{name}_n{n}.npz"
            np.savez_compressed(f, cov=cov, sub=sub)
            case["fcm"][str(n)] = "/inputs/" + f.name  # container path
            case.setdefault("fcm_info", {})[str(n)] = dict(density=info["density"], s=int(sub.shape[1]),
                                                           n_partial=int(((cov > 0) & (cov < 1 - 1e-12)).sum()),
                                                           n_cells=int((cov > 0).sum()))
        json.dump(case, open(OUT / f"{name}.json", "w"), indent=1)
        print(name, "nb", case["below_band"], "claim", np.round(case["claim"], 4), "safe",
              np.round(case["amm"]["safe_interval"], 4), {n: case["fcm_info"][n]["n_cells"] for n in case["fcm_info"]})


if __name__ == "__main__":
    main()
