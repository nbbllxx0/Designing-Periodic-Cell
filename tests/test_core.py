"""Fast core tests (small grids). Run: <amm env python> -m pytest -q tests"""
import numpy as np
import pytest
import scipy.linalg as sl
import scipy.sparse as sp

import amm  # noqa: F401  (import-order guard for MKL before torch)
from amm import bloch, fem, geometry as G, homog


def test_solid_cell_returns_material_tensor():
    r = homog.homogenize(np.ones((6, 6, 6), bool))
    D = fem.elastic_D(1.0, 0.3)
    assert np.linalg.norm(r["C"] - D) / np.linalg.norm(D) < 1e-12
    assert r["max_residual"] < 1e-10


def test_gyroid_tensor_symmetric_cubic_and_below_voigt():
    m, info = G.clean(G.tpms("gyroid", 16, density=0.3))
    assert all(info["percolates"])
    r = homog.homogenize(m)
    assert r["asymmetry"] < 1e-12 and r["max_residual"] < 1e-10
    assert r["cubic_deviation"] < 0.02
    D = fem.elastic_D(1.0, 0.3)
    assert np.all(np.linalg.eigvalsh(r["density"] * D - r["C"]) > -1e-12)  # Voigt bound


@pytest.mark.parametrize("spec", [("resonator", "cube_bars", dict(c=0.6, w=0.2)),
                                  ("struts", "octet", dict(r=0.07, R=0.0)),
                                  ("resonator", "sphere_ligaments", dict(c=0.3, w=0.15))])
def test_density_matched_across_resolutions(spec):
    fam, kind, p = spec
    rhos = [G.make(fam, kind, n, **p).mean() for n in (10, 20, 32, 48)]
    assert max(rhos) - min(rhos) < 0.005


def test_percolation_detects_floating_inclusion():
    m = np.zeros((10, 10, 10), bool)
    m[3:7, 3:7, 3:7] = True
    assert G.percolates(m) == [False, False, False]
    assert all(G.percolates(G.struts("sc", 12, r=0.15)))


def test_real2n_upper_matches_block_matrix():
    mesh = fem.build_mesh(G.resonator("cube_bars", 6, c=0.5, w=0.34))
    k = np.array([0.7, -0.3, 1.1])
    H = mesh.assemble("K", k)
    R = sp.bmat([[H.real, -H.imag], [H.imag, H.real]])
    ref = sp.triu(R).toarray()
    got = mesh.real2n_upper(mesh.csr_data(mesh.element_values("K", k))).toarray()
    assert np.allclose(got, ref)


def test_inertia_counts_match_dense_eigenvalues():
    cov, sub, _ = G.design_cell(dict(family="resonator", kind="cube_bars", params=dict(c=0.5, w=0.25)), 8)
    mesh = fem.build_mesh(cov, sub=sub)
    ic = bloch.InertiaCounter(mesh)
    for k in (np.zeros(3), np.array([np.pi, 0.4, 0.1]), np.array([1.0, 1.0, 0.5])):
        w = sl.eigh(mesh.assemble("K", k).toarray(), mesh.assemble("M", k).toarray(), eigvals_only=True)
        f = np.sqrt(np.clip(w, 0, None)) / (2 * np.pi * bloch.c_t())
        tests = [0.05, 0.2, 0.4, 0.6]
        for fs, c in zip(tests, ic.counts(k, tests)):
            if np.min(np.abs(f - fs)) > 1e-6:
                assert c["below"] == int((f < fs).sum()) and c["perturbed"] == 0
    ic.free()


def _dense_bands(mesh, ks, nev=10):
    out = []
    for k in ks:
        w = sl.eigh(mesh.assemble("K", k).toarray(), mesh.assemble("M", k).toarray(), eigvals_only=True)[:nev]
        out.append(np.sqrt(np.clip(w, 0, None)) / (2 * np.pi * bloch.c_t()))
    return np.array(out)


def test_gap_certificate_accepts_inside_and_rejects_too_wide():
    cov, sub, _ = G.design_cell(dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.2)), 8)
    mesh = fem.build_mesh(cov, sub=sub)
    ks = np.vstack([bloch.kpath(2)[0], bloch.ibz_interior(3, 0)])
    g = bloch.gaps(_dense_bands(mesh, ks))[0]
    lo, hi = g["f_lo"], g["f_hi"]
    ok = bloch.certify_gap({8: mesh}, lo + 0.1 * (hi - lo), hi - 0.1 * (hi - lo), n_path=2, n_interior=3)
    bad = bloch.certify_gap({8: mesh}, lo + 0.1 * (hi - lo), hi + 0.1 * (hi - lo), n_path=2, n_interior=3)
    assert ok["passed"] and ok["claim"]["below_band"] == g["below_band"]
    assert not bad["passed"]


def test_coverage_density_matches_exact_volume():
    # cube core c^3 plus three bars w^2 outside the core: 3 * w^2 * (1 - c) ; exact union volume
    c, w = 0.6, 0.2
    exact = c**3 + 3 * w**2 * (1 - c) - 0.0
    for n in (10, 20, 32):
        assert abs(G.resonator("cube_bars", n, c=c, w=w).mean() - exact) < 2e-3


@pytest.mark.skipif(not __import__("torch").cuda.is_available(), reason="no CUDA")
def test_gpu_bands_match_cpu_dense():
    cov, sub, _ = G.design_cell(dict(family="resonator", kind="cube_bars", params=dict(c=0.5, w=0.25)), 8)
    mesh = fem.build_mesh(cov, sub=sub)
    ks, _ = bloch.kpath(2)
    f_gpu = bloch.GPUBands(mesh)(ks, nev=10)
    for i, k in enumerate(ks):
        w = sl.eigh(mesh.assemble("K", k).toarray(), mesh.assemble("M", k).toarray(), eigvals_only=True)[:10]
        f = np.sqrt(np.clip(w, 0, None)) / (2 * np.pi * bloch.c_t())
        assert np.max(np.abs(f[3:] - f_gpu[i, 3:])) < 5e-4


def test_finite_cell_solid_and_patch():
    # full cell through the finite-cell path (all sub-samples solid) must reproduce the material tensor
    n, s = 4, 3
    sub = np.ones((n, s, n, s, n, s))
    cov = np.full((n, n, n), 0.999999)  # force the partial-voxel branch
    r = homog.homogenize(cov, sub=sub)
    D = fem.elastic_D()
    assert np.linalg.norm(r["C"] - D) / np.linalg.norm(D) < 1e-3  # midpoint rule vs hex8i full elements


def test_fcm_reduces_alignment_bias_vs_voigt_voxels():
    # grid-aligned (n=20) vs non-aligned (n=16): finite-cell partial voxels disagree less than coverage scaling
    spec = dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.2))
    fcm, voigt = {}, {}
    for n in (16, 20):
        cov, sub, _ = G.design_cell(spec, n)
        fcm[n] = homog.homogenize(cov, sub=sub)["G"]
        voigt[n] = homog.homogenize(cov)["G"]
    d_fcm = abs(fcm[16] - fcm[20]) / fcm[20]
    d_voigt = abs(voigt[16] - voigt[20]) / voigt[20]
    assert d_fcm < 0.75 * d_voigt


def test_to_ibz_preserves_bloch_spectrum():
    # the cubic point group plus time reversal map any k into the wedge without changing the eigenvalues
    from amm import bloch, fem, geometry as G
    cov, sub, _ = G.design_cell(dict(family="tpms", kind="schwarz_p", params=dict(density=0.3, mode="network")), 8)
    ic = bloch.InertiaCounter(fem.build_mesh(cov, sub=sub))
    k = np.array([-0.3, 2.9, 1.1]) * np.pi  # outside the first zone, unordered, negative component
    w = bloch.to_ibz(k)
    assert np.all(np.diff(w) <= 0) and w.min() >= 0 and w.max() <= np.pi
    fs = [0.2, 0.5, 0.8, 1.1]
    assert [c["below"] for c in ic.counts(k, fs)] == [c["below"] for c in ic.counts(w, fs)]
    ic.free()
