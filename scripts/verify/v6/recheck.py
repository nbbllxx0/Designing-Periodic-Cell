"""Exported-geometry recheck (NOTES.md section 3): the exported cell.stl, re-voxelized independently, re-run through
the certificate's static and Bloch blocks (amm's guards) and compared with the certificate.

    python scripts/verify/v6/recheck.py <out_json> <session_dir>

GPU: only the fresh adversarial k search at n = 10 (amm.bloch.adversarial_ks), inside the shared solver lock
(scripts/ops/gpulock_run.GpuLock, taken for that call only). Everything else is CPU (PARDISO).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

import amm  # noqa: F401
from amm import bloch, certify as cf, fem, geometry, homog, units

import stl_recheck as sr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
from gpulock_run import GpuLock  # noqa: E402

STATIC = ((32, 5), (48, 3), (64, 3))
STATIC_PH = (0.0, 0.5)
BLOCH = ((20, 5), (30, 5))
EDGE = (40, 3)
BLOCH_PH = (0.25, 0.5)
KEYS = ("density", "E100", "G", "bulk", "nu100")


def vox(stl, n, s, a_mm, phase=0.0):
    """STL coverage at n voxels (s^3 samples each) on the amm sample grid translated by `phase` voxels."""
    cov, sub6, info, _ = sr.voxelize_stl_aa(stl, n, s, a_mm, phase)  # anti-aliased (deviation 3)
    return cov, sub6, info


def rows_static(stl, a_mm, nu):
    rows = {}
    for n, s in STATIC:
        rows[n] = []
        for ph in STATIC_PH:
            t = time.perf_counter()
            cov, sub, info = vox(stl, n, s, a_mm, ph)
            r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=nu))
            row = {k: r[k] for k in KEYS}
            row.update(max_residual=r["max_residual"], min_eig=r["min_eig"], removed_fraction=info["removed_fraction"],
                       percolates=info["percolates"], phase=ph, seconds=round(time.perf_counter() - t, 1))
            rows[n].append(row)
            print(f"  static n={n} phase={ph}: density {row['density']:.5f} E100 {row['E100']:.6f} "
                  f"({row['seconds']} s)", flush=True)
    return rows


def main(out_json: str, session_dir: str) -> int:
    t0 = time.perf_counter()
    sd = Path(session_dir)
    s = json.loads((sd / "summary.json").read_text(encoding="utf-8"))
    d = s["released"]
    c = next(x for x in s["certify"] if x["design"] == d)
    h = c["result"]["spec_hash"]
    cert = json.loads(sorted((sd / "certificates").glob(f"{h}_*.json"))[-1].read_text(encoding="utf-8"))
    exp = s["calls"]["export"]["result"]
    stl = sd / exp["files"]["cell"]["path"]
    a_mm = float(s["config"]["cell_size_mm"])
    nu = units.MATERIALS[s["config"]["material"]]["nu"]
    targets = cert["targets"]
    out = dict(design=d, spec=cert["spec"], stl=exp["files"]["cell"]["path"],
               stl_sha256=exp["files"]["cell"]["sha256"], n_triangles=exp["files"]["cell"]["n_triangles"],
               export_method=exp["files"]["cell"]["method"], targets=targets, material=s["config"]["material"])
    raw = sr.voxelize_stl_aa(stl, 32, 5, a_mm)[3]
    out["parity"] = raw
    # ---- static
    print("static rows (STL)", flush=True)
    rows = rows_static(stl, a_mm, nu)
    conv = cf.static_convergence({n: rows[n] for n in rows})
    st_t = {k: v for k, v in targets.items() if k in cf.STATIC_KEYS}
    numerics = all(r["max_residual"] <= 1e-10 and r["min_eig"] > 1e-8 and r["removed_fraction"] <= 0.01
                   and all(r["percolates"]) for v in rows.values() for r in v)
    sv = cf.static_verdict(conv["quantities"], st_t, numerics) if st_t else None
    cst = cert["blocks"]["static"]
    cq = cst["convergence"]["quantities"]
    comp = {}
    for n, _ in STATIC:
        cr = cst["resolutions"].get(str(n)) or cst["resolutions"].get(n)
        if cr is None:
            continue
        comp[n] = {k: dict(stl=rows[n][0][k], certificate=cr[k], rel=(rows[n][0][k] - cr[k]) / abs(cr[k]))
                   for k in KEYS}
    out["static"] = dict(rows=rows, convergence={k: {kk: conv["quantities"][k][kk] for kk in
                                                    ("extrapolated", "lower", "upper", "converged", "mode", "p")}
                                                for k in KEYS},
                         numerics_ok=bool(numerics), verdict=sv,
                         certificate={k: {kk: cq[k][kk] for kk in ("extrapolated", "lower", "upper")} for k in KEYS},
                         certificate_rung=cst.get("used"),
                         diff_matched_phase0=comp,
                         diff_extrapolated={k: (conv["quantities"][k]["extrapolated"] - cq[k]["extrapolated"])
                                            / abs(cq[k]["extrapolated"]) for k in KEYS})
    # ---- gap
    gap = targets.get("gap")
    if gap:
        print("Bloch (STL)", flush=True)
        meshes = {n: fem.build_mesh(*vox(stl, n, s_, a_mm)[:2], nu=nu) for n, s_ in BLOCH}
        edge = {EDGE[0]: fem.build_mesh(*vox(stl, EDGE[0], EDGE[1], a_mm)[:2], nu=nu)}
        phm = [fem.build_mesh(*vox(stl, 30, 5, a_mm, p)[:2], nu=nu) for p in BLOCH_PH]
        m10 = fem.build_mesh(*vox(stl, 10, 10, a_mm)[:2], nu=nu)
        tg = time.perf_counter()
        with GpuLock("v6"):
            adv = bloch.adversarial_ks(m10, gap["f_lo"], gap["f_hi"])
        gpu_s = round(time.perf_counter() - tg, 1)
        ks_cert = np.array(cert["blocks"]["bloch"]["adversarial"]["ks"], float) * np.pi
        extra = np.vstack([ks_cert.reshape(-1, 3), adv["ks"].reshape(-1, 3)])
        tb = time.perf_counter()
        g = bloch.certify_gap(meshes, gap["f_lo"], gap["f_hi"], n_path=4, n_interior=10, extra_ks=extra,
                              edge_meshes=edge, phase_meshes=phm)
        g["verdict"] = cf.gap_verdict(g)
        cb = cert["blocks"]["bloch"]
        ce = (cb.get("convergence") or {}).get("edges", {})
        re_ = (g.get("convergence") or {}).get("edges", {})
        edge_diff = {str(n): dict(stl=re_.get(n) or re_.get(str(n)), certificate=ce.get(str(n)) or ce.get(n))
                     for n in (20, 30, 40)}
        out["gap"] = dict(passed=bool(g["passed"]), verdict=g["verdict"],
                          safe_interval=(g.get("convergence") or {}).get("safe_interval"),
                          certificate_safe_interval=(cb.get("convergence") or {}).get("safe_interval"),
                          below_band=g["claim"]["below_band"], certificate_below_band=cb["claim"]["below_band"],
                          resolutions={str(k): {kk: v[kk] for kk in ("passed", "n_failures", "ndof", "seconds")}
                                       for k, v in g["resolutions"].items()},
                          edges=edge_diff, n_k=g["n_k"], gpu_seconds=gpu_s,
                          adversarial_stl=dict(ks=(adv["ks"] / np.pi).round(4).tolist(),
                                               search_edges=adv.get("search_edges")),
                          seconds=round(time.perf_counter() - tb, 1))
        print(f"  gap: {g['verdict']} safe {out['gap']['safe_interval']} (cert {out['gap']['certificate_safe_interval']})",
              flush=True)
    st_ok = (sv is None) or sv["verdict"] == "certified"
    gp_ok = (not gap) or out["gap"]["verdict"]["verdict"] == "certified"
    out["passed"] = bool(st_ok and gp_ok)
    out["seconds"] = round(time.perf_counter() - t0, 1)
    Path(out_json).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"recheck passed={out['passed']} static={sv and sv['verdict']} "
          f"gap={gap and out['gap']['verdict']['verdict']} {out['seconds']} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
