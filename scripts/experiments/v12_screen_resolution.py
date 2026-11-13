"""V12 (audit-loop round 2, 2026-11-09): resolution dependence of the minimum-feature screen.

The PA12 filter (sphere_ligaments c 0.356522, w 0.108696, a = 10 mm, ligament diameter 1.087 mm) failed the
0.8 mm screen at the default screening resolution of 64 voxels per cell (voxel 0.156 mm). Its ligament axes lie
between voxel centres there, so the voxel solid loses one to two voxels of diameter. This script reruns the
manufacturing screen (export.screen, the tool's own check) at 64, 96 and 128 voxels per cell for the three
engineering designs and records the opening estimate, the removed fraction at the printer limit and the verdict.

    python scripts/experiments/v12_screen_resolution.py
Writes results/verification/v12/screen_resolution.json. CPU only, no LLM.
"""
import json
import time
from pathlib import Path

import amm  # noqa: F401
from amm import export

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v12"
DESIGNS = (("mount_PA12", dict(family="resonator", kind="cube_bars", params=dict(c=0.592174, w=0.151304)), 20.0, 0.8),
           ("filter_PA12", dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.356522, w=0.108696)),
            10.0, 0.8),
           ("filter_316L", dict(family="resonator", kind="cube_bars", params=dict(c=0.786957, w=0.06)), 10.0, 0.3))


def main():
    rows = []
    for name, spec, a_mm, limit_mm in DESIGNS:
        for res in (64, 96, 128):
            t0 = time.perf_counter()
            s = export.screen(spec, a_mm * 1e-3, limit_mm * 1e-3, "material default", tiles=3, resolution=res,
                              tile_resolution=32)
            f = s["min_feature"] if "min_feature" in s else s.get("feature", s)
            row = dict(case=name, resolution=res, voxel_mm=a_mm / res, limit_mm=limit_mm,
                       solid_est_mm=f.get("solid_est_mm"), removed_at_limit=f.get("solid_thinner_than_limit"),
                       passed=f.get("passed"), screen_verdict=s.get("verdict"), member_mm=spec["params"]["w"] * a_mm,
                       seconds=round(time.perf_counter() - t0, 1))
            rows.append(row)
            print(json.dumps(row), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "screen_resolution.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
