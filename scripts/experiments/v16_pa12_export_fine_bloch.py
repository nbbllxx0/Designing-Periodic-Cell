"""V16 (2026-11-09): recheck of the exported PA12 filter cell (cell.stl) at the resolutions of the V15 finer gap check.

V15 (results/verification/v15/filters.json) certified the PA12 sphere-ligament filter with counted resolutions
n = 30 and 40, an edge-only resolution n = 60 and grid phases 0.25 and 0.5 at n = 40. The exported-cell recheck
(results/verification/v6/case2/recheck_PA12.json, scripts/verify/v6/recheck.py) used n = 20/30 counted and 40 edge
only; under the released rules it is undetermined (results/verification/v14/rechecks.json). This script reruns its
gap block on the same STL, re-voxelized independently (anti-aliased rays, scripts/verify/v6/stl_recheck.py), with
the V15 resolutions, and judges it with the released checker (bloch.certify_gap, certify.gap_verdict, the density
spread check of the gap block and certify.feature_check at the finest resolution).

Wave vectors: the 37 per counted resolution of certify_gap plus, as extra k, the adversarial vectors of the PA12
certificate, of the V15 rerun and of the stored STL search at n = 10 in recheck_PA12.json. That search (31 GPU-min) is
not repeated: the STL file is the same (sha256 checked below). The run is CPU only (PARDISO). The static recheck is
not rerun; its stored result is carried over.

Cost: about 15 CPU-min (V15 PA12 gap block, 15.2 min). No GPU, no LLM.
Approved by the author 2026-11-09 ("Yes, recheck PA12").

    python scripts/experiments/v16_pa12_export_fine_bloch.py [PA12|316L]
Output: results/verification/v16/recheck_<cell>.json
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from amm import bloch, certify, fem, units

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "verify" / "v6"))
import stl_recheck as sr  # noqa: E402

OUT = ROOT / "results" / "verification" / "v16"
CELLS = {  # the PA12 recheck (approved "Yes, recheck PA12"); the 316L recheck added 2026-11-10 after the order-test
           # fix certified the 316L design (approved "Yes, all of it": the confirm-round fix list)
    "PA12": dict(session="results/verification/v6/case2/session_PA12",
                 cert="certificates/e5519f4fdbef64db_e212dc39bc22b626.json"),
    "316L": dict(session="results/verification/v6/case2/session_316L",
                 cert="certificates/f1d00ed043a926f1_0dc7c12bea6f73f4.json"),
}
CELL = sys.argv[1] if len(sys.argv) > 1 else "PA12"
SESSION = ROOT / CELLS[CELL]["session"]
RECHECK = ROOT / f"results/verification/v6/case2/recheck_{CELL}.json"
CERT = SESSION / CELLS[CELL]["cert"]
V15 = ROOT / "results/verification/v15/filters.json"
COUNTED = ((30, 5), (40, 3))  # (n, samples per voxel edge)
EDGE = ((60, 3),)
PHASE_S = 3  # samples per voxel edge for the phase meshes at the top counted n


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    rc, cert, v15 = load(RECHECK), load(CERT), load(V15)["cells"][CELL]
    s = load(SESSION / "summary.json")
    a_mm = float(s["config"]["cell_size_mm"])
    nu = units.MATERIALS[s["config"]["material"]]["nu"]
    stl = SESSION / rc["stl"]
    sha = hashlib.sha256(stl.read_bytes()).hexdigest()
    assert sha == rc["stl_sha256"], "STL differs from the one the stored adversarial search used"
    gap = rc["targets"]["gap"]

    def mesh(n, smp, phase=0.0):
        cov, sub, info, _ = sr.voxelize_stl_aa(stl, n, smp, a_mm, phase)
        return fem.build_mesh(cov, sub=sub, nu=nu), float(cov.mean()), info

    meshes, dens = {}, []
    for n, smp in COUNTED:
        m, d, _ = mesh(n, smp)
        meshes[n] = m
        dens.append(d)
        print(f"counted mesh n={n}: density {d:.5f}", flush=True)
    edge_meshes = {n: mesh(n, smp)[0] for n, smp in EDGE}
    n_top = max(meshes)
    phase_meshes = [mesh(n_top, PHASE_S, p)[0] for p in certify.BLOCH_PHASES]
    extra = np.vstack([np.array(x, float).reshape(-1, 3) * np.pi for x in
                       (cert["blocks"]["bloch"]["adversarial"]["ks"], v15["bloch"]["adversarial"]["ks"],
                        rc["gap"]["adversarial_stl"]["ks"])])
    tb = time.perf_counter()
    g = bloch.certify_gap(meshes, gap["f_lo"], gap["f_hi"], n_path=4, n_interior=10, extra_ks=extra,
                          edge_meshes=edge_meshes, phase_meshes=phase_meshes)
    g["density_spread"] = float(max(dens) - min(dens))
    g["passed"] = bool(g["passed"] and g["density_spread"] <= 0.01)
    g["verdict"] = certify.gap_verdict(g)
    feat = certify.feature_check(rc["spec"], max([*meshes, *edge_meshes]), certify.FEATURE_MIN_VOXELS)
    g["feature"] = feat
    if not feat["passed"]:
        g["passed"] = False
        g["verdict"] = certify._withhold(g["verdict"], feat)
    cv = g.get("convergence") or {}
    static_ok = bool(rc["static"].get("numerics_ok")) and rc["passed"]
    out = dict(
        settings=dict(counted=[list(x) for x in COUNTED], edge=[list(x) for x in EDGE],
                      bloch_phases=list(certify.BLOCH_PHASES), phase_samples=PHASE_S, n_extra_k=int(len(extra)),
                      feature_min_voxels=certify.FEATURE_MIN_VOXELS, checker=certify.checker_hash()),
        stl=rc["stl"], stl_sha256=sha, spec=rc["spec"], targets=rc["targets"], material=rc["material"],
        static_carried=dict(source=str(RECHECK.relative_to(ROOT)).replace("\\", "/"), passed=static_ok,
                            diff_extrapolated=rc["static"]["diff_extrapolated"]),
        gap=dict(passed=bool(g["passed"]), verdict=g["verdict"], safe_interval=cv.get("safe_interval"),
                 certificate_safe_interval=v15["bloch"]["convergence"]["safe_interval"],
                 below_band=g["claim"]["below_band"], certificate_below_band=v15["bloch"]["claim"]["below_band"],
                 lower_edge=cv.get("lower_edge"), upper_edge=cv.get("upper_edge"), edges=cv.get("edges"),
                 phase_edges=cv.get("phase_edges"), mode=cv.get("mode"), density_spread=g["density_spread"],
                 feature=feat, n_k=g["n_k"],
                 resolutions={str(k): {kk: v.get(kk) for kk in ("passed", "n_failures", "ndof", "seconds")}
                              for k, v in g["resolutions"].items()},
                 seconds=round(time.perf_counter() - tb, 1)),
    )
    gv = g["verdict"]["verdict"]
    out["overall"] = gv if static_ok else ("refuted" if gv == "refuted" else "undetermined")
    out["seconds"] = round(time.perf_counter() - t0, 1)
    (OUT / f"recheck_{CELL}.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"{CELL} export recheck: {out['overall']} ({g['verdict'].get('reason', '')}); safe {cv.get('safe_interval')}"
          f" vs design {out['gap']['certificate_safe_interval']}; {out['seconds']} s", flush=True)


if __name__ == "__main__":
    main()
