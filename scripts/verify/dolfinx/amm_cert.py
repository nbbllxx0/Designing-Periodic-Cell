"""V1c host side: the Bloch (gap) block of an amm certificate for the TPMS case, from the FROZEN E4 code.

No stored certificate under the frozen checker exists for a TPMS gap; the G2 Schwarz P network cell (density 0.25,
nu 0.3; gap claim of results/g2/classification_v3.json) is the only TPMS gap reference in the project. This runs
certify.bloch_block (the certificate's gap block, unchanged defaults) under the shared solver lock and stores it in
certificate form. The static block is not run (the comparison concerns bands only).

Usage: python scripts/verify/dolfinx/amm_cert.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FROZEN = Path(r"C:\AI\AgenticMetamaterials_workspaces\v1c_frozen")
sys.path.insert(0, str(FROZEN))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from amm import certify, fem  # noqa: E402
from lock import GpuLock  # noqa: E402

assert Path(certify.__file__).resolve().is_relative_to(FROZEN)
SPEC = {"family": "tpms", "kind": "schwarz_p", "params": {"density": 0.25, "mode": "network"}}
GAP = {"f_lo": 0.4821542675645598, "f_hi": 0.787663739130882}
NU = 0.3
OUT = ROOT / "results/verification/dolfinx/amm/tpms_schwarzp_d0.25_nu0.3_bloch.json"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with GpuLock("V1c amm_cert (TPMS bloch block)"):
        t0 = time.perf_counter()
        g = certify.bloch_block(SPEC, GAP, nu=NU)
        sec = round(time.perf_counter() - t0, 1)
    cert = dict(spec=SPEC, spec_hash=certify.spec_hash(SPEC), targets=dict(gap=GAP),
                solver=dict(nu=NU, element=fem.ELEMENT, partial_voxels="finite-cell"), checker=certify.checker_hash(),
                blocks=dict(bloch=g), timing=dict(bloch=sec), verdict=g["verdict"]["verdict"],
                note="Bloch block only (certify.bloch_block, frozen E4 code); static block not run",
                pid=os.getpid())
    json.dump(cert, open(OUT, "w"), indent=1, default=float)
    print(OUT, cert["verdict"], sec, "s", g.get("convergence", {}).get("safe_interval"))


if __name__ == "__main__":
    main()
