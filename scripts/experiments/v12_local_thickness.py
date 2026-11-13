"""V12 (audit-loop round 2, 2026-11-09): local thickness of the screened designs (domain reviewer #3).

The manufacturing screen's minimum feature is the largest ball diameter whose morphological opening removes at most
1% of the solid. That measure reacts to sharp edges and to the voxel staircase as well as to thin members. This
script computes the local thickness (diameter of the largest inscribed ball containing each solid voxel, after
Hildebrand and Ruegsegger) on the same voxel solid as the screen (export.solid_field, resolution 64, periodic) for
the three engineering designs, and reports the minimum, the 1st percentile and the solid fraction thinner than the
printer limit, beside the opening-based estimate.

Distances are between voxel centres; a ball of centre distance d to the nearest void voxel centre is counted as
diameter 2d - 1 voxels (a slab k voxels thick has d = (k + 1) / 2), the convention of the screen.

    python scripts/experiments/v12_local_thickness.py
Writes results/verification/v12/local_thickness.json. CPU only, no LLM.
"""
import json
from pathlib import Path

import numpy as np
from scipy import ndimage

import amm  # noqa: F401
from amm import export

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v12"
V6 = ROOT / "results/verification/v6"
DESIGNS = (("mount_PA12", "case1/session_design/exports/cube_bars_7db650ec_08d264/report.json"),
           ("filter_PA12", "case2/session_PA12/exports/sphere_ligaments_e5519f4f_e212dc/report.json"),
           ("filter_316L", "case2/session_316L/exports/cube_bars_f1d00ed0_0dc7c1/report.json"))


def find(o, key):
    if isinstance(o, dict):
        if key in o:
            return o[key]
        for v in o.values():
            r = find(v, key)
            if r is not None:
                return r
    return None


def local_thickness(solid: np.ndarray) -> np.ndarray:
    """Local thickness (voxels) of a periodic binary solid; 0 outside."""
    n = solid.shape[0]
    pad = n // 2
    P = np.pad(solid, pad, mode="wrap")
    d = ndimage.distance_transform_edt(P)
    # every solid voxel is a candidate ball centre (exact; maximal balls are a subset)
    lt = np.zeros_like(d)
    radii = np.unique(d[P])
    for r in radii:  # ascending: larger balls overwrite smaller ones
        centres = P & (d == r)
        cover = (ndimage.distance_transform_edt(~centres) <= r) & P
        lt[cover] = np.maximum(lt[cover], 2 * r - 1)
    c = (slice(pad, -pad),) * 3
    return lt[c] * solid


def main():
    rows = []
    for name, rel in DESIGNS:
        rep = json.loads((V6 / rel).read_text())
        spec = find(rep, "design")
        spec = dict(family="resonator", **spec) if "family" not in spec else spec
        a_mm, res = find(rep, "cell_size_mm"), find(rep, "resolution")
        limit = find(rep, "printer_limit_mm")
        field, _ = export.solid_field(spec, res)
        solid = field >= 0.5
        lt = local_thickness(solid)
        vox = a_mm / res
        vals = lt[solid] * vox
        row = dict(case=name, spec=spec, cell_mm=a_mm, resolution=res, voxel_mm=vox, printer_limit_mm=limit,
                   opening_estimate_mm=find(rep, "solid_est_mm"),
                   opening_removed_at_limit=find(rep, "solid_thinner_than_limit"),
                   local_thickness_min_mm=float(vals.min()), local_thickness_p1_mm=float(np.percentile(vals, 1)),
                   local_thickness_p5_mm=float(np.percentile(vals, 5)),
                   solid_fraction_thinner_than_limit=float((vals < limit).mean()),
                   nominal_member_mm=spec["params"]["w"] * a_mm)
        rows.append(row)
        print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items() if k != "spec"}),
              flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "local_thickness.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
