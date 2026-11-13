"""V15 (2026-11-09): finer Bloch block for the two engineering filters (PA12 sphere-ligament, 316L cube-bars), which
the released rules of amm 0.2.0 leave undetermined (results/verification/v14/engineering.json): PA12 by an upper edge
that drifts toward the claim without an admissible order at n = 20/30/40, 316L by bars of 0.06 a spanning 2.4 voxels
at n = 40 (< FEATURE_MIN_VOXELS = 3).

The gap block is rerun with the released checker at counted resolutions n = 30 and 40, edge-only resolution n = 60 and
grid phases 0.25 and 0.5 at n = 40 (the guard then fits the edge order on 30/40/60; the 316L bars span 3.6 voxels at
n = 60). Everything else is the default of amm.certify.bloch_block. The static block is not rerun: the stored static
verdicts of the v6 certificates are combined with the new gap verdict.

Cost (timing probe 2026-11-09, single solves at n = 20-60 calibrated on the stored certificates): about 21-26 min
(PA12) and 48-60 min (316L) of CPU wall time; the GPU is used only by the n = 10 adversarial search. No LLM.
Approved by the author 2026-11-09 ("Run both").

    python scripts/experiments/v15_filter_fine_bloch.py
Output: results/verification/v15/filters.json (one entry per cell, written as each finishes).
"""
import json
import time
from pathlib import Path

from amm import certify

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "verification" / "v15"
CERTS = {
    "PA12": "results/verification/v6/case2/session_PA12/certificates/e5519f4fdbef64db_e212dc39bc22b626.json",
    "316L": "results/verification/v6/case2/session_316L/certificates/f1d00ed043a926f1_0dc7c12bea6f73f4.json",
}
RES_BLOCH, EDGE_RES = (30, 40), (60,)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"settings": dict(res_bloch=list(RES_BLOCH), edge_res=list(EDGE_RES), bloch_phases=list(certify.BLOCH_PHASES),
                            feature_min_voxels=certify.FEATURE_MIN_VOXELS, checker=certify.checker_hash()),
           "cells": {}}
    for name, rel in CERTS.items():
        c = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        t0 = time.perf_counter()
        g = certify.bloch_block(c["spec"], c["targets"]["gap"], nu=c["solver"]["nu"], res_bloch=RES_BLOCH,
                                edge_res=EDGE_RES)
        secs = time.perf_counter() - t0
        static_v = c["blocks"]["static"]["verdict"]["verdict"]
        gap_v = g["verdict"]["verdict"]
        overall = gap_v if static_v == "certified" else ("refuted" if "refuted" in (static_v, gap_v) else "undetermined")
        out["cells"][name] = dict(source=rel, spec=c["spec"], nu=c["solver"]["nu"], gap_target=c["targets"]["gap"],
                                  static_verdict=static_v, gap_verdict=gap_v, gap_reason=g["verdict"].get("reason"),
                                  overall=overall, seconds=round(secs, 1), bloch=g)
        (OUT / "filters.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
        print(name, gap_v, g["verdict"].get("reason"), f"{secs:.0f} s", flush=True)


if __name__ == "__main__":
    main()
