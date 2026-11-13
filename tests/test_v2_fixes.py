"""V2 fixes (2026-11-08, results/software/NOTES_V2_fixes.md): Zener and other computed outputs refused with the reason,
negative minima refused on input (bound P1), and check_bounds UNDERSPECIFIED while a target cannot be normalized."""
from __future__ import annotations

from amm import tools


def _s(material="PA12"):
    s = tools.Session(None)
    assert s.call("set_material", {"name": material})["ok"]
    return s


def test_zener_target_is_refused_as_a_computed_output():
    s = _s()
    for key in ("zener_min", "Zener_max", "E110_min", "C44_min"):
        out = s.call("set_target", {key: 0.9})
        assert not out["ok"] and "Extra inputs are not permitted" in out["error"]
        assert f"{key}: not a design target" in out["error"] and "computed outputs" in out["error"]
    out = s.call("set_target", {"porosity_max": 0.5})  # an unknown key that is no output keeps the plain message
    assert out["error"] == "porosity_max: Extra inputs are not permitted"
    assert s.state["targets"] == {}


def test_negative_minimum_is_refused_on_input():
    s = _s()
    for key in ("E100_min", "G_min", "bulk_min"):
        out = s.call("set_target", {key: {"value": -5, "unit": "GPa"}})
        assert not out["ok"] and out["error"].startswith(f"{key} must be positive") and "P1" in out["error"]
        assert not s.call("set_target", {key: {"value": 0, "unit": "E_s"}})["ok"]
    assert s.state["targets"] == {}
    assert s.call("set_target", {"E100_max": {"value": -1, "unit": "GPa"}})["ok"]  # a maximum: proven infeasible
    assert s.call("check_bounds")["result"]["violated"][0]["bound"] == "P1"


def test_check_bounds_is_underspecified_while_a_target_cannot_be_normalized():
    s = _s()
    assert s.call("set_target", {"density_max": 0.3, "gap": {"f_lo": 1000, "f_hi": 2000, "unit": "Hz"}})["ok"]
    r = s.call("check_bounds")["result"]
    assert r["verdict"] == "UNDERSPECIFIED" == r["bounds_verdict"]
    assert any("no cell size" in m for m in r["cannot_normalize"])
    assert s.call("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"})["ok"]
    r = s.call("check_bounds")["result"]
    assert r["verdict"] != "UNDERSPECIFIED" and not r["cannot_normalize"]
