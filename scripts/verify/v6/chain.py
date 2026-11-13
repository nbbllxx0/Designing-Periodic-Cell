"""Case 1 finite-chain transmission (NOTES.md 1.7): 6 cells along z, periodic in x and y (k_perp = 0), driven bonded
plate at z = 0, free face at z = 6a, hysteretic loss factor 0.01. CPU only (PARDISO).

    python scripts/verify/v6/chain.py <label> <session_dir> <n>
Writes results/verification/v6/case1/chain_<label>_n<n>.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

import finite_fe as ff
from amm import units

V6 = Path(__file__).resolve().parents[3] / "results" / "verification" / "v6"
ETA, NZ = 0.01, 6
BAND_HZ = (11500.0, 14950.0)
A_M = 0.020


def main(label: str, session_dir: str, n: int) -> int:
    t0 = time.perf_counter()
    sd = Path(session_dir)
    s = json.loads((sd / "summary.json").read_text(encoding="utf-8"))
    d = s["released"]
    c = next(x for x in s["certify"] if x["design"] == d)
    h = c["result"]["spec_hash"]
    cert = json.loads(sorted((sd / "certificates").glob(f"{h}_*.json"))[-1].read_text(encoding="utf-8"))
    spec = cert["spec"]
    mat = units.MATERIALS[s["config"]["material"]]
    hz_per = units.c_t(mat) / A_M
    f_band = np.linspace(BAND_HZ[0], BAND_HZ[1], 41) / hz_per
    f_fig = np.linspace(0.01, 1.5 * BAND_HZ[1] / hz_per, 120)
    fs = np.concatenate([f_band, f_fig])
    cov, sub, info = ff.cell_geometry(spec, n)
    mesh = ff.TiledMesh(cov, sub, tiles=(1, 1, NZ), periodic=(True, True, False), nu=mat["nu"])
    ch = ff.HarmonicChain(mesh, eta=ETA)
    print(f"{label} n={n}: ne {mesh.ne}, free dof {ch.nf}, build {mesh.build_s} s", flush=True)
    r = ch.solve(fs, drives=(2, 0), log=lambda m: print(m, flush=True))
    out = dict(label=label, design=d, spec=spec, n=n, nz=NZ, material=s["config"]["material"],
               nu=mat["nu"], cell_size_m=A_M, hz_per_f_star=hz_per, band_Hz=list(BAND_HZ),
               n_band=len(f_band), density=mesh.density, boundary="periodic x, y (k_perp = 0); z: driven bonded "
               "plate at 0, free at 6a", transmission="|area-weighted mean output-face displacement along the drive| / U0",
               **r)
    for dk, name in (("2", "longitudinal"), ("0", "shear_x")):
        T = np.array(r["T"][dk])
        dB = 20 * np.log10(np.maximum(T, 1e-300))
        out.setdefault("band_metrics", {})[name] = dict(
            mean_dB=float(dB[:len(f_band)].mean()), max_dB=float(dB[:len(f_band)].max()),
            min_dB=float(dB[:len(f_band)].min()))
    out["seconds"] = round(time.perf_counter() - t0, 1)
    (V6 / "case1" / f"chain_{label}_n{n}.json").write_text(json.dumps(out, default=float), encoding="utf-8")
    print(json.dumps(out["band_metrics"], indent=1), f"total {out['seconds']} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], int(sys.argv[3])))
