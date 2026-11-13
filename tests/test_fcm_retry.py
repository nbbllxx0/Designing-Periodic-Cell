"""Regression: a partial voxel with one or two solid sub-samples has a rank-6 midpoint stiffness; when no other element
touches its corner nodes, K is singular and PARDISO fails (error -4). Found in the G2 re-run on iwp 0.15 network,
n = 48, grid phase 0.125. certify._static_row retries with the finite-cell stiffness floor (fem.build_mesh
fcm_alpha) and records it; the floor changes healthy solves by < 1e-8 relative (results/g2/NOTES.md)."""
import numpy as np
import pytest

import amm  # noqa: F401
from amm import certify, fem, geometry, homog

SPEC = {"family": "tpms", "kind": "iwp", "params": {"density": 0.15, "mode": "network"}}


def test_singular_partial_voxel_is_retried_with_the_fcm_floor():
    cov, sub, _ = geometry.design_cell(SPEC, 48, phase=0.125)
    with pytest.raises(Exception):
        homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=0.3))
    row = certify._static_row(SPEC, 48, 0.3, {}, {}, phase=0.125)
    assert row["numerics_ok"] and row["fcm_alpha"] == certify.FCM_ALPHA and row["factor_perturbed"] == 0


def test_fcm_floor_leaves_a_healthy_solve_unchanged():
    cov, sub, _ = geometry.design_cell(SPEC, 32, phase=0.25)
    a = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=0.3))
    b = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=0.3, fcm_alpha=certify.FCM_ALPHA))
    for q in ("E100", "G", "bulk"):
        assert abs(b[q] / a[q] - 1) < 1e-7
    assert np.isclose(a["density"], b["density"])
