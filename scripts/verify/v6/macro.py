"""Case 1 macro static check (NOTES.md 1.6): homogenized 6x6x6 mount with the certificate's guarded C*, plus a direct
voxel solve of a finite 3x3x3 block. CPU only (PARDISO).

    python scripts/verify/v6/macro.py <label> <session_dir>      (label: design | reference)
Writes results/verification/v6/case1/macro_<label>.json.
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
W_N, DELTA_MAX_M, A_M, TILES = 1800.0, 0.25e-3, 0.020, (6, 6, 6)


def load_certificate(session_dir: Path) -> tuple[dict, dict]:
    s = json.loads((session_dir / "summary.json").read_text(encoding="utf-8"))
    d = s["released"]
    c = next(x for x in s["certify"] if x["design"] == d)
    h = c["result"]["spec_hash"]
    f = sorted((session_dir / "certificates").glob(f"{h}_*.json"))
    cert = json.loads(f[-1].read_text(encoding="utf-8"))
    return s, cert


def main(label: str, session_dir: str) -> int:
    t0 = time.perf_counter()
    sd = Path(session_dir)
    s, cert = load_certificate(sd)
    mat = units.MATERIALS[s["config"]["material"]]
    Es, nu = mat["E"], mat["nu"]
    q = cert["blocks"]["static"]["convergence"]["quantities"]
    E_lo, G_lo = q["E100"]["lower"], q["G"]["lower"]
    nus = (q["nu100"]["lower"], q["nu100"]["upper"])
    ext = {k: q[k]["extrapolated"] for k in ("E100", "G", "nu100", "density")}
    out = dict(label=label, design=s["released"], spec=cert["spec"], material=s["config"]["material"], E_s=Es,
               cell_size_m=A_M, load_N=W_N, delta_max_m=DELTA_MAX_M, k_req_N_per_m=W_N / DELTA_MAX_M,
               guarded=dict(E100_lower=E_lo, G_lower=G_lo, nu100_bounds=list(nus)), extrapolated=ext,
               homogenized_6x6x6={}, homogenized_3x3x3={}, voxel_3x3x3={})
    phys = lambda k: k * Es * A_M  # k* in E_s a  ->  N/m
    # 1. homogenized 6x6x6 with the guarded C*, both nu100 bounds, m = 2, 4, 8
    for m in (2, 4, 8):
        rows = {}
        for tag, nu100 in (("nu_lower", nus[0]), ("nu_upper", nus[1])):
            r = ff.homogenized_block(ff.cubic_C(E_lo, nu100, G_lo), tiles=TILES, m=m)
            rows[tag] = dict(k_star=r["k"], k_N_per_m=phys(r["k"]), deflection_m=W_N / phys(r["k"]),
                             residual=r["residual"], ndof=r["ndof"], seconds=r["seconds"])
        worst = min(rows.values(), key=lambda x: x["k_N_per_m"])
        out["homogenized_6x6x6"][f"m{m}"] = dict(rows, worst=worst)
        print(f"{label} hom 6^3 m={m}: k = {worst['k_N_per_m']/1e6:.3f} kN/mm, delta = {worst['deflection_m']*1e3:.4f} mm",
              flush=True)
    fin = out["homogenized_6x6x6"]["m8"]["worst"]
    prev = out["homogenized_6x6x6"]["m4"]["worst"]
    out["A2"] = dict(deflection_mm=fin["deflection_m"] * 1e3, k_kN_per_mm=fin["k_N_per_m"] / 1e6,
                     mesh_change_m4_to_m8=fin["k_N_per_m"] / prev["k_N_per_m"] - 1,
                     uniaxial_estimate_kN_per_mm=E_lo * Es * (TILES[0] * A_M) ** 2 / (TILES[2] * A_M) / 1e6,
                     passed=bool(fin["deflection_m"] <= DELTA_MAX_M))
    # 2. homogenized 3x3x3 (guarded and extrapolated C*), m = 8
    for tag, C in (("guarded_worst", None), ("extrapolated", ff.cubic_C(ext["E100"], ext["nu100"], ext["G"]))):
        if C is None:
            ks = [ff.homogenized_block(ff.cubic_C(E_lo, v, G_lo), tiles=(3, 3, 3), m=8)["k"] for v in nus]
            k = min(ks)
        else:
            k = ff.homogenized_block(C, tiles=(3, 3, 3), m=8)["k"]
        out["homogenized_3x3x3"][tag] = dict(k_star=k, k_N_per_m=phys(k))
    # 3. direct voxel 3x3x3 block, n = 16, 24, 32
    for n in (16, 24, 32):
        cov, sub, info = ff.cell_geometry(cert["spec"], n)
        t1 = time.perf_counter()
        mesh = ff.TiledMesh(cov, sub, tiles=(3, 3, 3), periodic=(False, False, False), nu=nu, with_mass=False)
        r = ff.plate_compression(mesh)
        # matched-resolution homogenized reference: the periodic cell's own C* at the same n (phase 0), the same
        # 3x3x3 plates; the ratio separates the finite-size effect from discretization bias (deviation 2)
        from amm import fem, homog
        hc = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=nu))
        km = ff.homogenized_block(hc["C"], tiles=(3, 3, 3), m=8)["k"]
        out["voxel_3x3x3"][f"n{n}"] = dict(k_star=r["k"], k_N_per_m=phys(r["k"]), residual=r["residual"],
                                           n_perturbed=r["n_perturbed"], ndof=r["ndof"], ne=r["ne"],
                                           density=mesh.density, seconds=round(time.perf_counter() - t1, 1),
                                           periodic_E100_same_n=hc["E100"], k_star_hom_same_n=km,
                                           ratio_same_n=r["k"] / km)
        print(f"{label} voxel 3^3 n={n}: k* = {r['k']:.5f} ({r['ndof']} dof, {time.perf_counter()-t1:.0f} s), "
              f"hom ext {out['homogenized_3x3x3']['extrapolated']['k_star']:.5f}", flush=True)
        del mesh
    vx = out["voxel_3x3x3"]
    ks = [vx[f"n{n}"]["k_star"] for n in (16, 24, 32)]
    # stiffness converges from above; Richardson-type estimate with the amm static guard's order rule (p <= 1)
    from amm.bloch import _order
    p = _order([1 / 16, 1 / 24, 1 / 32], ks)
    pu = min(p, 1.0) if p is not None else 1.0
    rr = (1 / 32) ** pu / ((1 / 24) ** pu - (1 / 32) ** pu)
    k_ext = ks[2] + (ks[2] - ks[1]) * rr
    out["voxel_3x3x3"]["extrapolated"] = dict(k_star=k_ext, order=p, order_used=pu, k_N_per_m=phys(k_ext))
    ratio_ext = k_ext / out["homogenized_3x3x3"]["extrapolated"]["k_star"]
    ratio_fin = ks[2] / out["homogenized_3x3x3"]["extrapolated"]["k_star"]
    out["size_effect"] = dict(ratio_same_n={f"n{n}": vx[f"n{n}"]["ratio_same_n"] for n in (16, 24, 32)},
                              ratio_voxel_over_hom_3x3x3_extrapolated=ratio_ext, ratio_voxel_n32_over_hom=ratio_fin,
                              ratio_voxel_ext_over_hom_guarded=k_ext / out["homogenized_3x3x3"]["guarded_worst"]["k_star"])
    corr = min(1.0, vx["n32"]["ratio_same_n"])  # deviation 2: matched-resolution ratio at the finest n
    out["A2s"] = dict(size_corrected_deflection_mm=out["A2"]["deflection_mm"] / corr, ratio_used=corr,
                      passed=bool(out["A2"]["deflection_mm"] / corr <= DELTA_MAX_M * 1e3),
                      note="homogenized 6x6x6 (guarded) / min(1, voxel/homogenized ratio at 3x3x3, matched resolution n = 32); reported flag")
    out["seconds"] = round(time.perf_counter() - t0, 1)
    (V6 / "case1" / f"macro_{label}.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(json.dumps(dict(A2=out["A2"], A2s=out["A2s"], size=out["size_effect"]), indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
