"""Seeded faults that the certificate must catch (small grids so the suite stays fast)."""
import numpy as np

import amm  # noqa: F401
from amm import bloch, certify, fem, geometry as G

# feature_min_voxels=0: these grids are far below the released feature rule (tests/test_v3_rules.py covers the rule)
FAST = dict(res_bloch=(8, 10), static_ladder=((10, 12, 14),), tol_static=0.25, as_built=False, n_path=2, n_interior=2,
            edge_res=(12,), bloch_phases=(0.5,), adversarial_n=8, feature_min_voxels=0)


def test_floating_core_is_refused_by_static_and_bloch_blocks():
    # ligaments far thinner than a voxel (coverage < C_MIN) leave a sphere with no load path
    spec = dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.3, w=0.004))
    cov, _, info = G.design_cell(spec, 10)
    assert not any(info["percolates"])
    cert = certify.certify(spec, dict(E100_min=1e-4, gap=dict(f_lo=0.3, f_hi=0.4)), **FAST)
    assert not cert["passed"]
    rows = cert["blocks"]["static"]["resolutions"]
    assert all(not r["numerics_ok"] for r in rows.values() if "numerics_ok" in r)


def test_gap_claim_true_only_at_coarse_resolution_is_refused():
    spec = dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.2))
    meshes = {}
    for n in (10, 20):
        cov, sub, _ = G.design_cell(spec, n)
        meshes[n] = fem.build_mesh(cov, sub=sub)
    # n=10 (finite-cell) gap ~[0.334, 0.769]; n=20 ~[0.321, 0.722]: a claim up to 0.75 holds only at n=10
    r = bloch.certify_gap(meshes, 0.36, 0.75, n_path=2, n_interior=2)
    assert r["resolutions"][10]["passed"] and not r["resolutions"][20]["passed"] and not r["passed"]


def test_overstated_stiffness_is_refused_and_honest_claim_passes():
    spec = dict(family="tpms", kind="schwarz_p", params=dict(density=0.3, mode="network"))
    honest = certify.certify(spec, dict(density_max=0.31, E100_min=0.01), **FAST)
    assert honest["passed"], honest["blocks"]["static"]
    E = min(r["E100"] for r in honest["blocks"]["static"]["resolutions"].values())
    over = certify.certify(spec, dict(density_max=0.31, E100_min=1.2 * E), **FAST)
    assert not over["passed"]
    assert any("E100_min" in f for r in over["blocks"]["static"]["resolutions"].values() for f in r["checks_failed"])


def test_density_claim_violation_is_refused():
    spec = dict(family="tpms", kind="gyroid", params=dict(density=0.3, mode="network"))
    cert = certify.certify(spec, dict(density_max=0.25), **FAST)
    assert not cert["passed"]


def test_gap_claim_inside_both_resolutions_but_beyond_converged_edge_is_refused():
    # edges drifting down with resolution (Lucklum 2018 cell, n = 20 / 30, f a / c_l): counts alone accept 0.478
    edges = {20: (0.0488, 0.4806), 30: (0.0470, 0.4785)}
    over = bloch.gap_convergence(edges, 0.05, 0.478)
    assert not over["passed"] and abs(over["safe_interval"][1] - 0.4701) < 2e-4  # paper: 0.4702
    assert bloch.gap_convergence(edges, 0.05, 0.46)["passed"]
    assert not bloch.gap_convergence(edges, 0.048, 0.46)["passed"]  # below the coarse lower edge


def test_edge_estimate_matches_inertia_counts():
    spec = dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.2))
    cov, sub, _ = G.design_cell(spec, 10)
    ic = bloch.InertiaCounter(fem.build_mesh(cov, sub=sub))
    k = np.array([np.pi, 0.0, 0.0])
    for side in ("below", "above"):
        e = ic.edge(k, 0.5, side)
        lo, hi = ic.counts(k, [e - 1e-6, e + 1e-6])
        assert hi["below"] == lo["below"] + 1  # the estimated edge is an eigenvalue, located to 1e-6
        assert ic.counts(k, [0.5])[0]["below"] == (hi["below"] if side == "below" else lo["below"])  # nearest one
    ic.free()


def _vals(seq):
    return {n: {q: v for q in certify.STATIC_QUANTITIES} for n, v in seq.items()}


def test_static_claim_between_converged_value_and_coarse_values_is_refused():
    # Schwarz P network 0.25 (G2 run): E100 relative to the converged reference at n = 32, 48, 64
    conv = certify.static_convergence(_vals({32: 1.012, 48: 1.006, 64: 1.004}))
    assert conv["converged"]
    assert certify._guarded_checks(conv, dict(E100_min=1.003))  # above the converged value: refused
    assert not certify._guarded_checks(conv, dict(E100_min=0.98))  # honest claim (2 % below): accepted


def test_non_monotone_static_convergence_is_not_extrapolated():
    # thin SC struts (r = 0.06a, G2 run): E100 at n = 48, 64, 80 is +4.4 %, +5.1 %, +4.1 % off the reference
    conv = certify.static_convergence(_vals({48: 1.044, 64: 1.051, 80: 1.041}))
    assert not conv["converged"] and conv["quantities"]["E100"]["mode"] == "not converged"


def test_cut_voxel_bias_is_bounded_by_grid_phase_means():
    # cube_bars c = 0.7, w = 0.15 (G2 cell; results/g2/phase_ladder/): shear modulus G at grid phases 0, 1/8, 1/4,
    # 3/8, 1/2 voxel. At phase 0, n = 32, 48, 64 looks converged (last change 1 %), but the bar faces cut the voxels
    # at every one of these n; the aligned grid n = 80 gives 0.0033984, and the phase means extrapolate to ~0.0032.
    G_ = {32: [0.0042622, 0.0041849, 0.0039694, 0.0039064, 0.0039525],
          48: [0.0036919, 0.0037029, 0.0037451, 0.0037701, 0.0038288],
          64: [0.003651, 0.0036142, 0.0035785, 0.0035686, 0.0035864]}
    claim = dict(G_min=0.0034)  # above a computed value (n = 80, phase 0): false, since G converges from above
    phase0 = certify.static_convergence(_vals({n: v[0] for n, v in G_.items()}), p_max=2.0)
    assert phase0["converged"] and not certify._guarded_checks(phase0, claim)  # one phase, order up to 2: accepts
    phased = certify.static_convergence({n: [_vals({0: x})[0] for x in v] for n, v in G_.items()})
    assert certify._guarded_checks(phased, claim) or not phased["converged"]  # phase means: refused
    assert phased["quantities"]["G"]["lower"] < 0.0032


def test_grid_phase_keeps_density_and_zero_phase_is_unchanged():
    spec = dict(family="tpms", kind="gyroid", params=dict(density=0.25, mode="network"))
    c0, s0, i0 = G.design_cell(spec, 16)
    c1, s1, i1 = G.design_cell(spec, 16, phase=0.0)
    assert np.array_equal(c0, c1) and np.array_equal(s0, s1)
    c2, _, i2 = G.design_cell(spec, 16, phase=0.5)
    assert not np.array_equal(c0, c2) and abs(i2["density"] - i0["density"]) < 1e-3
    assert not hasattr(G, "_SHIFT")  # no module state: the phase is an argument (B3)


def test_interior_k_gap_closure_is_caught_by_the_adversarial_k_search(monkeypatch):
    # Injected fault: no cell of the G2 scan (95 cells) has a gap edge inside the zone in FP64 (results/g2/NOTES.md),
    # so the fault is seeded into the spectrum. The band below a true gap is pushed into the claim on a small ball
    # inside the irreducible wedge (radius 0.12 pi around k0, away from the path and the 10 random interior k).
    # Path + random interior sampling misses it; the GPU pattern search (adversarial_ks) finds it, and the counts
    # at the k it returns refuse the claim.
    spec = dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.2))
    cov, sub, _ = G.design_cell(spec, 10)
    mesh = fem.build_mesh(cov, sub=sub)
    f_lo, f_hi, j = 0.40, 0.70, 6  # n=10 gap ~[0.334, 0.769] above band 6
    k0, rho = np.pi * np.array([0.55, 0.35, 0.15]), 0.12 * np.pi
    bump = lambda k: 0.30 + 0.20 * (1 - (np.linalg.norm(np.asarray(k) - k0) / rho) ** 2)  # 0.5 at k0

    gpu_call, counts = bloch.GPUBands.__call__, bloch.InertiaCounter.counts

    def gpu_patched(self, ks, nev=12, chunk=None):
        f = gpu_call(self, ks, nev, chunk)
        for i, k in enumerate(ks):
            if np.linalg.norm(k - k0) < rho:
                f[i, j - 1] = max(f[i, j - 1], bump(k))
                f[i] = np.sort(f[i])
        return f

    def counts_patched(self, k, f_stars):
        out = counts(self, k, f_stars)
        if np.linalg.norm(np.asarray(k) - k0) < rho:
            for o in out:
                if bump(k) > o["f"]:  # band j-1 moved above this shift
                    o["below"] -= 1
        return out

    monkeypatch.setattr(bloch.GPUBands, "__call__", gpu_patched)
    monkeypatch.setattr(bloch.InertiaCounter, "counts", counts_patched)
    base = bloch.certify_gap({10: mesh}, f_lo, f_hi, n_path=4, n_interior=10, convergence=False)
    assert base["passed"]  # the seeded fault is invisible to path + random interior sampling
    adv = bloch.adversarial_ks(mesh, f_lo, f_hi)
    assert adv["search_edges"][0] > f_lo  # the search finds the band inside the claim
    caught = bloch.certify_gap({10: mesh}, f_lo, f_hi, n_path=4, n_interior=10, convergence=False,
                               extra_ks=adv["ks"])
    assert not caught["passed"]
