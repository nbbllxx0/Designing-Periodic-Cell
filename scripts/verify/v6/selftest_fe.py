"""Self-tests of finite_fe.py on homogeneous solids with analytic answers (run before any V6 case run).
    python scripts/verify/v6/selftest_fe.py"""
import json, sys, time
from pathlib import Path
import numpy as np
import finite_fe as ff
from amm import fem, bloch

out = {}
nu = 0.39
# 1. uniaxial strain column (periodic x, y): k = M A / H, M = lambda + 2 mu (exact for hex8 on a uniform mesh)
lam = nu / ((1 + nu) * (1 - 2 * nu)); mu = 1 / (2 * (1 + nu)); Mmod = lam + 2 * mu
m = ff.TiledMesh(np.ones((4, 4, 4)), None, tiles=(1, 1, 3), periodic=(True, True, False), nu=nu, with_mass=False)
r = ff.plate_compression(m)
out["column_uniaxial_strain"] = dict(k=r["k"], exact=Mmod * 1 / 3, rel=r["k"] / (Mmod / 3) - 1, res=r["residual"])
# 2. free-sided block, frictionless would be E A/H; bonded plates stiffen: report ratio and convergence
for mm in (2, 4, 6):
    C = fem.elastic_D(1.0, nu)
    rb = ff.homogenized_block(C, tiles=(3, 3, 3), m=mm)
    out[f"iso_block_3x3x3_m{mm}"] = dict(k=rb["k"], EA_over_H=3.0, ratio=rb["k"] / 3.0, res=rb["residual"])
# 3. cubic_C round trip
Cc = ff.cubic_C(0.06, 0.3, 0.02)
S = np.linalg.inv(Cc)
out["cubic_C_roundtrip"] = dict(E100=1 / S[0, 0], nu100=-S[0, 1] / S[0, 0], G=Cc[3, 3])
# 4. harmonic column vs analytic rod with lateral periodicity: u_out/U0 = 1 / cos(k L), k = omega / c* complex
L = 6
for drive, modulus in ((2, Mmod), (0, mu)):
    nn = 6
    mesh = ff.TiledMesh(np.ones((nn, nn, nn)), None, tiles=(1, 1, L), periodic=(True, True, False), nu=nu)
    ch = ff.HarmonicChain(mesh, eta=0.01)
    fs = np.array([0.02, 0.1, 0.2, 0.3])
    t0 = time.perf_counter()
    res = ch.solve(fs, drives=(drive,))
    w = np.sqrt([bloch.f_to_sigma(f, nu) for f in fs])
    kk = w / np.sqrt(modulus * (1 + 0.01j))
    ana = np.abs(1 / np.cos(kk * L))
    out[f"harmonic_drive{drive}"] = dict(f_star=fs.tolist(), T=res["T"][str(drive)], T_exact=ana.tolist(),
                                         rel=(np.array(res["T"][str(drive)]) / ana - 1).tolist(),
                                         residual_max=res["residual_max"], perturbed=res["perturbed_max"],
                                         s=round(time.perf_counter() - t0, 1))
print(json.dumps(out, indent=1))
Path(__file__).resolve().parents[3].joinpath("results/verification/v6/selftest_fe.json").write_text(
    json.dumps(out, indent=1), encoding="utf-8")
