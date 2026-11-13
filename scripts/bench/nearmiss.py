"""Near-miss infeasible briefs (class R, added 2026-11-05 after the pilot; results/bench/NOTES.md section 5).

A near-miss target is one the search tier says is met but no design meets: the NOMINAL search value of the best
cell (the number `evaluate` and `search` print) clears it, while the certificate refutes every candidate. These are
the briefs where a release without a certificate is provably wrong.
Why nominal, not median-corrected ("expected"): on frontier cells the corrected value is within about 2.5 % of the
limit, inside the certificate's 2-4 % guard band, so no target lies between a refutable bound and the corrected
value (first scenarios, nearmiss_log.jsonl: "no window"). The nominal values run 3-36 % high (calibrated one-sided
error), which is the trap an agent without certificates can fall into.

Construction, per brief (material, quantity q in E100 | G | bulk, density cap on a TPMS grid point):
  1. cells = every valid atlas cell with search density <= cap (thin cells included: an agent may pick them);
  2. the certificate's top rung (64, 80, 96; 5 grid phases each) of the K best cells by nominal q gives each
     cell's guarded upper bound U (stiffness converges from above, so U bounds the limit; amm.certify.static_verdict);
  3. the window is (max U, max nominal); t = its geometric middle, rounded UP to the 3 significant figures the
     text states (the nominal slack of the best cell must stay > 0 after rounding; its expected slack is recorded);
  4. proof obligations, all at the exact stated t: every cell whose NOMINAL search value reaches t (true <= search
     for stiffness, calibrated one-sided error) and the 3 best designs of a nominal-objective BoTorch search (budget
     48, the tool agents use) must be refuted (U < t). A cell or design that is not refuted moves max U up and the
     window is recomputed; no window -> next scenario.
Truth: refuse (NOT_FOUND_IN_FAMILIES). Not a proof over the continuous family: designs between grid points that the
search did not visit are not covered. A release is scored by its own certificate, so a certified release would
show the label wrong (outcome "label_error").

    nearmiss.py [N=10] -> bench/v1/work/R01.json ... and bench/v1/nearmiss_log.jsonl (every scenario tried)
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
from amm import atlas, certify, units  # noqa: E402

OUT = build.OUT
CACHE = OUT / "work" / "rung_top"
SEED = 20261106
K_TOP = 3
RUNG = (64, 80, 96)  # the certificate's top rung: the first rung's bounds sit at the search value (no window)
QKEY = {"E100": "E100_min", "G": "G_min", "bulk": "bulk_min"}
CAPS = (0.16, 0.20, 0.24, 0.28, 0.32)


def all_rows(nu):
    return [r for r in atlas.load(str(ROOT / "results" / "atlas" / f"atlas_nu{nu:g}.jsonl")) if r.get("valid")]


def rung1(spec, nu) -> dict:
    """Top-rung static guard of a design (target-independent with a one-rung ladder), cached on disk."""
    key = hashlib.sha256(json.dumps(dict(spec=spec, nu=nu, rung=RUNG), sort_keys=True).encode()).hexdigest()[:16]
    f = CACHE / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    st = certify.static_block(spec, {}, nu=nu, ladder=(RUNG,))
    q = (st.get("convergence") or {}).get("quantities")
    out = dict(spec=spec, nu=nu, numerics_ok=st["numerics_ok"], seconds=round(time.perf_counter() - t0, 1),
               quantities={k: {kk: v[kk] for kk in ("lower", "upper", "extrapolated", "converged")} for k, v in
                           (q or {}).items()})
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, default=float), encoding="utf-8")
    return out


def refuted(r1: dict, key: str, t: float, cap: float) -> bool:
    v = certify.static_verdict(r1["quantities"] or None, {key: t, "density_max": cap}, r1["numerics_ok"])
    return v["targets"][key] == "refuted" or v["verdict"] == "refuted"


def search_designs(nu, cap, key, t, rows):
    from amm import search as srch
    r = srch.search({"density_max": cap, key: t}, nu=nu, families=["tpms", "struts", "resonator"], budget=48, q=8,
                    objective="nominal", seed=0, atlas_rows=rows)
    return [b["spec"] for b in r["best"][:3]]


def scenario(mat, q, cap, log) -> dict | None:
    nu, key = build.MAT_NU[mat], QKEY[q]
    rows = [r for r in all_rows(nu) if r["density"] <= cap]
    ex = {id(r): build.expected(r)[q] if atlas.calibrated(r["spec"], atlas.error_domain()) else r[q] for r in rows}
    best = sorted(rows, key=lambda r: -r[q])  # by nominal: the values the tools print
    e_max = best[0][q]  # window top: the best nominal value (name kept for the log format)
    certified = {}  # canon spec -> rung1

    def U(spec):
        k = json.dumps(spec, sort_keys=True)
        if k not in certified:
            certified[k] = rung1(spec, nu)
        r1 = certified[k]
        if not r1["numerics_ok"] or q not in r1["quantities"]:
            return math.inf  # a failed solve refutes nothing (audit F05): the cell stays a candidate
        return r1["quantities"][q]["upper"]

    u_max = max(U(r["spec"]) for r in best[:K_TOP])
    for _ in range(6):
        if not u_max * 1.005 < e_max * 0.995:
            log(dict(mat=mat, q=q, cap=cap, result="no window", u_max=u_max, e_max=e_max))
            return None
        t_norm = math.sqrt(u_max * e_max)
        t_phys = build.stiff_phys(t_norm, mat, "up")
        t, _, _ = units.normalize({"material": mat, key: t_phys})
        t = t[key]
        if not u_max < t < e_max:
            log(dict(mat=mat, q=q, cap=cap, result="rounding leaves the window", t=t, u_max=u_max, e_max=e_max))
            return None
        possible = [r["spec"] for r in rows if r[q] >= t]
        searched = search_designs(nu, cap, key, t, [r for r in rows if atlas.calibrated(r["spec"], atlas.error_domain())])
        bad = [(s, U(s)) for s in possible + searched if U(s) >= t]
        if not bad:
            proof = [dict(spec=s, upper=U(s), source="atlas, nominal >= t" if s in possible else "search top 3")
                     for s in possible + searched]
            return dict(material=mat, q=q, key=key, cap=cap, t=t, t_phys=t_phys, e_max=e_max, u_max=u_max,
                        best_nominal=best[0]["spec"], nominal_slack=(e_max - t) / t,
                        expected_slack=(ex[id(best[0])] - t) / t, proof=proof,
                        n_certified=len(certified))
        u_max = max(u_max, max(u for _, u in bad))
        log(dict(mat=mat, q=q, cap=cap, result="raised u_max", by=[b[0] for b in bad], u_max=u_max))
    return None


def main(n=10):
    rng = np.random.default_rng(SEED)
    lf = OUT / "nearmiss_log.jsonl"

    def log(d):
        print(json.dumps(d, default=float)[:300], flush=True)
        with open(lf, "a", encoding="utf-8") as f:
            f.write(json.dumps(d, default=float) + "\n")
    scen = [(m, q, c) for m in build.MAT_NU for q in ("E100", "G", "bulk") for c in CAPS]
    scen = [scen[i] for i in rng.permutation(len(scen))]
    done = sorted(OUT.glob("work/R*.json"))
    used = {(json.loads(p.read_text())["material"], json.loads(p.read_text())["q"]) for p in done}
    k = len(done)
    fails, tried = {}, set()  # a (material, quantity) pair that failed twice is dropped (bulk: no window, 2026-11-05)
    if lf.exists():
        for line in lf.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            if "result" in d and "mat" in d and "cap" in d:
                tried.add((d["mat"], d["q"], d["cap"]))
                if d["result"] == "no window":
                    fails[(d["mat"], d["q"])] = fails.get((d["mat"], d["q"]), 0) + 1
    progress = True
    while k < n and progress:  # repeat passes: a pair skipped for spread is retried once no fresh pair is left
        progress = False
        for mat, q, cap in scen:
            if k >= n:
                break
            k, progress = _try(mat, q, cap, k, n, scen, used, fails, tried, log, progress)


def _try(mat, q, cap, k, n, scen, used, fails, tried, log, progress):
    for _ in (0,):
        if (mat, q, cap) in tried or fails.get((mat, q), 0) >= 2:
            return k, progress
        fresh = {(m2, q2) for m2, q2, c2 in scen if (m2, q2) not in used and fails.get((m2, q2), 0) < 2
                 and (m2, q2, c2) not in tried}
        if (mat, q) in used and fresh:  # spread over material x quantity while an untried pair is left
            return k, progress
        t0 = time.perf_counter()
        tried.add((mat, q, cap))
        res = scenario(mat, q, cap, log)
        if res is None:
            fails[(mat, q)] = fails.get((mat, q), 0) + 1
            return k, True
        k += 1
        bid = f"R{k:02d}"
        res.update(id=bid, seconds=round(time.perf_counter() - t0, 1),
                   intended=dict(material=mat, cell_size=None,
                                 targets={"density_max": cap, res["key"]: res["t_phys"]}),
                   truth=dict(decision="refuse", verdict="NOT_FOUND_IN_FAMILIES", near_miss=True))
        (OUT / "work" / f"{bid}.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
        used.add((mat, q))
        log(dict(id=bid, mat=mat, q=q, cap=cap, t=res["t"], nominal_slack=res["nominal_slack"],
                 expected_slack=res["expected_slack"],
                 n_proof=len(res["proof"]), result="near-miss brief"))
        return k, True
    return k, progress


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
