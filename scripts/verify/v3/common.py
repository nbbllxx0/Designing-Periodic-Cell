"""V3 shared harness: targets, evaluator with recording, the six methods, certificate summaries.

Protocol: results/verification/v3/NOTES.md. amm is used as installed in the checkout; nothing in amm/ is changed.
Import this module before torch (amm initializes MKL first).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import amm  # noqa: F401  (MKL before torch)
import numpy as np
from amm import atlas, certify, evaluate

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v3"
BUDGET, Q, SEED = 48, 8, 0
METHODS = {"M1": "atlas_only", "M2": "sobol", "M3": "de", "M4": "bo_full", "M5": "bo_no_seed",
           "M6": "bo_no_correction"}
OBJ = {"M1": "expected", "M2": "expected", "M3": "expected", "M4": "expected", "M5": "expected",
       "M6": "nominal"}
ERR = atlas.error_model()
DOMAIN = atlas.error_domain()


def jdefault(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, default=jdefault), encoding="utf-8")
    tmp.replace(path)


def load_targets(path=OUT / "targets.json") -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["targets"]


_ATLAS: dict = {}


def atlas_rows(nu: float) -> list[dict]:
    key = round(nu, 4)
    if key not in _ATLAS:
        _ATLAS[key] = atlas.load(str(ROOT / "results" / "atlas" / f"atlas_nu{nu:g}.jsonl"))
    return _ATLAS[key]


def slk(row, targets):
    e = atlas.err_for(row["spec"], ERR)
    return dict(nominal=atlas.slacks(row, targets)["min"], expected=atlas.slacks(row, targets, e, "expected")["min"],
                pess=atlas.slacks(row, targets, e, "pess")["min"], opt=atlas.slacks(row, targets, e, "opt")["min"])


def brief_row(row, targets, i):
    s = slk(row, targets)
    return dict(i=i, spec=row["spec"], hash=certify.spec_hash(row["spec"]), valid=bool(row.get("valid", False)),
                **{f"slack_{k}": v for k, v in s.items()},
                values={k: row.get(k) for k in ("density", "E100", "G", "bulk", "nu100")},
                gaps=[dict(f_lo=g["f_lo"], f_hi=g["f_hi"], rel=g["rel"]) for g in atlas.row_gaps(row)][:6])


class Recorder:
    """The search-tier evaluator of every method (the search tool's call), recording each row in order."""

    def __init__(self, targets, nu):
        self.targets, self.nu, self.rows, self.calls, self.seconds = targets, nu, [], 0, 0.0

    def __call__(self, specs):
        t = time.perf_counter()
        rows = evaluate.evaluate_batch(list(specs), nu=self.nu, keep_bands=True, **atlas.SEARCH_TIER)
        self.seconds += time.perf_counter() - t
        self.calls += 1
        for r in rows:
            r["nu"] = self.nu
            self.rows.append(r)
        return rows


# ---- design space shared by Sobol and DE --------------------------------------------------------------------
def _arms():
    from amm import search
    return search.arms()


def map_point(u, project: bool):
    """u = (u0, u1, u2) in [0,1]^3 -> spec, or None if invalid (project=False). u0 picks the arm."""
    from amm import search
    arms = _arms()
    a = arms[min(int(np.floor(u[0] * len(arms))), len(arms) - 1)]
    d = len(atlas.box(a[0]))
    return spec_for(a, list(u[1:1 + d]), project)


def spec_for(arm, x, project: bool):
    from amm import search
    spec = search.to_spec(arm, np.clip(np.asarray(x, float), 0.0, 1.0))
    p = dict(spec["params"])
    if atlas.valid(arm[0], p):
        return spec
    if not project:
        return None
    if arm[0] == "cube_bars":
        p["w"] = min(p["w"], p["c"] - 0.04)
    elif arm[0] == "sphere_ligaments":
        p["w"] = min(p["w"], 2 * p["c"] - 0.02)
    p.pop("mode", None)
    spec = atlas.make_spec(arm[0], p, arm[1])
    assert atlas.valid(arm[0], spec["params"]), spec
    return spec


def sobol_points(n_valid: int | None = None, seed: int = SEED):
    n_valid = BUDGET if n_valid is None else n_valid
    from scipy.stats import qmc
    U = qmc.Sobol(d=3, scramble=True, seed=seed).random(1024)
    out = []
    for u in U:
        s = map_point(u, project=False)
        if s is not None:
            out.append((u, s))
        if len(out) == n_valid:
            break
    return out


# ---- methods ------------------------------------------------------------------------------------------------
def best_of(rows, targets, objective):
    """Best row by the objective; ties keep the first seen."""
    best, bi = None, None
    for i, r in enumerate(rows):
        v = slk(r, targets)[objective]
        if best is None or v > best:
            best, bi = v, i
    return bi


def run_method(m: str, tgt: dict) -> dict:
    targets, nu = tgt["targets"], tgt["nu"]
    obj = OBJ[m]
    rec = Recorder(targets, nu)
    t0 = time.perf_counter()
    info = {}
    final_row, from_atlas = None, False
    if m == "M1":
        rows = atlas_rows(nu)
        i = best_of(rows, targets, obj)
        final_row, from_atlas = rows[i], True
        info["atlas_rows"] = len(rows)
    elif m == "M2":
        pts = sobol_points()
        specs = [s for _, s in pts]
        for k in range(0, len(specs), Q):
            rec(specs[k:k + Q])
        final_row = rec.rows[best_of(rec.rows, targets, obj)]
    elif m == "M3":
        from scipy.optimize import differential_evolution
        arms = _arms()
        init = []
        for u, _ in sobol_points(Q):
            init.append([min(int(np.floor(u[0] * len(arms))), len(arms) - 1), u[1], u[2]])
        init = np.array(init, float)

        def f(X):
            X = np.atleast_2d(X)
            if X.shape[0] != 3:
                X = X.T
            specs = []
            for col in X.T:
                a = arms[int(np.clip(round(col[0]), 0, len(arms) - 1))]
                d = len(atlas.box(a[0]))
                specs.append(spec_for(a, col[1:1 + d], project=True))
            left = BUDGET - len(rec.rows)
            if left <= 0:
                return np.full(len(specs), 2.0)
            rows = rec(specs[:left])
            vals = [-slk(r, targets)[obj] for r in rows] + [2.0] * (len(specs) - len(rows))
            return np.array(vals)

        res = differential_evolution(f, bounds=[(0, len(arms) - 1), (0, 1), (0, 1)], integrality=[True, False, False],
                                     init=init, maxiter=BUDGET // Q - 1, polish=False, tol=0, atol=0,
                                     updating="deferred", vectorized=True, seed=SEED)
        info["de"] = dict(nit=int(res.nit), nfev=int(res.nfev), message=str(res.message))
        final_row = rec.rows[best_of(rec.rows, targets, obj)]
    else:
        from amm import search
        kw = dict(budget=BUDGET, q=Q, objective=obj, seed=SEED, evaluator=rec,
                  atlas_rows=None if m == "M5" else atlas_rows(nu))
        r = search.search(targets, nu=nu, **kw)
        info["arms"] = r["arms"]
        info["rounds"] = r["rounds"]
        info["n_evaluations_reported"] = r["n_evaluations"]
        b = r["best"][0]
        from_atlas = bool(b["from_atlas"])
        if from_atlas:
            final_row = next(x for x in atlas_rows(nu) if certify.spec_hash(x["spec"]) == certify.spec_hash(b["spec"]))
        else:
            h = certify.spec_hash(b["spec"])
            final_row = next(x for x in rec.rows if certify.spec_hash(x["spec"]) == h)
    seconds = time.perf_counter() - t0
    evals = [brief_row(r, targets, i + 1) for i, r in enumerate(rec.rows)]
    fh = certify.spec_hash(final_row["spec"])
    evals_to_final = 0 if from_atlas else next(e["i"] for e in evals if e["hash"] == fh)
    # best-so-far seed for the curves: the best atlas row the method read (M1, M4, M6)
    seed_best = None
    if m in ("M1", "M4", "M6"):
        rows = atlas_rows(nu)
        if m != "M1":
            arms = {tuple(a) for a in info["arms"]}
            rows = [x for x in rows if (x["spec"]["kind"], x["spec"]["params"].get("mode")) in arms]
        j = best_of(rows, targets, obj)
        seed_best = slk(rows[j], targets)
    final = brief_row(final_row, targets, evals_to_final)
    final["calibrated_domain"] = atlas.calibrated(final_row["spec"], DOMAIN)
    return dict(target_id=tgt["target_id"], method=m, method_name=METHODS[m], objective=obj, nu=nu,
                targets=targets, budget=BUDGET if m != "M1" else 0, n_evaluations=len(rec.rows),
                evaluator_calls=rec.calls, evaluator_seconds=round(rec.seconds, 3), search_seconds=round(seconds, 3),
                from_atlas=from_atlas, evals_to_final=evals_to_final, final=final, seed_best=seed_best,
                evals=evals, info=info, finished=time.strftime("%Y-%m-%d %H:%M:%S"))


# ---- certificates -------------------------------------------------------------------------------------------
def cert_summary(c: dict, targets: dict) -> dict:
    st = c["blocks"]["static"]
    conv = (st.get("convergence") or {}).get("quantities") or {}
    out = dict(verdict=c["verdict"], passed=c["passed"], seconds=c["seconds"], timing=c["timing"],
               static_verdict=st["verdict"]["verdict"], static_rung=st.get("used"),
               bounds={q: dict(lower=v["lower"], upper=v["upper"], extrapolated=v["extrapolated"],
                               converged=v["converged"]) for q, v in conv.items()},
               checker=c["checker"], spec_hash=c["spec_hash"])
    sl = {}
    for key, (q, kind) in certify.STATIC_KEYS.items():
        if key in targets and q in conv:
            t = targets[key]
            v = conv[q]["lower"] if kind == "min" else conv[q]["upper"]
            sl[key] = ((v - t) if kind == "min" else (t - v)) / max(abs(t), 1e-12)
    bl = c["blocks"].get("bloch")
    if bl is not None:
        cv = bl.get("convergence") or {}
        out["gap_verdict"] = bl["verdict"]["verdict"]
        out["safe_interval"] = cv.get("safe_interval")
        out["gap_edges_extrapolated"] = [(cv.get("lower_edge") or {}).get("extrapolated"),
                                         (cv.get("upper_edge") or {}).get("extrapolated")]
        g = targets["gap"]
        si = cv.get("safe_interval")
        if si and si[0] is not None and si[1] is not None:
            mid = 0.5 * (g["f_lo"] + g["f_hi"])
            sl["gap"] = min(g["f_lo"] - si[0], si[1] - g["f_hi"]) / mid
        else:
            sl["gap"] = None
    out["slack_by_target"] = sl
    vals = [v for v in sl.values() if v is not None]
    out["certified_slack"] = min(vals) if vals and len(vals) == len(sl) else None
    return out
