"""V3 analysis (tests and verdict as pre-registered in results/verification/v3/NOTES.md section 6).

    analyze.py [--out DIR]
Writes summary.json, T5_v3.csv, fig_v3_success_vs_budget.png and prints a report.
"""
from __future__ import annotations

import csv
import itertools
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "results/verification/v3"
BUDGET = 48
M = ["M1", "M2", "M3", "M4", "M5", "M6"]
NAME = {"M1": "atlas-only", "M2": "Sobol", "M3": "differential evolution", "M4": "BO full (amm)",
        "M5": "BO without atlas seeding", "M6": "BO without error correction"}
BASE, ABL = ["M1", "M2", "M3"], ["M5", "M6"]
RNG = np.random.default_rng(20261108)


def tobool(x):
    return x if isinstance(x, bool) else str(x) == "True"


def holm(ps):
    order = np.argsort(ps)
    adj, run = [0.0] * len(ps), 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - r) * ps[i]))
        adj[i] = run
    return adj


def mcnemar(a, b):
    """exact two-sided McNemar: a, b boolean arrays (a = M4)."""
    n10, n01 = int(np.sum(a & ~b)), int(np.sum(~a & b))
    p = 1.0 if n10 + n01 == 0 else binomtest(n10, n10 + n01, 0.5).pvalue
    return dict(m4_only=n10, other_only=n01, p=float(p))


def signflip(d):
    d = np.asarray(d, float)
    n = len(d)
    obs = abs(d.mean())
    if n <= 20:
        S = np.array(list(itertools.product([1, -1], repeat=n)), dtype=np.int8) if n <= 16 else None
        if S is None:  # 2^n rows in chunks
            cnt, tot = 0, 0
            for first in itertools.product([1, -1], repeat=n - 14):
                rest = np.array(list(itertools.product([1, -1], repeat=14)), dtype=np.int8)
                s = np.hstack([np.tile(first, (len(rest), 1)), rest])
                v = np.abs(s @ d / n)
                cnt += int(np.sum(v >= obs - 1e-12))
                tot += len(v)
            return cnt / tot
        v = np.abs(S @ d / n)
        return float(np.mean(v >= obs - 1e-12))
    s = RNG.choice([1, -1], size=(100000, n))
    return float(np.mean(np.abs(s @ d / n) >= obs - 1e-12))


def boot(d, R=10000):
    d = np.asarray(d, float)
    idx = RNG.integers(0, len(d), size=(R, len(d)))
    m = d[idx].mean(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def load():
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / "rows").glob("*.json"))]
    for r in rows:
        r["certified"] = tobool(r["certified"])
    return rows


def method_table(rows, ids, methods):
    tab = {}
    for m in methods:
        rs = [r for r in rows if r["method"] == m and r["target_id"] in ids]
        if not rs:
            continue
        succ = np.array([r["certified"] for r in rs])
        C = np.array([r["evals_to_final"] if r["certified"] else BUDGET for r in rs], float)
        ev = sum(r["evals_spent"] for r in rs)
        evs = sum(r["evaluator_seconds"] for r in rs)
        cs = [r["certified_slack"] for r in rs if r["certified"] and r["certified_slack"] is not None]
        verdicts = {}
        for r in rs:
            verdicts[r["cert_verdict"]] = verdicts.get(r["cert_verdict"], 0) + 1
        tab[m] = dict(method=NAME[m], n=len(rs), certified=int(succ.sum()), rate=float(succ.mean()),
                      rate_ci=boot(succ.astype(float)), verdicts=verdicts,
                      search_tier_found_nominal=int(sum(r["slack_nominal"] > 0 for r in rs)),
                      search_tier_found_expected=int(sum(r["slack_expected"] > 0 for r in rs)),
                      final_from_atlas=int(sum(tobool(r["from_atlas"]) for r in rs)),
                      median_slack_expected=float(np.median([r["slack_expected"] for r in rs])),
                      median_slack_nominal=float(np.median([r["slack_nominal"] for r in rs])),
                      median_certified_slack=float(np.median(cs)) if cs else None,
                      evals_spent_total=int(ev), evals_spent_mean=float(ev / len(rs)),
                      evals_to_final_mean=float(np.mean([r["evals_to_final"] for r in rs])),
                      cost_C_mean=float(C.mean()),
                      cert_calls=int(sum(r["cert_calls"] for r in rs)),
                      throughput_evals_per_s=float(ev / evs) if evs else None,
                      latency_search_s_median=float(np.median([r["search_seconds"] for r in rs])),
                      latency_search_s_max=float(max(r["search_seconds"] for r in rs)),
                      search_s_total=float(sum(r["search_seconds"] for r in rs)),
                      cert_s_total=float(sum(r["cert_seconds"] for r in rs)),
                      cert_s_median_when_called=float(np.median([r["cert_seconds"] for r in rs if r["cert_calls"]]))
                      if any(r["cert_calls"] for r in rs) else None,
                      workflow_s_median=float(np.median([r["workflow_seconds"] for r in rs])),
                      workflow_s_total=float(sum(r["workflow_seconds"] for r in rs)))
    return tab


def paired(rows, ids, m, o):
    a = {r["target_id"]: r for r in rows if r["method"] == m and r["target_id"] in ids}
    b = {r["target_id"]: r for r in rows if r["method"] == o and r["target_id"] in ids}
    t = sorted(set(a) & set(b))
    sa = np.array([a[i]["certified"] for i in t])
    sb = np.array([b[i]["certified"] for i in t])
    Ca = np.array([a[i]["evals_to_final"] if a[i]["certified"] else BUDGET for i in t], float)
    Cb = np.array([b[i]["evals_to_final"] if b[i]["certified"] else BUDGET for i in t], float)
    mc = mcnemar(sa, sb)
    return dict(other=o, n=len(t), success_m4=int(sa.sum()), success_other=int(sb.sum()),
                diff_rate=float(sa.mean() - sb.mean()), diff_rate_ci=boot(sa.astype(float) - sb.astype(float)),
                mcnemar=mc, cost_m4=float(Ca.mean()), cost_other=float(Cb.mean()),
                cost_diff=float((Ca - Cb).mean()), cost_diff_ci=boot(Ca - Cb), cost_signflip_p=signflip(Ca - Cb))


def verdict(tests, tab):
    for k, adj in (("mcnemar", "p_holm"), ("cost", "cost_p_holm")):
        ps = [t["mcnemar"]["p"] if k == "mcnemar" else t["cost_signflip_p"] for t in tests]
        for t, a in zip(tests, holm(ps)):
            t[adj] = a
    by = {t["other"]: t for t in tests}
    best_n = max(tab[b]["certified"] for b in BASE)
    best = [b for b in BASE if tab[b]["certified"] == best_n]
    s4 = tab["M4"]["certified"]
    A = s4 > best_n and all(by[b]["p_holm"] < 0.05 for b in best)
    B = s4 >= best_n and all(tab["M4"]["cost_C_mean"] <= 0.5 * tab[b]["cost_C_mean"] and by[b]["cost_p_holm"] < 0.05
                             for b in best)
    worse = []
    for b in BASE:
        Ab = tab[b]["certified"] > s4 and by[b]["p_holm"] < 0.05
        Bb = tab[b]["certified"] >= s4 and tab[b]["cost_C_mean"] <= 0.5 * tab["M4"]["cost_C_mean"] \
            and by[b]["cost_p_holm"] < 0.05
        if Ab or Bb:
            worse.append(dict(baseline=b, A=bool(Ab), B=bool(Bb)))
    v = "clear advantage" if (A or B) else ("baseline better" if worse else "no clear advantage")
    return dict(verdict=v, best_baselines=best, best_baseline_success=best_n, m4_success=s4, criterion_A=bool(A),
                criterion_B=bool(B), baselines_better=worse)


def curves(ids, methods):
    """fraction of targets whose best design so far has nominal (expected) slack > 0, per evaluation count."""
    out = {}
    for m in methods:
        Fn, Fe = [], []
        for tid in ids:
            p = OUT / "search" / f"{tid}_{m}.json"
            if not p.exists():
                continue
            r = json.loads(p.read_text(encoding="utf-8"))
            sb = r.get("seed_best") or {}
            bn = [sb.get("nominal", -np.inf)] if m != "M6" else [sb.get("nominal", -np.inf)]
            be = [sb.get("expected", -np.inf)]
            obj = r["objective"]
            # best-so-far by the method's own objective; report that design's nominal / expected slack
            cur = (sb.get(obj, -np.inf), sb.get("nominal", -np.inf), sb.get("expected", -np.inf))
            seq_n, seq_e = [cur[1]], [cur[2]]
            for e in r["evals"]:
                v = e[f"slack_{obj}"]
                if v > cur[0]:
                    cur = (v, e["slack_nominal"], e["slack_expected"])
                seq_n.append(cur[1])
                seq_e.append(cur[2])
            while len(seq_n) < BUDGET + 1:
                seq_n.append(seq_n[-1])
                seq_e.append(seq_e[-1])
            Fn.append(np.array(seq_n) > 0)
            Fe.append(np.array(seq_e) > 0)
        if Fn:
            out[m] = dict(nominal=np.mean(Fn, axis=0).tolist(), expected=np.mean(Fe, axis=0).tolist(), n=len(Fn))
    return out


COL = {"M1": "#2a78d6", "M2": "#eb6834", "M3": "#1baf7a", "M4": "#eda100", "M5": "#e87ba4", "M6": "#008300"}
STY = {"M1": "-", "M2": "--", "M3": "-.", "M4": "-", "M5": ":", "M6": (0, (5, 1, 1, 1))}
MRK = {"M1": "o", "M2": "s", "M3": "^", "M4": "D", "M5": "v", "M6": "P"}


def figure(cv, tab, n):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.0), gridspec_kw=dict(width_ratios=[1.6, 1]))
    ax = axes[0]
    x = np.arange(BUDGET + 1)
    for m in M:
        if m not in cv:
            continue
        y = np.array(cv[m]["nominal"])
        if m == "M1":
            ax.plot([0], [y[0]], marker=MRK[m], ms=8, ls="none", color=COL[m], label=NAME[m])
            continue
        ax.plot(x, y, ls=STY[m], lw=2, color=COL[m], label=NAME[m])
        ax.plot([BUDGET], [y[-1]], marker=MRK[m], ms=8, color=COL[m], ls="none", markeredgecolor="white")
    ax.set_xlabel("search-tier evaluations")
    ax.set_ylabel("fraction of targets met at search tier\n(best-so-far design, nominal slack > 0)")
    ax.set_xlim(-1.5, BUDGET + 1.5)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(alpha=0.25, lw=0.6)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.set_title(f"(a) search tier, {n} primary targets", fontsize=10, loc="left")
    ax = axes[1]
    ms = [m for m in M if m in tab]
    vals = [tab[m]["rate"] for m in ms]
    lo = [tab[m]["rate"] - tab[m]["rate_ci"][0] for m in ms]
    hi = [tab[m]["rate_ci"][1] - tab[m]["rate"] for m in ms]
    ax.bar(range(len(ms)), vals, color=[COL[m] for m in ms], width=0.7, edgecolor="white", linewidth=2)
    ax.errorbar(range(len(ms)), vals, yerr=[lo, hi], fmt="none", ecolor="#52514e", capsize=3, lw=1)
    for i, m in enumerate(ms):
        ax.text(i, 0.01, f"{tab[m]['certified']}/{tab[m]['n']}", ha="center", va="bottom", fontsize=8, color="#0b0b0b")
    ax.set_xticks(range(len(ms)))
    ax.set_xticklabels([m for m in ms], fontsize=9)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("certified success (95 % bootstrap CI)")
    ax.set_title("(b) certified at the final budget", fontsize=10, loc="left")
    ax.grid(axis="y", alpha=0.25, lw=0.6)
    for a in axes:
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    fig.text(0.99, 0.005, "M1 atlas-only (0 evaluations), M2 Sobol, M3 DE, M4 BO full, M5 BO no seeding, "
             "M6 BO no correction; budget 48", ha="right", fontsize=7, color="#52514e")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / "fig_v3_success_vs_budget.png", dpi=200)


def coverage(targets):
    """Calibration check: observed search-tier error of every certified-or-attempted final design vs the model."""
    sys.path.insert(0, str(HERE))
    import common
    from amm import atlas
    out = []
    tmap = {t["target_id"]: t for t in targets}
    for p in sorted((OUT / "certs").glob("*.summary.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        tid = s["target_id"]
        # search-tier values of the design (from any search record of it)
        rec = None
        for q in (OUT / "search").glob(f"{tid}_M*.json"):
            r = json.loads(q.read_text(encoding="utf-8"))
            if r["final"]["hash"] == s["spec_hash"]:
                rec = r["final"]
                break
        if rec is None:
            continue
        e = atlas.err_for(s["spec"], common.ERR)
        row = dict(target_id=tid, nu=tmap[tid]["nu"], kind=s["spec"]["kind"], verdict=s["verdict"])
        for qn in ("E100", "G", "bulk"):
            b = s["bounds"].get(qn)
            v = rec["values"].get(qn)
            if b and v and b["extrapolated"] and b["converged"]:
                obs = v / b["extrapolated"] - 1
                rng = e.get(qn)
                row[qn] = dict(obs=obs, median=e.get("median", {}).get(qn), range=rng,
                               inside=bool(rng and rng[0] - 1e-12 <= obs <= rng[1] + 1e-12))
        ge = s.get("gap_edges_extrapolated")
        if ge and ge[0] is not None and ge[1] is not None and rec["gaps"]:
            g = tmap[tid]["targets"]["gap"]
            best = max(rec["gaps"], key=lambda x: min(g["f_lo"] - x["f_lo"], x["f_hi"] - g["f_hi"]))
            gm = 0.5 * (best["f_lo"] + best["f_hi"])
            for nm, sv, ev in (("gap_lo", best["f_lo"], ge[0]), ("gap_hi", best["f_hi"], ge[1])):
                obs = (sv - ev) / gm
                rng = e.get(nm)
                row[nm] = dict(obs=obs, median=e.get("median", {}).get(nm), range=rng,
                               inside=bool(rng and rng[0] - 1e-12 <= obs <= rng[1] + 1e-12))
        out.append(row)
    agg = {}
    for r in out:
        for qn in ("E100", "G", "bulk", "gap_lo", "gap_hi"):
            if qn in r:
                a = agg.setdefault(str(r["nu"]), {}).setdefault(qn, dict(n=0, inside=0, obs=[], above_median=0))
                a["n"] += 1
                a["inside"] += int(r[qn]["inside"])
                a["obs"].append(r[qn]["obs"])
                a["above_median"] += int(r[qn]["median"] is not None and r[qn]["obs"] > r[qn]["median"])
    for nu in agg:
        for qn, a in agg[nu].items():
            a["obs_median"] = float(np.median(a["obs"]))
            a["obs_min"], a["obs_max"] = float(min(a["obs"])), float(max(a["obs"]))
            del a["obs"]
    return dict(per_design=out, by_nu=agg)


def main():
    targets = json.loads((OUT / "targets.json").read_text(encoding="utf-8"))["targets"]
    rows = load()
    prim = [t["target_id"] for t in targets if t["set"] == "primary"]
    done = [i for i in prim if all(any(r["target_id"] == i and r["method"] == m for r in rows) for m in ["M1", "M2", "M3", "M4", "M5"])]
    tab = method_table(rows, set(done), M)
    tests = [paired(rows, set(done), "M4", b) for b in BASE]
    v = verdict(tests, tab)
    sec = [paired(rows, set(done), "M4", a) for a in ABL if a in tab]
    if sec:
        for t, a in zip(sec, holm([t["mcnemar"]["p"] for t in sec])):
            t["p_holm"] = a
        for t, a in zip(sec, holm([t["cost_signflip_p"] for t in sec])):
            t["cost_p_holm"] = a
    by_nu = {str(nu): method_table(rows, {t["target_id"] for t in targets if t["set"] == "primary"
                                          and t["nu"] == nu and t["target_id"] in done}, M)
             for nu in (0.3, 0.342, 0.39)}
    by_type = {tt: method_table(rows, {t["target_id"] for t in targets if t["set"] == "primary"
                                       and t["target_type"] == tt and t["target_id"] in done}, M)
               for tt in ("static", "gap", "combined")}
    calib_ids = {t["target_id"] for t in targets if t["set"] == "calibration"}
    calib = [dict(target_id=r["target_id"], nu=r["nu"], method=r["method"], certified=r["certified"],
                  verdict=r["cert_verdict"], slack_nominal=r["slack_nominal"], slack_expected=r["slack_expected"],
                  final=r["final_kind"] + " " + r["final_params"]) for r in rows if r["target_id"] in calib_ids]
    cov = coverage(targets)
    certs = list((OUT / "certs").glob("*.summary.json"))
    cert_s = [json.loads(p.read_text(encoding="utf-8"))["seconds"] for p in certs]
    st = json.loads((OUT / "state.json").read_text(encoding="utf-8")) if (OUT / "state.json").exists() else {}
    cv = curves(done, M)
    summary = dict(n_primary_targets=len(done), primary_targets=done, budget=BUDGET, methods=NAME, per_method=tab,
                   primary_tests=tests, verdict=v, secondary_tests=sec, by_nu=by_nu, by_target_type=by_type,
                   calibration_targets=calib, error_model_coverage=cov["by_nu"],
                   unique_certificates=len(certs), certificate_seconds_total=float(sum(cert_s)),
                   certificate_seconds_median=float(np.median(cert_s)) if cert_s else None,
                   run_state=dict(spent_hours=st.get("spent_seconds", 0) / 3600, cuts=st.get("cuts")),
                   curves=cv)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    (OUT / "coverage_per_design.json").write_text(json.dumps(cov["per_design"], indent=1, default=float),
                                                  encoding="utf-8")
    keys = ["method", "n", "certified", "rate", "rate_ci", "search_tier_found_nominal", "search_tier_found_expected",
            "final_from_atlas", "median_slack_expected", "median_certified_slack", "evals_spent_mean",
            "evals_to_final_mean", "cost_C_mean", "cert_calls", "throughput_evals_per_s", "latency_search_s_median",
            "cert_s_median_when_called", "workflow_s_median", "workflow_s_total"]
    with open(OUT / "T5_v3.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id"] + keys + ["mcnemar_vs_M4_p", "holm_p", "cost_signflip_p", "cost_holm_p"])
        allt = {t["other"]: t for t in tests + sec}
        for m in M:
            if m not in tab:
                continue
            t = allt.get(m, {})
            w.writerow([m] + [json.dumps(tab[m][k]) if isinstance(tab[m][k], list) else tab[m][k] for k in keys]
                       + [t.get("mcnemar", {}).get("p", ""), t.get("p_holm", ""), t.get("cost_signflip_p", ""),
                          t.get("cost_p_holm", "")])
    figure(cv, tab, len(done))
    print(json.dumps(dict(n=len(done), verdict=v, per_method={m: {k: tab[m][k] for k in ("certified", "n", "rate", "rate_ci",
                                                                                      "cost_C_mean", "verdicts")}
                                                           for m in tab},
                          tests=[{k: t[k] for k in ("other", "mcnemar", "p_holm", "cost_diff", "cost_signflip_p",
                                                    "cost_p_holm", "diff_rate_ci")} for t in tests],
                          secondary=[{k: t.get(k) for k in ("other", "mcnemar", "p_holm", "cost_diff",
                                                            "cost_signflip_p", "cost_p_holm")} for t in sec]),
                     indent=1, default=float))


if __name__ == "__main__":
    main()
