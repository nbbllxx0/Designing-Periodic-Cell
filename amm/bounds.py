"""Physics bounds on requests, checked BEFORE any search. Three-way verdicts with the violated bound named.

    PROVEN_INFEASIBLE   a rigorous bound is violated (the `scope` says for which design space it is rigorous)
    NOT_REFUTED         no rigorous bound is violated; search decides (FEASIBLE or NOT_FOUND_IN_FAMILIES)
    UNDERSPECIFIED      information needed to state the request in solver units is missing (ask, don't guess)

Rigorous bounds used (two-phase solid + void, solid isotropic E_s, nu_s; phi = solid fraction):
  V1  Voigt (any geometry, any symmetry): C* <= phi C_s as quadratic forms. Hence for every direction the
      Young's modulus E(n) <= phi E_s, every coordinate shear modulus C44 <= phi mu_s, and the hydrostatic
      stiffness (1:C*:1)/9 <= phi K_s. [Hill 1952; Milton, The Theory of Composites, 2002, ch. 13]
  S1  Stability (thermodynamics): C* positive definite. For cubic symmetry C11 > |C12|, C11 + 2 C12 > 0, C44 > 0,
      which confines the [100] Poisson ratio nu100 = C12 / (C11 + C12) to (-1, 1/2).
      Scope: cubic (or isotropic) effective symmetry. Outside the declared cubic design space a non-cubic cell can
      exceed it, so the verdict carries the scope.
  P1  Positivity and consistency: requested minima must be positive where the quantity is a modulus; a minimum
      above the corresponding maximum is contradictory.
  W1  A complete gap cannot include f = 0: the three acoustic branches start at 0 at Gamma and are continuous.
      Also f_hi > f_lo.
Advisory only (reported, never used to refuse a cubic request):
  HS  Hashin-Shtrikman upper bounds on bulk and shear modulus for porous materials. Rigorous for isotropic
      composites; used as PROVEN only when the request asks for isotropy.
Margins: `ratio_to_bound` = target / bound, so values near 1 flag requests that only near-ideal geometries can meet.
"""
from __future__ import annotations

from . import units

PROVEN, NOT_REFUTED, UNDERSPECIFIED = "PROVEN_INFEASIBLE", "NOT_REFUTED", "UNDERSPECIFIED"


def solid_moduli(nu: float, E: float = 1.0) -> dict:
    mu = E / (2 * (1 + nu))
    K = E / (3 * (1 - 2 * nu))
    return dict(E=E, mu=mu, K=K)


def hashin_shtrikman_porous(phi: float, nu: float, E: float = 1.0) -> dict:
    """HS upper bounds (void second phase) on bulk K, shear mu and the implied isotropic E."""
    s = solid_moduli(nu, E)
    K, mu = s["K"], s["mu"]
    if phi <= 0:
        return dict(K=0.0, mu=0.0, E=0.0)
    K_hs = K + (1 - phi) / (-1.0 / K + 3 * phi / (3 * K + 4 * mu))
    mu_hs = mu + (1 - phi) / (-1.0 / mu + 6 * phi * (K + 2 * mu) / (5 * mu * (3 * K + 4 * mu)))
    E_hs = 9 * K_hs * mu_hs / (3 * K_hs + mu_hs)
    return dict(K=K_hs, mu=mu_hs, E=E_hs)


def check(targets: dict, nu_s: float = 0.3, symmetry: str = "cubic", missing: list | None = None) -> dict:
    """targets: normalized (see certify.STATIC_KEYS and gap). symmetry: declared design space ("cubic"|"isotropic")."""
    viol, adv, margins = [], [], {}
    if missing:
        return dict(verdict=UNDERSPECIFIED, missing=list(missing), violated=[], advisory=[], margins={})
    phi_max = min(targets.get("density_max", 1.0), 1.0)
    s = solid_moduli(nu_s)

    def v(bid, stmt, target, limit, scope):
        viol.append(dict(bound=bid, statement=stmt, target=target, limit=limit, scope=scope))

    # P1 consistency / positivity
    for lo, hi in (("density_min", "density_max"), ("E100_min", "E100_max"), ("nu100_min", "nu100_max")):
        if lo in targets and hi in targets and targets[lo] > targets[hi]:
            v("P1", f"{lo} > {hi}: contradictory request", targets[lo], targets[hi], "any")
    if targets.get("density_max", 1.0) <= 0 or targets.get("density_min", 0.0) > 1.0:
        v("P1", "solid fraction outside (0, 1]", targets.get("density_max", targets.get("density_min")), "(0,1]", "any")
    for k in ("E100_max",):
        if k in targets and targets[k] <= 0:
            v("P1", f"{k} <= 0: a load-bearing cell has a positive modulus", targets[k], 0.0, "any")

    # V1 Voigt
    for key, q, lim in (("E100_min", "E", phi_max * s["E"]), ("G_min", "mu", phi_max * s["mu"]),
                        ("bulk_min", "K", phi_max * s["K"])):
        if key in targets:
            margins[key] = dict(bound="V1", limit=lim, ratio_to_bound=targets[key] / lim)
            if targets[key] > lim:
                v("V1", f"{key} exceeds the Voigt bound phi_max * {q}_s (any geometry)", targets[key], lim, "any")

    # S1 stability (cubic / isotropic effective symmetry)
    if symmetry in ("cubic", "isotropic"):
        if targets.get("nu100_min", -2) >= 0.5:
            v("S1", "nu100 >= 1/2 violates positive definiteness for cubic symmetry", targets["nu100_min"], 0.5,
              "cubic design space")
        if targets.get("nu100_max", 2) <= -1.0:
            v("S1", "nu100 <= -1 violates positive definiteness for cubic symmetry", targets["nu100_max"], -1.0,
              "cubic design space")

    # W1 gap
    g = targets.get("gap")
    if g:
        if g["f_lo"] <= 0:
            v("W1", "a complete gap cannot contain f = 0 (acoustic branches start at 0 at Gamma)", g["f_lo"], 0.0,
              "any")
        if g["f_hi"] <= g["f_lo"]:
            v("W1", "gap upper edge not above lower edge", g["f_hi"], g["f_lo"], "any")

    # HS (rigorous only for isotropic requests)
    hs = hashin_shtrikman_porous(phi_max, nu_s)
    for key, q in (("bulk_min", "K"), ("G_min", "mu"), ("E100_min", "E")):
        if key in targets and targets[key] > hs[q]:
            entry = dict(bound="HS", statement=f"{key} exceeds the Hashin-Shtrikman upper bound on {q}",
                         target=targets[key], limit=hs[q], scope="isotropic")
            (viol if symmetry == "isotropic" else adv).append(entry)
            margins.setdefault(key, {})["hs_limit"] = hs[q]

    return dict(verdict=PROVEN if viol else NOT_REFUTED, violated=viol, advisory=adv, margins=margins,
                assumptions=dict(nu_s=nu_s, phi_max=phi_max, symmetry=symmetry))


def check_request(request: dict, symmetry: str = "cubic") -> dict:
    """Physical request (see units.normalize) -> verdict, normalized targets and context."""
    targets, missing, ctx = units.normalize(request)
    nu = ctx["nu_s"] if ctx["nu_s"] is not None else 0.3
    out = check(targets, nu_s=nu, symmetry=symmetry, missing=missing)
    out.update(targets=targets, context={k: v for k, v in ctx.items() if k != "material"})
    return out
