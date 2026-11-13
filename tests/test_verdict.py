"""Three-way certificate verdicts (certified / refuted / undetermined), amm.certify.static_verdict / gap_verdict."""
from amm import certify


def q(lower, upper, ext, rem=0.01, conv=True):
    return dict(lower=lower, upper=upper, extrapolated=ext, remaining=rem, converged=conv)


BASE = dict(density=q(0.19, 0.21, 0.2), E100=q(0.09, 0.12, 0.1), G=q(0.03, 0.05, 0.04), bulk=q(0.05, 0.07, 0.06),
            nu100=q(0.28, 0.32, 0.3))


def test_static_certified_refuted_undetermined():
    assert certify.static_verdict(BASE, {"E100_min": 0.08, "density_max": 0.25})["verdict"] == "certified"
    v = certify.static_verdict(BASE, {"E100_min": 0.13})  # above the guarded upper bound
    assert v["verdict"] == "refuted" and v["targets"]["E100_min"] == "refuted"
    v = certify.static_verdict(BASE, {"E100_min": 0.095})  # inside the guard band: abstain, never refute
    assert v["verdict"] == "undetermined"
    assert certify.static_verdict(BASE, {"density_max": 0.18})["verdict"] == "refuted"


def test_static_not_converged_never_certifies():
    b = dict(BASE, E100=q(0.09, 0.12, 0.1, conv=False), nu100=q(0.28, 0.32, 0.3, conv=False))
    assert certify.static_verdict(b, {"E100_min": 0.05})["verdict"] == "undetermined"
    # stiffness converges from above: the largest computed value bounds the limit even before convergence
    assert certify.static_verdict(b, {"E100_min": 0.2})["verdict"] == "refuted"
    # nu100 has no one-sided convergence: no refutation before convergence
    assert certify.static_verdict(b, {"nu100_min": 0.4})["verdict"] == "undetermined"


def test_static_failed_numerics_abstain_invalid_geometry_refutes():
    """Audit F05: a solver failure says nothing about the design; a cell with no load path is not a solid."""
    v = certify.static_verdict(None, {"E100_min": 0.01}, numerics_ok=False)
    assert v["verdict"] == "undetermined" and v["reason"] == "numerical_failure"
    v = certify.static_verdict(None, {"E100_min": 0.01}, numerics_ok=False, invalid_geometry=True)
    assert v["verdict"] == "refuted" and v["reason"] == "invalid_geometry"
    assert certify._geometry_invalid([dict(checks_failed=["does not percolate [True, False, True]"])])
    assert not certify._geometry_invalid([dict(checks_failed=["solver error: singular"], percolates=[True] * 3)])


def edges_report(f_lo, f_hi, lo_ext, hi_ext, passed=False):
    return dict(passed=passed, claim=dict(f_lo=f_lo, f_hi=f_hi, below_band=6),
                resolutions={20: dict(n_failures=0), 30: dict(n_failures=0)},
                convergence=dict(edges={20: [lo_ext + 0.02, hi_ext + 0.06], 30: [lo_ext + 0.01, hi_ext + 0.03]},
                                 lower_edge=dict(extrapolated=lo_ext, remaining=0.004),
                                 upper_edge=dict(extrapolated=hi_ext, remaining=0.01), safety=2.0))


def test_gap_verdicts():
    assert certify.gap_verdict(edges_report(0.3, 0.6, 0.28, 0.65, passed=True))["verdict"] == "certified"
    # upper edge surely below the claimed f_hi
    assert certify.gap_verdict(edges_report(0.3, 0.8, 0.28, 0.65))["verdict"] == "refuted"
    # lower edge surely above the claimed f_lo
    assert certify.gap_verdict(edges_report(0.25, 0.6, 0.30, 0.65))["verdict"] == "refuted"
    # claim inside the guard band
    assert certify.gap_verdict(edges_report(0.3, 0.66, 0.28, 0.65))["verdict"] == "undetermined"


def test_gap_count_failures_are_evidence_not_refutation():
    r = dict(passed=False, resolutions={20: dict(n_failures=3), 30: dict(n_failures=2)})
    v = certify.gap_verdict(r)
    assert v["verdict"] == "undetermined" and v["evidence"] == "against"


def test_static_block_without_static_targets_stops_at_the_first_rung():
    from amm import atlas
    st = certify.static_block(atlas.make_spec("cube_bars", {"c": 0.6, "w": 0.2}), {})
    assert st["passed"] and st["used"] == [32, 48, 64] and st["verdict"]["verdict"] == "certified"
