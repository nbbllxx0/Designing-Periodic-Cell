"""BoTorch search tool and atlas oracle on a synthetic evaluator (no solver): the mechanics, not the physics."""
import numpy as np

import amm  # noqa: F401
from amm import atlas, search

NO_ERR = {f: {} for f in ("tpms", "struts", "resonator")}
DOM = {"tpms:network": {"density": 0.0}, "tpms:sheet": {"density": 0.0}, "struts": {"r": 0.0}, "resonator": {"w": 0.0}}


def fake_eval(specs):
    """Smooth synthetic properties: E100 peaks at cube_bars c = 0.6, w = 0.25; other kinds are soft."""
    rows = []
    for s in specs:
        p = s["params"]
        if s["kind"] == "cube_bars":
            e = 0.05 * np.exp(-((p["c"] - 0.6) ** 2 + (p["w"] - 0.25) ** 2) / 0.01)
        else:
            e = 0.002
        rows.append(dict(spec=s, valid=True, density=0.2, E100=float(e), G=0.01, bulk=0.01, nu100=0.3,
                         bloch_valid=False, bands=None))
    return rows


def test_search_finds_the_narrow_feasible_region():
    r = search.search({"E100_min": 0.04}, families=["resonator"], budget=40, q=8, evaluator=fake_eval,
                      err=NO_ERR, domain=DOM, objective="nominal", n_cand=512)
    assert r["found"] and r["best"][0]["spec"]["kind"] == "cube_bars"
    p = r["best"][0]["spec"]["params"]
    assert abs(p["c"] - 0.6) < 0.08 and abs(p["w"] - 0.25) < 0.08
    assert r["n_evaluations"] == 40


def test_search_reports_not_found_for_an_unreachable_target():
    r = search.search({"E100_min": 0.08}, families=["resonator"], budget=24, q=8, evaluator=fake_eval,
                      err=NO_ERR, domain=DOM, objective="nominal", n_cand=256)
    assert not r["found"] and r["best"][0]["slack_nominal"] < 0


def test_search_proposals_respect_validity():
    r = search.search({"E100_min": 0.04}, families=["struts", "resonator"], budget=24, q=8, evaluator=fake_eval,
                      err=NO_ERR, domain=DOM, objective="nominal", max_arms=5, n_cand=256)
    for h in r["history"]:
        assert atlas.valid(h["spec"]["kind"], h["spec"]["params"])


def test_oracle_uses_the_error_ranges():
    rows = fake_eval([atlas.make_spec("cube_bars", dict(c=0.6, w=0.25))])  # E100 = 0.05
    err = {"resonator": {"E100": [0.0, 0.25]}}  # true E100 in [0.04, 0.05]
    assert atlas.oracle(rows, {"E100_min": 0.039}, err, domain=DOM)["verdict"] == "FEASIBLE"
    assert atlas.oracle(rows, {"E100_min": 0.045}, err, domain=DOM)["verdict"] == "BORDERLINE"
    assert atlas.oracle(rows, {"E100_min": 0.051}, err, domain=DOM)["verdict"] == "NOT_FOUND_IN_FAMILIES"


def test_gap_slack_pessimistic_and_optimistic():
    bands = np.array([[0.1, 0.2, 0.5], [0.15, 0.25, 0.6]])  # one gap between 0.25 and 0.5
    row = dict(spec=atlas.make_spec("cube_bars", dict(c=0.6, w=0.2)), valid=True, bloch_valid=True, bands=bands)
    t = {"gap": {"f_lo": 0.3, "f_hi": 0.45}}
    err = {"gap_lo": [0.0, 0.1], "gap_hi": [0.0, 0.2]}
    n, p, o = (atlas.slacks(row, t, err, c)["gap"] for c in ("nominal", "pess", "opt"))
    assert np.isclose(n, 0.05 / 0.375) and p < n <= o
