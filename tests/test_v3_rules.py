"""Rules added after the third audit round (2026-11-09): the gap guard no longer reads a monotone drift toward the
claim as phase noise, and a certificate needs the load-path feature resolved by FEATURE_MIN_VOXELS voxels."""
import numpy as np

import amm  # noqa: F401
from amm import bloch, certify, geometry as G

NS = [20, 30, 40]
PH = [0.600, 0.610]  # phase spread P = 0.01


def test_drift_toward_the_claim_is_not_phase_noise():
    # upper edge falling by 0.006 then 0.0058: steps within 2P but no admissible order (p < 0.25)
    f = [0.6118, 0.6058, 0.6000]
    safe, info = bloch._edge_guard(NS, f, PH, bloch.CONVERGENCE_SAFETY, "hi")
    assert safe is None and info["drift_toward_claim"]
    # the same drift on the lower edge moves away from the claim: bounded by the computed values
    safe, info = bloch._edge_guard(NS, f, PH, bloch.CONVERGENCE_SAFETY, "lo")
    assert safe is not None and safe >= max(f) and not info["drift_toward_claim"]


def test_non_monotone_noise_is_still_bounded_by_the_phase_spread():
    f = [0.6050, 0.5990, 0.6030]
    safe, info = bloch._edge_guard(NS, f, PH, bloch.CONVERGENCE_SAFETY, "hi")
    assert safe is not None and abs(safe - (0.6030 - 2 * 0.01)) < 1e-12 and not info["drift_toward_claim"]


def test_convergent_drift_toward_the_claim_still_uses_the_order_fit():
    h = 1 / np.array(NS, float)
    f = list(0.55 + 0.4 * h)  # p = 1 exactly
    safe, info = bloch._edge_guard(NS, f, PH, bloch.CONVERGENCE_SAFETY, "hi")
    assert safe is not None and abs(info["p"] - 1) < 1e-6 and info["drift_toward_claim"]


def test_feature_size_is_exact_for_parametric_families_and_close_numerically():
    for spec, size in ((dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.06)), 0.06),
                       (dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.3, w=0.1)), 0.1),
                       (dict(family="struts", kind="bcc", params=dict(r=0.06, R=0.22)), 0.12)):
        assert G.thinnest_feature(spec)["size"] == size
        sub, _ = G._fine_coverage(spec["family"], spec["kind"], 128, nf=128, **spec["params"])
        assert abs(G._bottleneck(sub >= 0.5) - size) <= 1.5 / 128  # the numeric route agrees within ~1 voxel


def test_feature_rule_withholds_a_certificate_and_keeps_a_refutation():
    thin = dict(family="resonator", kind="cube_bars", params=dict(c=0.787, w=0.06))
    f = certify.feature_check(thin, 40)
    assert not f["passed"] and abs(f["voxels"] - 2.4) < 1e-9
    assert certify.feature_check(thin, 64)["passed"]
    v = certify._withhold(dict(verdict="certified", targets={"E100_min": "certified"}), f)
    assert v["verdict"] == "undetermined" and v["targets"]["E100_min"] == "undetermined" and "voxels" in v["reason"]
    assert certify._withhold(dict(verdict="refuted"), f)["verdict"] == "refuted"


def test_order_fit_is_judged_in_h_not_on_raw_steps():
    # n = 30, 40, 60 has equal h-increments: a first-order sequence has equal raw steps and p < 1 growing steps.
    # Both are admissible orders (confirm audit 2026-11-10); the raw-step test used to reject them.
    ns = [30, 40, 60]
    h = 1 / np.array(ns, float)
    for p in (0.5, 0.93, 1.0):
        f = list(0.58 + 0.01 * h ** p)
        assert abs(bloch._order(list(h), f) - p) < 1e-6
    # the 316L filter's stored upper edges (f*, n = 30/40/60): an admissible order near 0.93
    f = [0.5792292119304038, 0.5787896180321678, 0.5783394856284751]
    p = bloch._order(list(h), f)
    assert p is not None and 0.8 < p < 1.0
    safe, info = bloch._edge_guard(ns, f, [f[-1]], bloch.CONVERGENCE_SAFETY, "hi")
    assert safe is not None and safe < f[-1] and info["drift_toward_claim"]
    # on 20/30/40 the old raw-step test was implied by p > 0: a growing raw step still has no order
    assert bloch._order([1 / 20, 1 / 30, 1 / 40], [0.70, 0.69, 0.678]) is None
