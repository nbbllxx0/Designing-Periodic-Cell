"""Family atlas (plan E2): a dense search-tier sweep of every family and kind over its parameter box, and the
feasibility oracle built on it.

Every row is one `evaluate_batch` result (static at n = 20, bands at n = 10 on the k-path; search tier, NOT a
certificate) with the band diagram kept, so any gap can be re-read later. The parameter spaces are 1-D (TPMS:
density per kind and mode) or 2-D (struts: r, R; resonators: c, w), so a regular grid covers them densely; the
plan's "20k cells per family" was sized for higher-dimensional spaces and is not needed here.

Slack: for a set of normalized targets (the keys of `certify.STATIC_KEYS` and `gap`), each constraint gets a
relative slack, positive when met:
  min target t on q:  (q - t) / |t|          max target:  (t - q) / |t|
  gap [f_lo, f_hi]:   for each complete gap of the cell, min((f_lo - edge_lo), (edge_hi - f_hi)) / f_mid,
                      best over the cell's gaps (no gap, or an invalid cell: -1)
The overall slack is the minimum over constraints: > 0 means every target is met at the search tier.
Search-tier values carry discretization error, one-sided for stiffness and gap edges (they converge from above);
`error_model()` holds the calibrated ranges (scripts/atlas/calibrate.py, results/atlas/NOTES.md). The oracle
reports FEASIBLE only when a cell clears every target at the pessimistic end of the ranges, NOT_FOUND only when
every cell misses at the optimistic end, BORDERLINE otherwise.
"""
from __future__ import annotations

import itertools
import json
import os
import time

import numpy as np

from . import bloch, certify, evaluate, geometry

# parameter boxes (normalized by the cell size a) and validity rules per kind
BOX = {
    "tpms": {"density": (0.06, 0.60)},
    "struts": {"r": (0.04, 0.15), "R": (0.0, 0.32)},
    "cube_bars": {"c": (0.30, 0.86), "w": (0.06, 0.36)},
    "sphere_ligaments": {"c": (0.12, 0.46), "w": (0.06, 0.34)},
}
TPMS_MODES = ("network", "sheet")
R_GAP = 0.03  # a strut node sphere is either absent (R = 0) or at least r + R_GAP (otherwise it is hidden)


def box(kind: str) -> dict:
    return BOX[kind] if kind in BOX else BOX[family_of(kind)]


def family_of(kind: str) -> str:
    return next(f for f, ks in geometry.FAMILIES.items() if kind in ks)


def valid(kind: str, p: dict) -> bool:
    """Geometric validity inside the box (not physics): the shape is what its name says."""
    if kind == "cube_bars":
        return p["w"] <= p["c"] - 0.04  # bars thinner than the core
    if kind == "sphere_ligaments":
        return p["w"] <= 2 * p["c"] - 0.02  # ligaments thinner than the sphere
    if family_of(kind) == "struts":
        return p["R"] == 0.0 or p["R"] >= p["r"] + R_GAP
    return True


def make_spec(kind: str, p: dict, mode: str | None = None) -> dict:
    fam = family_of(kind)
    params = {k: float(round(v, 6)) for k, v in p.items()}
    if fam == "tpms":
        params["mode"] = mode
    return dict(family=fam, kind=kind, params=params)


def grid_specs(n1: int = 28, n2: int = 24) -> list[dict]:
    """Regular grid: n1 densities per TPMS kind and mode; n2 x n2 per 2-D kind (struts: R = 0 plus n2 - 1 values)."""
    out = []
    for kind in geometry.TPMS:
        for mode in TPMS_MODES:
            out += [make_spec(kind, dict(density=d), mode) for d in np.linspace(*BOX["tpms"]["density"], n1)]
    for kind in geometry.STRUTS:
        rs = np.linspace(*BOX["struts"]["r"], n2)
        Rs = [0.0] + list(np.linspace(0.08, BOX["struts"]["R"][1], n2 - 1))
        out += [make_spec(kind, dict(r=r, R=R)) for r, R in itertools.product(rs, Rs) if valid(kind, dict(r=r, R=R))]
    for kind in geometry.RESONATORS:
        b = BOX[kind]
        out += [make_spec(kind, dict(c=c, w=w)) for c, w in itertools.product(np.linspace(*b["c"], n2),
                                                                             np.linspace(*b["w"], n2))
                if valid(kind, dict(c=c, w=w))]
    return out


SEARCH_TIER = dict(n_static=20, n_bloch=10, npts=4, nev=24, workers=4)


def run(specs: list[dict], path: str, nu: float = 0.3, batch: int = 16, log=print) -> None:
    """Evaluate specs at the search tier, appending rows to the jsonl `path` (resumable: done specs are skipped)."""
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            done = {certify.spec_hash(json.loads(l)["spec"]) for l in f if l.strip()}
    todo = [s for s in specs if certify.spec_hash(s) not in done]
    log(f"atlas: {len(done)} done, {len(todo)} to go (nu = {nu})")
    t0 = time.perf_counter()
    for i in range(0, len(todo), batch):
        rows = evaluate.evaluate_batch(todo[i:i + batch], nu=nu, keep_bands=True, **SEARCH_TIER)
        with open(path, "a") as f:
            for r in rows:
                r["nu"] = nu
                r["bands"] = np.round(np.asarray(r["bands"]), 6).tolist() if "bands" in r else None
                f.write(json.dumps(r, default=float) + "\n")
        n = i + len(rows)
        log(f"  {n}/{len(todo)}  {(time.perf_counter() - t0) / n:.2f} s/cell")


def load(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def row_gaps(row: dict, min_rel: float = 0.0) -> list[dict]:
    if not row.get("bloch_valid") or row.get("bands") is None:
        return []
    return bloch.gaps(np.asarray(row["bands"]), min_rel=min_rel)


def error_model_path() -> str:
    """error_model.json in amm.data.data_dir(): $AMM_DATA_DIR if set, else results/atlas of the source checkout.
    Resolved at each call (B9, 2026-11-08; until then frozen at import), so setting AMM_DATA_DIR later works too."""
    from . import data
    return str(data.data_dir() / "error_model.json")


# the path at import time (kept for compatibility; the functions below resolve it at each call)
ERROR_MODEL_PATH = error_model_path()


def error_model(path: str | None = None) -> dict:
    """The calibrated model (scripts/atlas/calibrate.py): {"ranges": {family: {quantity: [lo, hi]}}, "ranges_thin":
    ..., "thin_below": {family: min feature}}. true = search / (1 + e) with e in [lo, hi]; for gap edges, true
    edge = search edge - e * f_mid. Cells thinner than thin_below use ranges_thin (several times wider).
    path: default error_model_path() (amm.data)."""
    with open(path or error_model_path()) as f:
        return json.load(f)


def err_for(spec: dict, model: dict) -> dict:
    """The error ranges that apply to this cell (a plain {family: ranges} map is accepted too, e.g. in tests)."""
    fam = spec["family"]
    if "ranges" not in model:
        return model.get(fam, {})
    thin = spec["params"][FEATURE_PARAM[fam]] < model.get("thin_below", {}).get(fam, 0.0) - 1e-9
    return model["ranges_thin" if thin else "ranges"].get(fam, {})


FEATURE_PARAM = {"tpms": "density", "struts": "r", "resonator": "w"}  # sets the thinnest feature


def error_domain(path: str | None = None) -> dict:
    """{family (TPMS: "tpms:<mode>"): {param: min}}: the error ranges hold only at or above the calibrated minimum."""
    with open(path or error_model_path()) as f:
        return json.load(f).get("domain", {})


def calibrated(spec: dict, domain: dict) -> bool:
    key = f"tpms:{spec['params'].get('mode')}" if spec["family"] == "tpms" else spec["family"]
    d = domain.get(key)
    if not d:
        return False
    return all(spec["params"][k] >= v - 1e-9 for k, v in d.items())


def _true_range(v: float, r) -> tuple[float, float]:
    a, b = v / (1 + r[1]), v / (1 + r[0])
    return min(a, b), max(a, b)


def slacks(row: dict, targets: dict, err: dict | None = None, case: str = "nominal") -> dict:
    """Per-constraint relative slack and the overall minimum (module docstring).

    case: "nominal" uses the search-tier values; with `err` (err_for(spec, error_model())), "expected" corrects each
    value by the calibrated median error, "pess" uses the end of each quantity's error range that is worst for the
    target and "opt" the best end."""
    s = {}
    ok = row.get("valid", False)
    for key, (q, kind) in certify.STATIC_KEYS.items():
        if key in targets:
            t = targets[key]
            v = row.get(q)
            if not ok or v is None:
                s[key] = -1.0
                continue
            if case == "expected" and err and q in err.get("median", {}):
                med = err["median"][q]
                v = v - med if q == "nu100" else v / (1 + med)
            elif case in ("pess", "opt") and err and q in err:
                lo, hi = _true_range(v, err[q]) if q != "nu100" else (v - err[q][1], v - err[q][0])
                worst_low = (case == "pess") == (kind == "min")  # the low end is worst for a min target
                v = lo if worst_low else hi
            s[key] = ((v - t) if kind == "min" else (t - v)) / max(abs(t), 1e-12)
    if "gap" in targets:
        lo, hi = targets["gap"]["f_lo"], targets["gap"]["f_hi"]
        mid = 0.5 * (lo + hi)
        best = -1.0
        for g in row_gaps(row) if ok else []:
            e_lo, e_hi = g["f_lo"], g["f_hi"]
            if case != "nominal" and err:
                gm = 0.5 * (e_lo + e_hi)
                if case == "expected":
                    med = err.get("median", {})
                    e_lo, e_hi = e_lo - med.get("gap_lo", 0.0) * gm, e_hi - med.get("gap_hi", 0.0) * gm
                elif case == "pess":  # lower edge drops least, upper edge drops most
                    e_lo, e_hi = e_lo - err["gap_lo"][0] * gm, e_hi - err["gap_hi"][1] * gm
                else:
                    e_lo, e_hi = e_lo - err["gap_lo"][1] * gm, e_hi - err["gap_hi"][0] * gm
            best = max(best, min(lo - e_lo, e_hi - hi) / mid)
        s["gap"] = best
    s["min"] = min(s.values()) if s else 0.0
    return s


def interpolated_best(rows: list[dict], targets: dict, err: dict, case: str = "opt", samples: int = 11) -> float:
    """Best overall slack between grid points: per arm (kind, TPMS mode), each constraint's slack is interpolated
    linearly along each 1-D grid segment or bilinearly over each 2-D grid square (all corners present), the minimum
    over constraints taken at samples x samples points, and the maximum returned. Interpolation is an estimate,
    not a bound; it stops a design that sits between grid points (e.g. a density cap between two TPMS densities)
    from being reported NOT_FOUND."""
    arms = {}
    for r in rows:
        sp = r["spec"]
        arms.setdefault((sp["kind"], sp["params"].get("mode")), []).append(r)
    t = np.linspace(0.0, 1.0, samples)
    best = -np.inf
    for (kind, _), rs in arms.items():
        names = list(box(kind))
        sl = {}
        for r in rs:
            s = slacks(r, targets, err_for(r["spec"], err), case)
            sl[tuple(round(r["spec"]["params"][k], 6) for k in names)] = np.array([v for k, v in s.items() if k != "min"])
        axes = [sorted({key[i] for key in sl}) for i in range(len(names))]
        if len(names) == 1:
            xs = axes[0]
            for a, b in zip(xs[:-1], xs[1:]):
                v = (1 - t)[:, None] * sl[(a,)] + t[:, None] * sl[(b,)]
                best = max(best, float(v.min(axis=1).max()))
        else:
            xs, ys = axes
            for i in range(len(xs) - 1):
                for j in range(len(ys) - 1):
                    c = [(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i], ys[j + 1]), (xs[i + 1], ys[j + 1])]
                    if not all(k in sl for k in c):
                        continue
                    u, w = np.meshgrid(t, t, indexing="ij")
                    u, w = u.ravel()[:, None], w.ravel()[:, None]
                    v = ((1 - u) * (1 - w) * sl[c[0]] + u * (1 - w) * sl[c[1]] + (1 - u) * w * sl[c[2]]
                         + u * w * sl[c[3]])
                    best = max(best, float(v.min(axis=1).max()))
        best = max(best, max(float(v.min()) for v in sl.values()))
    return best


def oracle(rows: list[dict], targets: dict, err: dict | None = None, top: int = 5,
           domain: dict | None = None) -> dict:
    """Feasibility verdict over atlas rows for normalized targets, with the search tier's error ranges.

    err: error_model() (default: loaded from error_model_path(), amm.data). FEASIBLE: some cell meets every target at the
    pessimistic end of every error range. NOT_FOUND_IN_FAMILIES: every cell misses some target even at the
    optimistic end, and so does the grid interpolation between cells (interpolated_best). BORDERLINE otherwise. Grid resolution and gaps that open only beyond the search tier are not
    covered (results/atlas/NOTES.md). Only rows inside the calibrated domain (error_domain) count; the verdict is
    stated for that domain, which the result names."""
    err = error_model() if err is None else err
    domain = error_domain() if domain is None else domain
    inside = [r for r in rows if calibrated(r["spec"], domain)]
    excluded = len(rows) - len(inside)
    rows = inside
    scored = []
    for r in rows:
        e = err_for(r["spec"], err)
        sp, so, sn = slacks(r, targets, e, "pess"), slacks(r, targets, e, "opt"), slacks(r, targets)
        scored.append((sp["min"], so["min"], sn["min"], r))
    scored.sort(key=lambda x: (-x[0], -x[2]))
    n_clear = sum(x[0] > 0 for x in scored)
    n_possible = sum(x[1] > 0 for x in scored)
    between = interpolated_best(rows, targets, err, "opt") if rows else -np.inf
    verdict = "FEASIBLE" if n_clear else ("NOT_FOUND_IN_FAMILIES" if n_possible == 0 and between <= 0 else "BORDERLINE")
    best = [dict(spec=x[3]["spec"], slack_pess=x[0], slack_opt=x[1], slack_nominal=x[2]) for x in scored[:top]]
    return dict(verdict=verdict, n_cells=len(rows), n_clear=n_clear, n_possible=n_possible, best=best,
                interpolated_opt=between, domain=domain, n_outside_domain=excluded)
