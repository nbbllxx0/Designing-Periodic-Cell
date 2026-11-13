"""Bounds and units: soundness (achieved designs are never refuted) and the refusals the paper relies on."""
import numpy as np
import pytest

import amm  # noqa: F401
from amm import bounds, fem, geometry as G, homog, units

DESIGNS = [dict(family="tpms", kind=k, params=dict(density=d, mode=m))
           for k in ("gyroid", "schwarz_p", "diamond", "iwp") for d in (0.15, 0.35) for m in ("network", "sheet")]
DESIGNS += [dict(family="struts", kind=k, params=dict(r=0.08, R=0.15)) for k in ("sc", "bcc", "octet")]
DESIGNS += [dict(family="resonator", kind=k, params=dict(c=c, w=0.2))
            for k, c in (("cube_bars", 0.6), ("sphere_ligaments", 0.3))]


@pytest.fixture(scope="module")
def achieved():
    out = []
    for spec in DESIGNS:
        cov, sub, info = G.design_cell(spec, 16)
        if not all(info["percolates"]):
            continue
        r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub))
        out.append((spec, r))
    return out


def test_bounds_never_refute_an_achieved_design(achieved):
    assert len(achieved) >= 15
    for spec, r in achieved:
        t = dict(density_max=r["density"] + 1e-9, E100_min=r["E100"], G_min=r["G"], bulk_min=r["bulk"],
                 nu100_min=r["nu100"] - 1e-9, nu100_max=r["nu100"] + 1e-9)
        out = bounds.check(t, nu_s=0.3, symmetry="cubic")
        assert out["verdict"] == bounds.NOT_REFUTED, (spec, out["violated"])
        for key in ("E100_min", "G_min", "bulk_min"):
            assert out["margins"][key]["ratio_to_bound"] <= 1.0


def test_hs_formula_limits_and_order():
    s = bounds.solid_moduli(0.3)
    assert np.isclose(bounds.hashin_shtrikman_porous(1.0, 0.3)["K"], s["K"])
    assert np.isclose(bounds.hashin_shtrikman_porous(1.0, 0.3)["mu"], s["mu"])
    for phi in (0.05, 0.2, 0.5, 0.9):
        hs = bounds.hashin_shtrikman_porous(phi, 0.3)
        assert 0 < hs["K"] <= phi * s["K"] and 0 < hs["mu"] <= phi * s["mu"] and hs["E"] <= phi * s["E"] + 1e-12


def test_unit_slip_is_refused_by_voigt():
    # "a 30%-dense PA12 lattice with E = 1.7 GPa" asks for the solid's own modulus: impossible for any geometry
    out = bounds.check_request(dict(material="PA12", density_max=0.3, E100_min=[1.7, "GPa"]))
    assert out["verdict"] == bounds.PROVEN and out["violated"][0]["bound"] == "V1"
    ok = bounds.check_request(dict(material="PA12", density_max=0.3, E100_min=[170, "MPa"]))
    assert ok["verdict"] == bounds.NOT_REFUTED
    near = bounds.check_request(dict(material="PA12", density_max=0.3, E100_min=[500, "MPa"]))
    assert near["verdict"] == bounds.NOT_REFUTED and near["margins"]["E100_min"]["ratio_to_bound"] > 0.95


def test_poisson_outside_cubic_stability_is_refused_with_scope():
    out = bounds.check(dict(nu100_min=0.6), symmetry="cubic")
    assert out["verdict"] == bounds.PROVEN and out["violated"][0]["scope"] == "cubic design space"
    assert bounds.check(dict(nu100_max=-0.5), symmetry="cubic")["verdict"] == bounds.NOT_REFUTED  # auxetic is allowed


def test_gap_rules_and_contradictions():
    assert bounds.check(dict(gap=dict(f_lo=0.0, f_hi=0.3)))["violated"][0]["bound"] == "W1"
    assert bounds.check(dict(gap=dict(f_lo=0.5, f_hi=0.4)))["verdict"] == bounds.PROVEN
    assert bounds.check(dict(density_min=0.4, density_max=0.3))["violated"][0]["bound"] == "P1"


def test_hs_is_advisory_for_cubic_and_binding_for_isotropic():
    hs = bounds.hashin_shtrikman_porous(0.2, 0.3)
    t = dict(density_max=0.2, bulk_min=0.5 * (hs["K"] + 0.2 * bounds.solid_moduli(0.3)["K"]))  # between HS and Voigt
    cub = bounds.check(t, symmetry="cubic")
    iso = bounds.check(t, symmetry="isotropic")
    assert cub["verdict"] == bounds.NOT_REFUTED and cub["advisory"][0]["bound"] == "HS"
    assert iso["verdict"] == bounds.PROVEN


def test_missing_information_is_underspecified_not_guessed():
    out = bounds.check_request(dict(material="PA12", gap=dict(f_lo=[2, "kHz"], f_hi=[3, "kHz"])))
    assert out["verdict"] == bounds.UNDERSPECIFIED and "cell size" in out["missing"][0]
    out = bounds.check_request(dict(E100_min=[50, "MPa"], density_max=0.3))
    assert out["verdict"] == bounds.UNDERSPECIFIED and "material" in out["missing"][0]


def test_frequency_conversion_roundtrip():
    t, missing, ctx = units.normalize(dict(material="Ti6Al4V", cell_size=[10, "mm"],
                                           gap=dict(f_lo=[50, "kHz"], f_hi=[80, "kHz"])))
    assert not missing
    back = units.to_physical(t["gap"], units.MATERIALS["Ti6Al4V"], 10e-3)
    assert np.isclose(back["f_lo_Hz"], 50e3) and np.isclose(back["f_hi_Hz"], 80e3)
