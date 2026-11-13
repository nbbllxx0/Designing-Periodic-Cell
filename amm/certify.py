"""Release certificates. Computed by the solvers only; the agent layer can read a certificate but never write one.

A design is a `spec` = {"family", "kind", "params"} (see `geometry`). A request's `targets` may contain:

    density_max, density_min                       solid fraction
    E100_min, E100_max, G_min, bulk_min            normalized by E_s
    nu100_min, nu100_max                           Poisson ratio along [100]
    gap: {"f_lo": .., "f_hi": ..}                  complete-gap interval in f* = f a / c_t

Static block. Resolution triples are tried in order (default (32, 48, 64), (48, 64, 80), then (64, 80, 96)). Every
resolution is solved at grid phases 0, 1/8, 1/4, 3/8 and 1/2 voxel (the periodic cell translated by a fraction of a
voxel; the spread over phases is pure discretization error from where surfaces cut the voxels, several % for
flat-faced resonators and thin struts). Per quantity, the phase means are extrapolated with an order fitted through
the three resolutions (capped at 1) and the bound is moved out by twice the estimated remaining error
(`static_convergence`). The first rung that converges (remaining error and phase spread <= `tol_static`) and whose
guarded bounds meet every target is used; otherwise the next rung is tried, and the design is refused if none
qualifies. Checks: FP64 residual <= 1e-10 for all six load cases, |C - C^T| / |C| <= 1e-10, C positive definite (min
eigenvalue > 1e-8), percolation in x, y and z, at most 1% of solid removed as islands, and every static target
against the guarded bounds. Stiffness converges from above, slowly (about O(h)) for resonators, and a single-phase
sequence can look converged while missing a cut-voxel bias of several percent (results/g2/NOTES.md).
Bloch block (counted resolutions 20 and 30): `bloch.certify_gap` (inertia counts) on the irreducible-zone path,
random interior samples and the worst-case interior k found by the GPU pattern search on a coarse mesh
(`bloch.adversarial_ks`, n = 10); the densities of the two resolutions agree. Discretization guard
(`bloch.gap_convergence`): the edges are also computed at n = 40 (Lanczos at the two most extreme k of n = 30)
and at grid phases 0.25 and 0.5 at n = 30. The convergence order is fitted per edge (capped at 2; slower than
0.25, or non-monotone beyond the phase noise, fails closed; a drift toward the claim that fits no order also fails
closed), the extrapolated edge is moved inward by twice the estimated remaining error, and the phase extremes by
twice the phase spread. The claim must lie inside.
Feature resolution (both blocks): the finest resolution of the block must put at least FEATURE_MIN_VOXELS = 3
voxels across the load-path feature (`geometry.thinnest_feature`: bar width, strut diameter, or the TPMS
bottleneck); otherwise the static ladder skips to a finer rung, and on the last rung, or in the Bloch block (finest
n = 40), a certified verdict becomes undetermined.
As-built block (robustness flag, not required for release): the static targets and the gap counts after the
surface is offset by -/+ `as_built_offset` (fraction of the cell edge; 0.01 = 0.1 mm on a 10 mm cell).
All blocks use finite-cell partial voxels (`fem.build_mesh(cov, sub)`).
"""
from __future__ import annotations

import hashlib
import json
import time

import numpy as np

from . import bloch, fem, geometry, homog
from .progress import checkpoint

STATIC_KEYS = {"density_max": ("density", "max"), "density_min": ("density", "min"),
               "E100_min": ("E100", "min"), "E100_max": ("E100", "max"), "G_min": ("G", "min"),
               "bulk_min": ("bulk", "min"), "nu100_min": ("nu100", "min"), "nu100_max": ("nu100", "max")}


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def _mesh(spec: dict, n: int, nu: float, offset_voxels: float = 0.0, phase: float = 0.0):
    cov, sub, info = geometry.design_cell(spec, n, offset_voxels=offset_voxels, phase=phase)
    if info["n_components"] == 0:
        return None, info
    return fem.build_mesh(cov, sub=sub, nu=nu), info


def _static_checks(r: dict, targets: dict) -> list[str]:
    fails = []
    for key, (q, kind) in STATIC_KEYS.items():
        if key in targets:
            v, t = r[q], targets[key]
            if (kind == "min" and v < t) or (kind == "max" and v > t):
                fails.append(f"{key}: {q}={v:.5g} vs {t}")
    return fails


def _static_row(spec, n, nu, targets, cache, phase=0.0):
    key = n if phase == 0.0 else (n, phase)
    if key not in cache:
        checkpoint("certificate: static solve", n=int(n), phase=float(phase), solved=len(cache))
        cov, sub, info = geometry.design_cell(spec, n, phase=phase)
        if info["n_components"] == 0:
            cache[key] = dict(numerics_ok=False, checks_failed=["empty geometry"])
            return cache[key]
        if not all(info["percolates"]):  # fail closed: no load path, K is singular beyond the pinned node
            cache[key] = dict(numerics_ok=False, checks_failed=[f"does not percolate {info['percolates']}"],
                              density=info["density"], percolates=info["percolates"])
            return cache[key]
        alpha = 0.0
        for alpha in (0.0, FCM_ALPHA):  # retry with the finite-cell stiffness floor (fem.build_mesh) on failure
            try:
                r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=nu, fcm_alpha=alpha))
                break
            except Exception as e:  # any solver failure is a refusal, never a crash
                err = e
        else:
            cache[key] = dict(numerics_ok=False, checks_failed=[f"solver error: {err}"], density=info["density"])
            return cache[key]
        r.pop("C")
        r["fcm_alpha"] = alpha
        r.update(removed_fraction=info["removed_fraction"], n_components=info["n_components"],
                 percolates=info["percolates"], phase=phase)
        r["checks_failed"] = _static_checks(r, targets)
        r["numerics_ok"] = bool(r["max_residual"] <= 1e-10 and r["asymmetry"] <= 1e-10 and r["min_eig"] > 1e-8
                                and r["factor_perturbed"] == 0 and r["removed_fraction"] <= 0.01
                                and all(r["percolates"]))
        cache[key] = r
    return cache[key]


def _geometry_invalid(rows) -> bool:
    """True when a static row failed for a geometric reason (no solid, no load path, floating material), as
    opposed to a solver failure."""
    for r in rows:
        f = " ".join(r.get("checks_failed") or [])
        if "empty geometry" in f or "does not percolate" in f:
            return True
        if "percolates" in r and not all(r["percolates"]):
            return True
        if r.get("removed_fraction", 0.0) > 0.01:
            return True
    return False


FCM_ALPHA = 1e-8  # finite-cell stiffness floor for the retry; changes healthy solves by < 1e-8 (results/g2/NOTES.md)
STATIC_QUANTITIES = ("density", "E100", "G", "bulk", "nu100")
STATIC_SAFETY = 2.0  # same factor as bloch.CONVERGENCE_SAFETY; see results/g2/NOTES.md
STATIC_P_MAX = 1.0  # static phase means: fitted order capped at 1 (held-out calibration, results/g2/NOTES.md)
STATIC_PHASES = (0.125, 0.25, 0.375, 0.5)  # extra grid phases (voxel widths), at every resolution of the rung
FEATURE_MIN_VOXELS = 3.0  # voxels the finest resolution of a block must put across the load-path feature


def feature_check(spec: dict, n: int, min_voxels: float = FEATURE_MIN_VOXELS, _cache: dict = {}) -> dict:
    """Feature resolution of a block whose finest resolution is n: the load-path feature
    (`geometry.thinnest_feature`) must span at least `min_voxels` voxels. Below it the three-resolution guard is
    fitted outside the regime where the feature is resolved, and a certificate is withheld (audit round 3,
    2026-11-09: the 316L filter certificate rested on bars 1.2-2.4 voxels wide at n = 20-40)."""
    key = spec_hash(spec)
    if key not in _cache:
        _cache[key] = geometry.thinnest_feature(spec)
    f = _cache[key]
    vox = f["size"] * n
    return dict(size=f["size"], method=f["method"], n=int(n), voxels=float(vox), min_voxels=float(min_voxels),
                passed=bool(vox >= min_voxels))


def _withhold(verdict: dict, feat: dict) -> dict:
    """A certified verdict becomes undetermined when the feature is not resolved; refutations stand."""
    why = (f"load-path feature {feat['size']:.4g} a spans {feat['voxels']:.2f} voxels at n = {feat['n']} "
           f"(< {feat['min_voxels']:g}): raise the resolution")
    out = dict(verdict)
    if "targets" in out:
        out["targets"] = {k: ("undetermined" if v == "certified" else v) for k, v in out["targets"].items()}
    if out.get("verdict") == "certified":
        out.update(verdict="undetermined", reason=why)
    out["feature"] = feat
    return out


def static_convergence(vals: dict, phase_vals=None, safety: float = STATIC_SAFETY, tol: float = 0.05,
                       flat: float = 1e-3, p_max: float = STATIC_P_MAX) -> dict:
    """Discretization guard for static quantities over three resolutions n1 < n2 < n3 (h = 1/n).

    vals {n: value dict} or {n: [value dicts, one per grid phase]} (the cell re-voxelized after a translation by a
    fraction of a voxel; the cell is periodic, so the spread over phases is pure discretization error from where
    surfaces cut the voxels). Per quantity, m(n) = mean over phases and P = spread at n3. Phase means converge
    smoothly where single-phase sequences jump with the cut pattern (results/g2/NOTES.md).
      * m monotone and an order p in [0.25, 8] fits the three means (the order equation in h; capped at STATIC_P_MAX = 1;
        resonators converge at about h^0.5-1, and a three-point fit can read p > 1 early),
        ext = m3 + d23 r, remaining error e = |d23| r, r = h3^p / (h2^p - h3^p);
      * otherwise, if every change is negligible (< `flat`) or within the phase noise (|d12|, |d23| <= safety P):
        ext = m3, e = max(|d23|, P);
      * otherwise not converged.
    Converged when e and P are within `tol` (relative; absolute for nu100). Bounds: lower = min(all values,
    ext - safety e), upper = max(all values, ext + safety e). Static minima are checked against `lower`, maxima
    against `upper`. `phase_vals` (legacy): extra phase dicts at n3 only; prefer phases at every resolution."""
    from .bloch import _order

    ns = sorted(vals)[-3:]
    rows = {n: (vals[n] if isinstance(vals[n], list) else [vals[n]]) for n in ns}
    if phase_vals:
        rows[ns[-1]] = rows[ns[-1]] + list(phase_vals)
    h = [1 / n for n in ns]
    out, ok = {}, True
    for q in STATIC_QUANTITIES:
        per = [[r[q] for r in rows[n]] for n in ns]
        m = [float(np.mean(v)) for v in per]
        allv = [x for v in per for x in v]
        P = max(per[-1]) - min(per[-1])
        scale = 1.0 if q == "nu100" else max(abs(m[-1]), 1e-12)
        d12, d23 = m[1] - m[0], m[2] - m[1]
        p = _order(h, m)
        if p is not None:
            pu = min(p, p_max)
            r = h[2] ** pu / (h[1] ** pu - h[2] ** pu)
            ext, err, mode = m[2] + d23 * r, abs(d23) * r, "order-fit"
        elif (abs(d12) / scale <= flat and abs(d23) / scale <= flat) or                 (P > 0 and abs(d12) <= safety * P and abs(d23) <= safety * P):
            ext, err, mode = m[2], max(abs(d23), P), "noise"
        else:
            ext, err, mode = m[2], None, "not converged"
        conv = bool(err is not None and err / scale <= tol and P / scale <= tol)
        e = err if err is not None else abs(d23)
        out[q] = dict(means=m, values=per, phase_spread=P, p=p, mode=mode, extrapolated=ext, remaining=err,
                      converged=conv, lower=min(*allv, ext - safety * e), upper=max(*allv, ext + safety * e))
        ok &= conv
    return dict(resolutions=ns, n_phases=[len(rows[n]) for n in ns], converged=bool(ok), quantities=out,
                safety=safety)


def _guarded_checks(conv: dict, targets: dict) -> list[str]:
    fails = []
    for key, (q, kind) in STATIC_KEYS.items():
        if key in targets:
            b = conv["quantities"][q]
            v, t = (b["lower"], targets[key]) if kind == "min" else (b["upper"], targets[key])
            if (kind == "min" and v < t) or (kind == "max" and v > t):
                fails.append(f"{key}: guarded {'lower' if kind == 'min' else 'upper'} {q}={v:.5g} vs {t}")
    return fails


FROM_ABOVE = ("E100", "G", "bulk")  # stiffness converges from above (results/g2/NOTES.md, results/atlas/NOTES.md)


def static_verdict(quantities: dict | None, targets: dict, numerics_ok: bool = True,
                   invalid_geometry: bool = False) -> dict:
    """Three-way verdict per static target from the guard's bounds (`static_convergence(...)["quantities"]`).

    certified    the guarded bound clears the target (min: lower >= t; max: upper <= t), quantity converged;
    refuted      the opposite guarded bound misses it (min: upper < t; max: lower > t). Needs a converged quantity,
                 except a minimum on E100 / G / bulk: these converge from above, so the largest computed value
                 (always inside `upper`) bounds the limit even before convergence;
    undetermined otherwise: the target lies inside the guard band. Not a refusal of a true claim, an abstention.
    Failed numerics: an invalid geometry (empty, not percolating, or > 1 % of the solid in floating parts) refutes
    the design, since it is not a load-bearing solid; a solver failure (factorization error, residual, asymmetry or
    a near-singular stiffness) is undetermined: it says nothing about the physical design (audit F05, 2026-11-06)."""
    if not numerics_ok or not quantities:
        if invalid_geometry:
            st = {k: "refuted" for k in targets if k in STATIC_KEYS}
            return dict(verdict="refuted", targets=st, reason="invalid_geometry",
                        note="the design is not a connected load-bearing solid")
        st = {k: "undetermined" for k in targets if k in STATIC_KEYS}
        return dict(verdict="undetermined", targets=st, reason="numerical_failure",
                    note="the solver failed its checks: neither proven nor disproven")
    st = {}
    for key, (q, kind) in STATIC_KEYS.items():
        if key not in targets:
            continue
        b, t = quantities[q], targets[key]
        conv = bool(b.get("converged"))
        if kind == "min":
            if conv and b["lower"] >= t:
                st[key] = "certified"
            elif b["upper"] < t and (conv or q in FROM_ABOVE):
                st[key] = "refuted"
            else:
                st[key] = "undetermined"
        else:
            if conv and b["upper"] <= t:
                st[key] = "certified"
            elif conv and b["lower"] > t:
                st[key] = "refuted"
            else:
                st[key] = "undetermined"
    vals = set(st.values())
    v = "refuted" if "refuted" in vals else ("undetermined" if "undetermined" in vals else "certified")
    return dict(verdict=v, targets=st)


def gap_verdict(report: dict) -> dict:
    """Three-way verdict of a gap claim from a `bloch.certify_gap` report.

    certified    the report passed (counts at every resolution and k, edge guard);
    refuted      the guarded edges exclude the claim: the lower edge's lower bound min(computed, ext - s e) lies above
                 f_lo, or the upper edge's upper bound max(computed, ext + s e) lies below f_hi;
    undetermined otherwise, including every case where counts fail at some k. Edges converge from above, so a
                 mode inside the claimed interval on a finite mesh does not prove the converged gap closed (its band
                 index is not known), and a failed count is an abstention, not a refutation.
    A solver failure or empty geometry is reported as undetermined with its reason (fail closed, no claim made)."""
    if report.get("passed"):
        return dict(verdict="certified")
    c = report.get("convergence")
    claim = report.get("claim") or {}
    if (c and claim and (c.get("lower_edge") or {}).get("extrapolated") is not None
            and (c.get("upper_edge") or {}).get("extrapolated") is not None):
        s = c.get("safety", 2.0)
        edges = list((c.get("edges") or {}).values()) + list(c.get("phase_edges") or [])
        lo, hi = c["lower_edge"], c["upper_edge"]
        lo_e = lo.get("remaining") or 0.0
        hi_e = hi.get("remaining") or 0.0
        lo_lower = min([e[0] for e in edges] + [lo["extrapolated"] - s * lo_e])
        hi_upper = max([e[1] for e in edges] + [hi["extrapolated"] + s * hi_e])
        if lo_lower > claim["f_lo"]:
            return dict(verdict="refuted", reason=f"lower edge >= {lo_lower:.5g} > f_lo {claim['f_lo']:.5g}")
        if hi_upper < claim["f_hi"]:
            return dict(verdict="refuted", reason=f"upper edge <= {hi_upper:.5g} < f_hi {claim['f_hi']:.5g}")
    res = report.get("resolutions") or {}
    for side, name in (("lower_edge", "lower"), ("upper_edge", "upper")):
        e = (c or {}).get(side) or {}
        if e.get("reason") and not any((r or {}).get("n_failures") for r in res.values()):
            return dict(verdict="undetermined", reason=f"no safe {name} edge: {e['reason']}")
    if res and all((r or {}).get("n_failures") for r in res.values()):
        # modes inside the interval at every resolution: evidence against the claim, not a proof (see above)
        return dict(verdict="undetermined", evidence="against",
                    reason="modes inside the claimed interval at every resolution (likely false, not provable)")
    return dict(verdict="undetermined", reason=report.get("reason") or report.get("edge_failure")
                or ("count failures" if any((r or {}).get("n_failures") for r in (report.get("resolutions") or {}).values())
                    else "claim inside the edge guard band"))


def static_block(spec, targets, nu=0.3, ladder=((32, 48, 64), (48, 64, 80), (64, 80, 96)), tol=0.05,
                 phases=STATIC_PHASES, cache: dict | None = None,
                 feature_min_voxels: float = FEATURE_MIN_VOXELS) -> dict:
    """Three-resolution static block, every resolution solved at grid phases 0 and `phases`. Rungs are tried in order;
    the design moves to the next rung when the values have not converged, or when a target lies inside the guard
    band (between the guarded bound and the computed values), since the finer rung's band is narrower. A rung whose
    finest resolution puts fewer than `feature_min_voxels` voxels across the load-path feature is skipped while a
    finer rung remains; on the last rung it withholds certification (`feature_check`). Release needs: numerics at
    every solve of the rung (residual, symmetry, positive definiteness, percolation, islands), every static target
    met by the guarded bounds, and the feature resolved."""
    cache = {} if cache is None else cache
    tried = []
    conv, rung, fails = None, ladder[0], []
    # convergence is required of the quantities that carry a target (all of them before 2026-11-05; a gap-only
    # request then climbed the whole ladder and ended undetermined on an untargeted quantity, results/probe/NOTES.md)
    needed = sorted({q for key, (q, _) in STATIC_KEYS.items() if key in targets})
    ok_conv = False
    for i_rung, rung in enumerate(ladder):
        feat = feature_check(spec, max(rung), feature_min_voxels)
        if not feat["passed"] and i_rung < len(ladder) - 1:
            tried.append(dict(resolutions=list(rung), skipped=True, feature=feat))
            continue
        checkpoint("certificate: static rung", rung=list(rung), rung_index=len(tried) + 1, rungs=len(ladder))
        rows = [_static_row(spec, n, nu, targets, cache) for n in rung]
        rows += [_static_row(spec, n, nu, targets, cache, phase=p) for n in rung for p in phases]
        if any("E100" not in r for r in rows):
            reason = "; ".join(f for r in rows for f in r.get("checks_failed", [])) or "solve failed"
            tried.append(dict(resolutions=list(rung), converged=False, checks_failed=[reason], not_converged=[]))
            return dict(passed=False, reason=reason, used=list(rung), ladder=tried, convergence=None,
                        checks_failed=[reason], numerics_ok=False,
                        verdict=static_verdict(None, targets, False, invalid_geometry=_geometry_invalid(rows)),
                        resolutions={k: v for k, v in cache.items() if isinstance(k, int)},
                        phase_rows={f"{k[0]}@{k[1]}": v for k, v in cache.items() if not isinstance(k, int)}, tol=tol)
        conv = static_convergence({n: [cache[n]] + [cache[(n, p)] for p in phases] for n in rung}, tol=tol)
        ok_conv = all(conv["quantities"][q]["converged"] for q in needed)
        fails = _guarded_checks(conv, targets) if ok_conv else ["static values not converged on the ladder"]
        tried.append(dict(resolutions=list(rung), converged=ok_conv, converged_all=conv["converged"],
                          checks_failed=fails,
                          not_converged=[q for q, v in conv["quantities"].items() if not v["converged"]]))
        if ok_conv and not fails:
            break
    keys = list(rung) + [(n, p) for n in rung for p in phases]
    numerics = all(cache[k]["numerics_ok"] for k in keys)
    verdict = static_verdict(conv["quantities"], targets, bool(numerics),
                             invalid_geometry=_geometry_invalid([cache[k] for k in keys]))
    if not feat["passed"]:
        verdict = _withhold(verdict, feat)
        fails = fails + [verdict.get("reason") or "load-path feature not resolved"]
    return dict(passed=bool(numerics and ok_conv and not fails), used=list(rung), ladder=tried, needed=needed,
                feature=feat, convergence=conv, checks_failed=fails, numerics_ok=bool(numerics), verdict=verdict,
                resolutions={k: v for k, v in cache.items() if isinstance(k, int)},
                phase_rows={f"{k[0]}@{k[1]}": v for k, v in cache.items() if not isinstance(k, int)}, tol=tol)


BLOCH_EDGE_RES = (40,)  # edge-only third resolution for the order-fitted gap guard (results/g2/NOTES.md)
BLOCH_PHASES = (0.25, 0.5)  # grid phases at the finest counted Bloch resolution


def bloch_block(spec, gap, nu=0.3, res_bloch=(20, 30), n_path=4, n_interior=10, edge_res=BLOCH_EDGE_RES,
                bloch_phases=BLOCH_PHASES, adversarial_n=10, feature_min_voxels: float = FEATURE_MIN_VOXELS) -> dict:
    """Gap block of the certificate (see the module docstring). Fails closed on any solver error. A certified gap is
    withheld (undetermined) when the finest resolution of the block, counted or edge-only, puts fewer than
    `feature_min_voxels` voxels across the load-path feature (`feature_check`); a refutation stands."""
    g = _bloch_block(spec, gap, nu, res_bloch, n_path, n_interior, edge_res, bloch_phases, adversarial_n)
    feat = feature_check(spec, max(tuple(res_bloch) + tuple(edge_res or ())), feature_min_voxels)
    g["feature"] = feat
    if not feat["passed"]:
        g["passed"] = False
        g["verdict"] = _withhold(g["verdict"], feat)
    return g


def _bloch_block(spec, gap, nu, res_bloch, n_path, n_interior, edge_res, bloch_phases, adversarial_n) -> dict:
    checkpoint("certificate: Bloch block", resolutions=list(res_bloch))
    meshes, dens = {}, []
    for n in res_bloch:
        m, info = _mesh(spec, n, nu)
        if m is None:
            return dict(passed=False, reason="empty geometry", verdict=dict(verdict="refuted", reason="empty geometry"))
        meshes[n] = m
        dens.append(info["density"])
    try:
        n_top = max(res_bloch)
        edge_meshes = {n: _mesh(spec, n, nu)[0] for n in edge_res}
        phase_meshes = [_mesh(spec, n_top, nu, phase=p)[0] for p in bloch_phases]
        if any(m is None for m in [*edge_meshes.values(), *phase_meshes]):
            raise ValueError("empty geometry at an edge resolution or grid phase")
        # worst-case k inside the zone from the GPU search tier on a coarse mesh (an interior extremum is not left
        # to random sampling; tests/test_mutations.py); fails closed if the search cannot run
        adv = bloch.adversarial_ks(_mesh(spec, adversarial_n, nu)[0], gap["f_lo"], gap["f_hi"])
        g = bloch.certify_gap(meshes, gap["f_lo"], gap["f_hi"], n_path=n_path, n_interior=n_interior,
                              edge_meshes=edge_meshes, phase_meshes=phase_meshes, extra_ks=adv["ks"])
        g["adversarial"] = dict(n=adversarial_n, ks=np.round(adv["ks"] / np.pi, 4).tolist(),
                                search_edges=adv.get("search_edges"))
        g["density_spread"] = float(max(dens) - min(dens))
        g["passed"] = bool(g["passed"] and g["density_spread"] <= 0.01)
        g["verdict"] = gap_verdict(g)
        return g
    except Exception as e:  # fail closed
        return dict(passed=False, reason=f"solver error: {e}", verdict=dict(verdict="undetermined",
                                                                             reason=f"solver error: {e}"))


def as_built_block(spec: dict, targets: dict, nu: float = 0.3, n_static: int = 32, n_bloch: int = 20,
                   offset: float = 0.01, bloch_claim: dict | None = None) -> dict:
    """As-built robustness flag (not required for release): the surface is eroded and dilated by `offset` (fraction
    of the cell edge) and the static targets (densities excluded) are re-checked by one solve at n_static; with a
    gap target and the Bloch block's `bloch_claim` (its band index `below_band`), the gap counts are re-checked at
    n_bloch on 2 path points per leg and 4 interior k. Moved out of `certify` unchanged (B2, 2026-11-07) so that the
    `as_built` tool runs the same check."""
    gap = targets.get("gap")
    ab = {}
    static_t = {k: v for k, v in targets.items() if k in STATIC_KEYS and not k.startswith("density")}
    for op, sgn in (("erode", -1), ("dilate", 1)):
        checkpoint("as-built check", case=op, offset=offset)
        m, info_ab = _mesh(spec, n_static, nu, offset_voxels=sgn * offset * n_static)
        if m is None or not all(info_ab["percolates"]):
            ab[op] = dict(passed=False, reason="geometry vanished or lost its load path")
            continue
        try:
            r = homog.homogenize(mesh=m)
        except Exception as e:
            ab[op] = dict(passed=False, reason=f"solver error: {e}")
            continue
        e = dict(E100=r["E100"], density=r["density"], static_failed=_static_checks(r, static_t))
        e["static_ok"] = bool(r["min_eig"] > 1e-8 and not e["static_failed"])
        if gap and bloch_claim is not None:
            mb, _ = _mesh(spec, n_bloch, nu, offset_voxels=sgn * offset * n_bloch)
            gb = bloch.certify_gap({n_bloch: mb}, gap["f_lo"], gap["f_hi"], n_path=2, n_interior=4,
                                   below_band=bloch_claim["below_band"])
            e["gap_ok"] = gb["passed"]
        e["passed"] = bool(e["static_ok"] and e.get("gap_ok", True))
        ab[op] = e
    return dict(passed=all(v["passed"] for v in ab.values()), offset=offset, cases=ab,
                note="robustness flag; reported, not required for release")


def rescore_bloch(report: dict, spec: dict, feature_min_voxels: float = FEATURE_MIN_VOXELS) -> dict:
    """A stored gap report re-judged by the current rules, without a solve: the edge guard is re-applied to the
    stored edge estimates and phase edges (`bloch.gap_convergence`), and the feature rule to the finest resolution of
    the stored edges. The counts, edges and density spread are what the solver produced, which the rules do not
    change, so the result is the verdict the current code gives on the same solves. Used to re-score certificates
    written before the round-3 rules (2026-11-09)."""
    import copy
    g = copy.deepcopy(report)
    res = g.get("resolutions") or {}
    counts_ok = bool(res) and all((r or {}).get("passed") for r in res.values()) and not g.get("edge_failure")
    c = g.get("convergence")
    if c and len(c.get("edges") or {}) >= 2:
        edges = {int(n): tuple(v) for n, v in c["edges"].items()}
        new = bloch.gap_convergence(edges, g["claim"]["f_lo"], g["claim"]["f_hi"],
                                    safety=c.get("safety", bloch.CONVERGENCE_SAFETY), phase_edges=c.get("phase_edges"))
        new["edge_search"] = c.get("edge_search")
        g["convergence"] = new
        g["passed"] = bool(counts_ok and new["passed"] and g.get("density_spread", 0.0) <= 0.01)
    if res:  # a report without resolutions (solver error, empty geometry) keeps its stored verdict
        g["verdict"] = gap_verdict(g)
    ns = [int(n) for n in ((c or {}).get("edges") or res)]
    if ns:
        feat = feature_check(spec, max(ns), feature_min_voxels)
        g["feature"] = feat
        if not feat["passed"]:
            g["passed"] = False
            g["verdict"] = _withhold(g["verdict"], feat)
    return g


def rescore_static(block: dict, spec: dict, feature_min_voxels: float = FEATURE_MIN_VOXELS) -> dict:
    """A stored static block re-judged by the feature rule at the finest resolution of the rung it used (the static
    guard itself is unchanged)."""
    import copy
    st = copy.deepcopy(block)
    if st.get("used"):
        feat = feature_check(spec, max(st["used"]), feature_min_voxels)
        st["feature"] = feat
        if not feat["passed"]:
            st["passed"] = False
            st["verdict"] = _withhold(st.get("verdict") or {}, feat)
    return st


def rescore_certificate(cert: dict, feature_min_voxels: float = FEATURE_MIN_VOXELS) -> dict:
    """A stored certificate re-judged by the current rules (`rescore_static`, `rescore_bloch`); the overall verdict
    follows `certify`. The stored checker identity is kept and the rules applied are recorded."""
    import copy
    out = copy.deepcopy(cert)
    b = out["blocks"]
    b["static"] = rescore_static(b["static"], out["spec"], feature_min_voxels)
    passed = bool(b["static"]["passed"])
    if "bloch" in b:
        b["bloch"] = rescore_bloch(b["bloch"], out["spec"], feature_min_voxels)
        passed &= bool(b["bloch"]["passed"])
    vs = [b["static"]["verdict"]["verdict"]] + ([b["bloch"]["verdict"]["verdict"]] if "bloch" in b else [])
    out["passed"] = passed
    out["verdict"] = "certified" if passed else "refuted" if "refuted" in vs else "undetermined"
    out["robust"] = bool(passed and b.get("as_built", {}).get("passed", False))
    out["rescored"] = dict(checker=checker_hash(), feature_min_voxels=feature_min_voxels,
                           rules="drift toward the claim fails closed; load-path feature resolution")
    return out


# Files that always belong to the checker identity although certify.py does not import them: units.py (the
# material table and unit conversion that state a request in solver units) and the package's runtime set-up
# (__init__.py, _runtime.py: MKL threads and the reproducibility mode).
CHECKER_EXTRA = ("units.py", "__init__.py", "_runtime.py")


def checker_files(pkg_dir=None) -> tuple:
    """Every amm source file the certificate depends on: certify.py, the transitive closure of its imports of amm
    modules (read from the source with `ast`, including imports inside functions), and CHECKER_EXTRA. A new module
    that the checker imports joins the identity automatically (B3, 2026-11-07; until then a fixed list of 7 files).
    """
    import ast
    from pathlib import Path
    pkg = Path(pkg_dir) if pkg_dir is not None else Path(__file__).parent
    todo, seen = ["certify"], set()
    while todo:
        mod = todo.pop()
        if mod in seen or not (pkg / f"{mod}.py").exists():
            continue
        seen.add(mod)
        tree = ast.parse((pkg / f"{mod}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level == 1 and node.module is None:            # from . import a, b
                    todo += [a.name for a in node.names]
                elif node.level == 1:                                   # from .a import x
                    todo.append(node.module.split(".")[0])
                elif node.level == 0 and node.module and node.module.split(".")[0] == "amm":
                    parts = node.module.split(".")
                    todo += [parts[1]] if len(parts) > 1 else [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                todo += [a.name.split(".")[1] for a in node.names if a.name.startswith("amm.")]
    files = {f"{m}.py" for m in seen} | {f for f in CHECKER_EXTRA if (pkg / f).exists()}
    return tuple(sorted(files))


CHECKER_FILES = checker_files()


def checker_hash() -> str:
    """Identity of the certificate code (audit F09): certificates and caches record it. Covers every file of
    `checker_files()`, recomputed at each call (a file added to the closure later is covered too)."""
    import hashlib
    from pathlib import Path
    h = hashlib.sha256()
    for f in checker_files():
        h.update(f.encode() + (Path(__file__).parent / f).read_bytes())
    return h.hexdigest()[:16]


def certify(spec: dict, targets: dict, res_bloch=(20, 30), static_ladder=((32, 48, 64), (48, 64, 80), (64, 80, 96)),
            tol_static: float = 0.05, as_built: bool = True, as_built_offset: float = 0.01, nu: float = 0.3,
            n_path: int = 4, n_interior: int = 10, edge_res=BLOCH_EDGE_RES, bloch_phases=BLOCH_PHASES,
            adversarial_n: int = 10, feature_min_voxels: float = FEATURE_MIN_VOXELS) -> dict:
    t0 = time.perf_counter()
    cert = dict(spec=spec, spec_hash=spec_hash(spec), targets=targets,
                solver=dict(nu=nu, element=fem.ELEMENT, partial_voxels="finite-cell"), checker=checker_hash(),
                blocks={}, timing={})
    st = static_block(spec, targets, nu, static_ladder, tol_static, feature_min_voxels=feature_min_voxels)
    cert["blocks"]["static"] = st
    cert["timing"]["static"] = round(time.perf_counter() - t0, 1)
    passed = st["passed"]

    gap = targets.get("gap")
    if gap:
        t1 = time.perf_counter()
        g = bloch_block(spec, gap, nu, res_bloch, n_path, n_interior, edge_res, bloch_phases, adversarial_n,
                        feature_min_voxels)
        cert["blocks"]["bloch"] = g
        cert["timing"]["bloch"] = round(time.perf_counter() - t1, 1)
        passed &= g["passed"]

    if as_built:
        t2 = time.perf_counter()
        n_s, n_b = st.get("used", static_ladder[0])[0], min(res_bloch)
        cert["blocks"]["as_built"] = as_built_block(spec, targets, nu, n_s, n_b, as_built_offset,
                                                    bloch_claim=cert["blocks"].get("bloch", {}).get("claim"))
        cert["timing"]["as_built"] = round(time.perf_counter() - t2, 1)
    cert["passed"] = bool(passed)
    vs = [cert["blocks"]["static"]["verdict"]["verdict"]] + ([cert["blocks"]["bloch"]["verdict"]["verdict"]]
                                                           if "bloch" in cert["blocks"] else [])
    cert["verdict"] = ("certified" if passed else "refuted" if "refuted" in vs else "undetermined")
    cert["robust"] = bool(passed and cert["blocks"].get("as_built", {}).get("passed", False))
    cert["seconds"] = round(time.perf_counter() - t0, 1)
    return cert
