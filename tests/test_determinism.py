"""Bit-reproducibility needed for exact replay of agent sessions (amm.tools.replay)."""
import amm
from amm import atlas, evaluate


def test_mkl_runs_in_strict_reproducible_mode():
    assert amm.MKL_CBWR_STATUS == 0x10002  # MKL_CBWR_AUTO | MKL_CBWR_STRICT


def test_search_tier_is_bit_identical_across_batches():
    d = atlas.make_spec("sphere_ligaments", {"c": 0.232985, "w": 0.060785})
    o = [atlas.make_spec("cube_bars", {"c": 0.6, "w": 0.2})]
    rows = [[x for x in evaluate.evaluate_batch(b, nu=0.3, **atlas.SEARCH_TIER) if x["spec"] == d][0]
            for b in ([d], o + [d], [d])]
    for r in rows[1:]:
        assert r["gaps"] == rows[0]["gaps"] and r["E100"] == rows[0]["E100"]
