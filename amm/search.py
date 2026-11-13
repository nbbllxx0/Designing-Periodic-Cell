"""`search` tool: Bayesian optimization over the family parameters (BoTorch), with batched search-tier evaluation.

Arms: one per kind (TPMS: per kind and mode). Each arm's parameters live in a 1-D or 2-D box (amm.atlas.BOX),
mapped to the unit cube. Objective: the overall slack of amm.atlas.slacks for the request's normalized targets,
with each value corrected by the calibrated median search-tier error (objective="expected", the default: the
best estimate of the converged value); "pess" optimizes the worst end of the error ranges (a design found that way
clears its targets with high confidence, but 5 % claims rarely can), "nominal" the raw search-tier values.

Per round: a GP (SingleTaskGP, standardized outcomes) per arm, qLogEI over a Sobol candidate set filtered by the
arm's validity rule (amm.atlas.valid), the best q candidates over all arms evaluated as one batch. Atlas rows at
the same Poisson ratio seed the GPs for free and choose which arms to search (the `max_arms` best by seed
slack). Results are search-tier values, NOT certificates: certify the returned design before any claim.
"""
from __future__ import annotations

import time

import numpy as np
import torch
from torch.quasirandom import SobolEngine

try:  # optional extra (pip install amm[search]); the rest of amm works without it
    from botorch.acquisition.logei import qLogExpectedImprovement
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import SingleTaskGP
    from botorch.models.transforms.outcome import Standardize
    from botorch.optim import optimize_acqf_discrete
    from gpytorch.mlls import ExactMarginalLogLikelihood
except ImportError as _e:  # pragma: no cover - exercised by tests/test_packaging.py with the modules hidden
    raise ImportError("amm.search (the `search` tool) needs BoTorch and GPyTorch: pip install amm[search]") from _e

from . import atlas, certify, evaluate, geometry
from .progress import checkpoint


def arms(families=None) -> list[tuple]:
    """(kind, mode) pairs; mode is None outside TPMS."""
    fams = families or list(geometry.FAMILIES)
    out = []
    for fam in fams:
        for kind in geometry.FAMILIES[fam]:
            out += [(kind, m) for m in atlas.TPMS_MODES] if fam == "tpms" else [(kind, None)]
    return out


def _names(kind):
    return list(atlas.box(kind))


def to_spec(arm, x) -> dict:
    kind, mode = arm
    b = atlas.box(kind)
    p = {k: lo + float(xi) * (hi - lo) for k, (lo, hi), xi in zip(b, b.values(), x)}
    if atlas.family_of(kind) == "struts" and p["R"] < p["r"] + atlas.R_GAP:
        p["R"] = 0.0 if p["R"] < 0.5 * (p["r"] + atlas.R_GAP) else p["r"] + atlas.R_GAP  # snap to a valid node
    return atlas.make_spec(kind, p, mode)


def to_unit(arm, spec) -> np.ndarray:
    b = atlas.box(arm[0])
    return np.array([(spec["params"][k] - lo) / (hi - lo) for k, (lo, hi) in b.items()])


def arm_of(spec) -> tuple:
    return (spec["kind"], spec["params"].get("mode"))


def _candidates(arm, n, seed) -> np.ndarray:
    d = len(_names(arm[0]))
    X = SobolEngine(d, scramble=True, seed=seed).draw(n).double().numpy()
    keep = [i for i, x in enumerate(X) if atlas.valid(arm[0], to_spec(arm, x)["params"])]
    return X[keep]


def search(targets: dict, nu: float = 0.3, families=None, budget: int = 48, q: int = 8, atlas_rows=None,
           objective: str = "expected", max_arms: int = 3, n_cand: int = 1024, seed: int = 0, evaluator=None, err=None,
           domain=None, log=None) -> dict:
    """Find designs whose search-tier properties meet `targets` (normalized; amm.units.normalize).

    budget: number of new evaluations. atlas_rows: rows of amm.atlas.load at the same nu (optional seed data).
    evaluator: specs -> rows (default: amm.evaluate.evaluate_batch at amm.atlas.SEARCH_TIER). Returns the best
    designs with nominal / pessimistic / optimistic slacks, the arms searched and the full evaluation history."""
    t0 = time.perf_counter()
    torch.manual_seed(seed)
    err = atlas.error_model() if err is None else err
    domain = atlas.error_domain() if domain is None else domain
    case = objective
    evaluator = evaluator or (lambda specs: evaluate.evaluate_batch(specs, nu=nu, keep_bands=True,
                                                                    **atlas.SEARCH_TIER))
    log = log or (lambda s: None)

    def score(row):
        return atlas.slacks(row, targets, atlas.err_for(row["spec"], err), case)["min"]

    all_arms = arms(families)
    data = {a: dict(X=[], y=[], rows=[]) for a in all_arms}
    for r in atlas_rows or []:
        a = arm_of(r["spec"])
        if a in data and abs(r.get("nu", nu) - nu) < 1e-9:
            data[a]["X"].append(to_unit(a, r["spec"]))
            data[a]["y"].append(score(r))
            data[a]["rows"].append(r)
    seeded = {a: max(d["y"]) for a, d in data.items() if d["y"]}
    if seeded:
        active = sorted(seeded, key=lambda a: -seeded[a])[:max_arms]
    else:
        active = all_arms
    history, n_eval = [], 0

    def run(specs):
        checkpoint("search: batch", batch=len({h["round"] for h in history}) + 1, n_evaluations=n_eval,
                   n_new=len(specs), budget=budget)
        rows = evaluator(specs)
        for r in rows:
            a = arm_of(r["spec"])
            y = score(r)
            data[a]["X"].append(to_unit(a, r["spec"]))
            data[a]["y"].append(y)
            data[a]["rows"].append(r)
            history.append(dict(spec=r["spec"], slack=y, round=len({h["round"] for h in history})))
        return rows

    # arms without seed data: a small Sobol start (counted in the budget)
    start = []
    for a in active:
        if len(data[a]["y"]) < 3:
            start += [to_spec(a, x) for x in _candidates(a, 16, seed)[:3]]
    if start:
        run(start[:budget])
        n_eval += len(start[:budget])
    rnd = 0
    while n_eval < budget:
        rnd += 1
        qq = min(q, budget - n_eval)
        best_f = max(max(data[a]["y"]) for a in active)
        picks = []
        for a in active:
            X = torch.tensor(np.array(data[a]["X"]), dtype=torch.double)
            Y = torch.tensor(np.array(data[a]["y"]), dtype=torch.double).clamp(min=-1.0).unsqueeze(-1)
            C = _candidates(a, n_cand, seed + rnd)
            if len(X):  # drop candidates within 1e-3 of an evaluated point
                dist = np.min(np.linalg.norm(C[:, None, :] - X.numpy()[None], axis=2), axis=1)
                C = C[dist > 1e-3]
            if not len(C):
                continue
            if float(Y.std()) < 1e-12:  # flat arm (e.g. no gap anywhere yet): explore, ranked below any GP pick
                picks += [(-np.inf, a, c) for c in C[:qq]]
                continue
            model = SingleTaskGP(X, Y, outcome_transform=Standardize(m=1))
            try:
                fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
            except Exception:  # a failed hyperparameter fit keeps the defaults; the GP is still usable
                pass
            acq = qLogExpectedImprovement(model, best_f=best_f)
            cand, _ = optimize_acqf_discrete(acq, q=min(qq, len(C)), choices=torch.tensor(C), unique=True)
            with torch.no_grad():
                vals = acq(cand.unsqueeze(1)).numpy()  # single-point value of each pick, to rank across arms
            picks += [(float(v), a, c.numpy()) for v, c in zip(vals, cand)]
        if not picks:
            break
        picks.sort(key=lambda t: -t[0])
        specs = [to_spec(a, x) for _, a, x in picks[:qq]]
        run(specs)
        n_eval += len(specs)
        log(f"round {rnd}: {n_eval}/{budget} evaluations, best {case} slack "
            f"{max(max(data[a]['y']) for a in active):+.4f}")

    rows = [r for a in active for r in data[a]["rows"]]
    atlas_ids = {id(r) for r in atlas_rows or []}
    seen, best = set(), []
    for r in sorted(rows, key=lambda r: -score(r)):
        h = certify.spec_hash(r["spec"])
        if h in seen:
            continue
        seen.add(h)
        e = atlas.err_for(r["spec"], err)
        best.append(dict(spec=r["spec"], calibrated=atlas.calibrated(r["spec"], domain),
                         slack_nominal=atlas.slacks(r, targets)["min"],
                         slack_expected=atlas.slacks(r, targets, e, "expected")["min"],
                         slack_pess=atlas.slacks(r, targets, e, "pess")["min"],
                         slack_opt=atlas.slacks(r, targets, e, "opt")["min"],
                         values={k: r.get(k) for k in ("density", "E100", "G", "bulk", "nu100") if k in r},
                         gaps=atlas.row_gaps(r)[:3], from_atlas=id(r) in atlas_ids))
        if len(best) == 5:
            break
    return dict(objective=case, arms=[list(a) for a in active], n_evaluations=n_eval, rounds=rnd, best=best,
                found=bool(best and best[0][f"slack_{case}"] > 0),
                found_pessimistic=bool(best and best[0]["slack_pess"] > 0),
                history=history, seconds=round(time.perf_counter() - t0, 1), nu=nu, targets=targets,
                note="search-tier values, not certificates")
