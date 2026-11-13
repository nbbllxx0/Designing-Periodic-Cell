"""Tutorial (c): manufacturing screening and STL export of a design.

    python examples/03_export_and_screening.py [--out DIR]

Steps:
  1. PA12 by SLS (typical minimum feature 0.8 mm, a datasheet value in amm.units.MATERIALS), 10 mm cell;
  2. `screen_manufacturing` of a bcc strut lattice with 1.6 mm struts: estimated minimum solid feature and narrowest
     channel in mm against the printer limit, connectivity of a 3x3x3 block, watertight surfaces;
  3. the same design on a 4 mm cell (0.64 mm struts): the feature check fails against the 0.8 mm limit;
  4. `export`: single-cell STL, tiled 3x3x3 STL and report.json with the full evidence, written to
     <out>/exports/<name>/.
Screening is NOT a printability claim: support, powder removal, residual stress and process parameters are not
checked. The design here is not certified (no targets are certified in this session), so the report's outcome is
"not_certified"; run tutorial 02 for a certified design.

Needs only the core install; scikit-image (extra `export`) gives marching-cubes surfaces, without it the voxel
boundary surface is written (method "voxel_faces"). Runtime: about 10-40 s on CPU.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import amm  # noqa: F401
from amm import tools

HERE = Path(__file__).resolve().parent
DESIGN = {"kind": "bcc", "params": {"r": 0.08, "R": 0.0}}  # strut radius 0.08 a: diameter 0.16 a


def screen_line(r):
    mf = r["min_feature"]
    return (f"{r['verdict']}: min solid feature {mf['solid_est_mm']:.2f} mm, narrowest channel {mf['void_est_mm']:.2f}"
            f" mm, limit {mf['printer_limit_mm']} mm ({'pass' if mf['passed'] else 'FAIL'}; "
            f"{100 * mf['solid_thinner_than_limit']:.1f} % of the solid thinner than the limit); 3x3x3 block "
            f"connected {r['tiled_connectivity']['passed']}; watertight {r['watertight']['passed']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "outputs" / "03_session"), help="session directory (overwritten)")
    a = ap.parse_args()
    out_dir = Path(a.out)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    t0 = time.perf_counter()
    s = tools.Session(out_dir, profile="C")
    assert s.call("set_material", {"name": "PA12"})["ok"]
    assert s.call("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"})["ok"]

    t1 = time.perf_counter()
    ok = s.call("screen_manufacturing", {"design": DESIGN, "tiles": 3, "resolution": 64})
    assert ok["ok"], ok
    r = ok["result"]
    print(f"10 mm cell: {screen_line(r)}  [{time.perf_counter() - t1:.1f} s]")
    print(f"  limit source: {r['min_feature']['limit_source']}")
    print(f"  surface method: {r['watertight']['cell']['method']}; disclaimer: {r['disclaimer']}")

    assert s.call("set_constraints", {"cell_size": 4, "cell_size_unit": "mm"})["ok"]
    small = s.call("screen_manufacturing", {"design": DESIGN, "tiles": 3, "resolution": 64})["result"]
    print(f"4 mm cell:  {screen_line(small)}")

    assert s.call("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"})["ok"]
    assert s.call("set_target", {"density_max": 0.3})["ok"]
    t2 = time.perf_counter()
    ex = s.call("export", {"design": DESIGN, "tiles": 3, "resolution": 64, "tile_resolution": 32})
    assert ex["ok"], ex
    e = ex["result"]
    print(f"\nexport {e['name']} ({e['unit']}), outcome {e['outcome']} ({e['outcome_title']}), "
          f"{time.perf_counter() - t2:.1f} s")
    for k, f in e["files"].items():
        print(f"  {k:7s} {f['path']}  {f['bytes']} bytes  sha256 {f['sha256'][:16]}"
              + (f"  {f['n_triangles']} triangles ({f['method']})" if "n_triangles" in f else ""))
    rep = json.loads((out_dir / e["files"]["report"]["path"]).read_text(encoding="utf-8"))
    print("  report.json keys:", sorted(rep))
    print("  disclaimers:", *rep["disclaimers"], sep="\n    - ")

    assert r["passed"] and not small["min_feature"]["passed"]
    print(f"\ntotal {time.perf_counter() - t0:.1f} s")
    print("summary:", json.dumps(dict(design=DESIGN, screen_10mm=r["verdict"], screen_4mm=small["verdict"],
                                      export=e["name"], seconds_total=round(time.perf_counter() - t0, 1))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
