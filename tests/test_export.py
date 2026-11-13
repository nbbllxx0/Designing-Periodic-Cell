"""B2 (2026-11-07): STL export, report, manufacturing screening and the as-built tool."""
from __future__ import annotations

import json
import struct

import numpy as np
import pytest

from amm import certify, export as ex, tools

SC = dict(family="struts", kind="sc", params=dict(r=0.12, R=0.0))


def _session(tmp_path, profile="C", cell=10):
    s = tools.Session(tmp_path / "s", profile=profile)
    assert s.call("set_material", {"name": "PA12"})["ok"]
    if cell:
        assert s.call("set_constraints", {"cell_size": cell, "cell_size_unit": "mm"})["ok"]
    return s


@pytest.mark.parametrize("method", ["marching_cubes", "voxel_faces"])
def test_surfaces_are_watertight_and_enclose_the_solid(method):
    field, _ = ex.solid_field(SC, 32)
    V, F, m = ex.surface(field, 1 / 32, method)
    chk = ex.mesh_check(V, F)
    assert m == method and chk["watertight"] and chk["n_shells"] == 1
    assert chk["volume"] == pytest.approx(field.mean(), rel=0.12)  # outward orientation: positive volume


def test_min_feature_estimate_is_close_to_the_strut_diameter():
    for spec, d in ((SC, 0.24), (dict(family="struts", kind="bcc", params=dict(r=0.05, R=0.0)), 0.10)):
        field, _ = ex.solid_field(spec, 48)
        est = ex.min_feature(field >= 0.5)["voxels"] / 48
        assert d - 3 / 48 <= est <= d + 1 / 48, (spec["kind"], est)


def test_screen_flags_a_printer_limit_above_the_feature_size(tmp_path):
    s = _session(tmp_path)
    d = {"kind": "bcc", "params": {"r": 0.05, "R": 0.0}}  # 1.0 mm struts on a 10 mm cell
    ok = s.call("screen_manufacturing", {"design": d, "tiles": 2, "resolution": 32})["result"]
    assert ok["schema_version"] == "amm-screen/1" and "NOT a printability claim" in ok["disclaimer"]
    assert ok["min_feature"]["printer_limit_mm"] == pytest.approx(0.8) and "PA12" in ok["min_feature"]["limit_source"]
    assert ok["tiled_connectivity"]["passed"] and ok["watertight"]["passed"]
    bad = s.call("screen_manufacturing", {"design": d, "tiles": 2, "resolution": 32,
                                          "printer_min_feature_mm": 2.0})["result"]
    assert not bad["min_feature"]["passed"] and bad["verdict"] == "screen failed"
    assert bad["min_feature"]["solid_thinner_than_limit"] > 0.5


def test_screen_without_cell_size_is_incomplete(tmp_path):
    s = _session(tmp_path, cell=None)
    r = s.call("screen_manufacturing", {"design": {"kind": "sc", "params": {"r": 0.12, "R": 0.0}},
                                        "tiles": 1, "resolution": 24})["result"]
    assert r["complete"] is False and r["min_feature"]["passed"] is None and "incomplete" in r["verdict"]


def test_export_writes_stl_and_report_with_the_evidence(tmp_path):
    s = _session(tmp_path)
    assert s.call("set_target", {"density_max": 0.4})["ok"]
    out = s.call("export", {"design": {"kind": "sc", "params": {"r": 0.12, "R": 0.0}}, "tiles": 2,
                            "resolution": 32, "tile_resolution": 16})
    assert out["ok"], out
    r = out["result"]
    assert r["schema_version"] == "amm-export/1" and r["unit"] == "mm" and r["outcome"] == "not_certified"
    root = tmp_path / "s"
    for k in ("cell", "tiled"):
        b = (root / r["files"][k]["path"]).read_bytes()
        n = struct.unpack("<I", b[80:84])[0]
        assert len(b) == 84 + 50 * n and n == r["files"][k]["n_triangles"] and ex.sha256(b) == r["files"][k]["sha256"]
        v = np.frombuffer(b[84:], dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])["v"]
        assert v.max() <= (10.0 if k == "cell" else 20.0) + 1e-3 and v.min() >= -1e-3  # mm, tiles 2 = 20 mm
    assert r["files"]["tiled"]["path"].endswith("tiled_2x2x2.stl")
    rep = json.loads((root / r["files"]["report"]["path"]).read_text(encoding="utf-8"))
    assert rep["schema_version"] == "amm-export/1" and rep["outcome"]["outcome"] == "not_certified"
    assert rep["spec"]["material"] == "PA12" and rep["normalized_targets"] == {"density_max": 0.4}
    assert any("NOT a printability claim" in d for d in rep["disclaimers"])
    assert rep["screening"]["watertight"]["passed"] and rep["identity"]["checker"] == certify.checker_hash()
    # deterministic: the same export again gives the same files
    again = s.call("export", {"design": {"kind": "sc", "params": {"r": 0.12, "R": 0.0}}, "tiles": 2,
                              "resolution": 32, "tile_resolution": 16})["result"]
    assert again["files"] == r["files"]


def test_export_needs_a_session_directory():
    s = tools.Session(None, profile="B")
    s.call("set_material", {"name": "PA12"})
    out = s.call("export", {"design": {"kind": "sc", "params": {"r": 0.12, "R": 0.0}}})
    assert not out["ok"] and "session directory" in out["error"]


def test_as_built_tool_runs_the_certificate_block(tmp_path):
    s = _session(tmp_path)
    assert s.call("set_target", {"E100_min": {"value": 0.002, "unit": "E_s"}})["ok"]
    d = {"kind": "sc", "params": {"r": 0.12, "R": 0.0}}
    out = s.call("as_built", {"design": d, "offset": 0.01})
    assert out["ok"], out
    r = out["result"]
    assert r["schema_version"] == "amm-asbuilt/1" and r["offset_mm"] == pytest.approx(0.1)
    assert set(r["cases"]) == {"erode", "dilate"} and r["source"].startswith("standalone")
    ref = certify.as_built_block(SC, {"E100_min": 0.002}, nu=0.39, n_static=32, n_bloch=20, offset=0.01)
    assert tools._plain(ref["cases"]) == r["cases"]  # the same check as inside certify
    assert r["cases"]["erode"]["E100"] < r["cases"]["dilate"]["E100"]
    assert not tools.Session(None, profile="B").call("as_built", {"design": d})["ok"]  # profile C only
    assert s.used["as_built"] == 1
