"""V14 (2026-11-09): every stored certificate and gap report of the paper re-judged by the released rules of amm 0.2.0
(audit round 3): (1) a gap edge that drifts monotonically toward the claim must pass the order fit, otherwise it has
no safe value (amm.bloch._edge_guard); (2) the finest resolution of a block must put FEATURE_MIN_VOXELS = 3 voxels
across the load-path feature, otherwise a certified verdict becomes undetermined (amm.certify.feature_check).

No solves: amm.certify.rescore_certificate / rescore_bloch re-apply the rules to the stored counts, edge estimates and
phase edges, which the rules do not change, so each verdict is the one the released code gives on the same solves.
Check: with the feature rule off, only the drift-toward-claim edges change verdicts (asserted below).

Outputs (results/verification/v14/):
  bench/        the search benchmark (copy of results/verification/v3 with re-scored certificates, summaries, rows and
                runs.csv); then `python scripts/verify/v3/analyze.py --out results/verification/v14/bench`
  witnesses.json  the witness certificates of the benchmark briefs (bench/v1/work)
  engineering.json  the engineering certificates (v6 cases, v11 robust mount rerun)
  gaps.json     the twelve gaps certified under the earlier rule (safe edges, branches, verdicts) and the reference
                grading of every guarded edge in the DOLFINx and finite-cell comparisons under the released rule
  summary.json  the counts quoted in the paper

    python scripts/experiments/v14_rule_rescore.py
CPU only, about a minute; no LLM.
"""
import collections
import glob
import json
import shutil
import sys
from pathlib import Path

import amm  # noqa: F401
from amm import bloch, certify

ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / "results/verification/v3"
OUT = ROOT / "results/verification/v14"
BENCH = OUT / "bench"
sys.path.insert(0, str(ROOT / "scripts/verify/v3"))
sys.path.insert(0, str(ROOT / "scripts/experiments"))
import common as v3common  # noqa: E402
import driver as v3driver  # noqa: E402
from v12_gap_guard_audit import cases as gap_cases  # noqa: E402

DRIFT_ONLY_EXPECTED = None  # filled by the first pass and reported


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def dump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, default=float), encoding="utf-8")


def why(c):
    b = c["blocks"]
    for k in ("bloch", "static"):
        v = (b.get(k) or {}).get("verdict") or {}
        if v.get("verdict") != "certified" and v.get("reason"):
            return f"{k}: {v['reason']}"
    return None


# ---------------------------------------------------------------- benchmark
def bench():
    if BENCH.exists():
        shutil.rmtree(BENCH)
    (BENCH / "certs").mkdir(parents=True)
    for name in ("targets.json", "state.json"):
        shutil.copy2(V3 / name, BENCH / name)
    shutil.copytree(V3 / "search", BENCH / "search")
    tg = {t["target_id"]: t for t in load(V3 / "targets.json")["targets"]}
    changes, drift_only = [], []
    for f in sorted(glob.glob(str(V3 / "certs/*.json"))):
        if f.endswith(".summary.json"):
            continue
        c = load(f)
        s_old = load(f[:-5] + ".summary.json")
        r = certify.rescore_certificate(c)
        r0 = certify.rescore_certificate(c, feature_min_voxels=0)
        tid = s_old["target_id"]
        s = v3common.cert_summary(r, tg[tid]["targets"])
        for k in ("target_id", "spec", "methods", "wall_seconds_v3", "finished"):
            s[k] = s_old.get(k)
        s["verdict_before_rules"] = s_old["verdict"]
        dump(BENCH / "certs" / Path(f).name, r)
        dump(BENCH / "certs" / (Path(f).stem + ".summary.json"), s)
        if r0["verdict"] != c["verdict"]:
            drift_only.append(Path(f).stem)
        if r["verdict"] != c["verdict"]:
            feat = r["blocks"].get("bloch", {}).get("feature") or r["blocks"]["static"].get("feature") or {}
            changes.append(dict(cert=Path(f).stem, kind=c["spec"]["kind"], params=c["spec"]["params"],
                                before=c["verdict"], after=r["verdict"], reason=why(r),
                                rule=("feature" if not feat.get("passed", True) else "drift toward claim"),
                                feature_voxels=feat.get("voxels"), methods=s_old.get("methods")))
    (BENCH / "rows").mkdir()
    for t in tg.values():
        for m in ("M1", "M2", "M3", "M4", "M5", "M6"):
            if (BENCH / "search" / f"{t['target_id']}_{m}.json").exists():
                dump(BENCH / "rows" / f"{t['target_id']}_{m}.json", v3driver.row_for(BENCH, t, m))
    v3driver.write_csv(BENCH)
    summ = [load(p) for p in glob.glob(str(BENCH / "certs/*.summary.json"))]
    return dict(n_certificates=len(summ),
                before=dict(collections.Counter(s["verdict_before_rules"] for s in summ)),
                after=dict(collections.Counter(s["verdict"] for s in summ)),
                changed=changes, changed_by_rule=dict(collections.Counter(x["rule"] for x in changes)),
                drift_rule_alone_changes=drift_only)


# ---------------------------------------------------------------- witnesses
def witnesses():
    tg = {t["target_id"]: t["set"] for t in load(V3 / "targets.json")["targets"]}
    rows = []
    for f in sorted(glob.glob(str(ROOT / "bench/v1/work/**/*.json"), recursive=True)):
        try:
            c = load(f)
        except Exception:
            continue
        if not isinstance(c, dict) or "blocks" not in c or "spec" not in c:
            continue
        r = certify.rescore_certificate(c)
        brief = Path(f).stem.split("_")[0]
        rows.append(dict(file=str(Path(f).relative_to(ROOT)).replace("\\", "/"), brief=brief,
                         benchmark_set=tg.get(brief), kind=c["spec"]["kind"], params=c["spec"]["params"],
                         before=c["verdict"], after=r["verdict"], reason=why(r) if r["verdict"] != c["verdict"] else None))
    ch = [x for x in rows if x["before"] != x["after"]]
    return dict(n=len(rows), before=dict(collections.Counter(x["before"] for x in rows)),
                after=dict(collections.Counter(x["after"] for x in rows)), changed=ch,
                primary_targets_losing_witness=sorted({x["brief"] for x in ch if x["benchmark_set"] == "primary"})), rows


# ---------------------------------------------------------------- engineering
def engineering():
    rows = []
    pats = ["results/verification/v6/case1/session_*/certificates/*.json",
            "results/verification/v6/case2/session_*/certificates/*.json",
            "results/verification/v11/robust_mount/session_*/certificates/*.json"]
    for pat in pats:
        for f in sorted(glob.glob(str(ROOT / pat))):
            c = load(f)
            r = certify.rescore_certificate(c)
            bl = r["blocks"].get("bloch") or {}
            cv = bl.get("convergence") or {}
            rows.append(dict(file=str(Path(f).relative_to(ROOT)).replace("\\", "/"), kind=c["spec"]["kind"],
                             params=c["spec"]["params"], before=c["verdict"], after=r["verdict"], reason=why(r),
                             safe_interval_before=((c["blocks"].get("bloch") or {}).get("convergence") or {}).get(
                                 "safe_interval"),
                             safe_interval_after=cv.get("safe_interval"),
                             feature=bl.get("feature") or r["blocks"]["static"].get("feature"),
                             upper_edge=cv.get("upper_edge"), lower_edge=cv.get("lower_edge")))
    return rows


def rechecks():
    """Exported-mesh rechecks (v6 case*/recheck_*.json). They stored the edge sequences but not the phase edges, so
    the guard cannot be re-run in full; the released rules still decide them: an edge that drifts toward the claim
    without an admissible order has no safe value whatever the phase spread, an edge that fits an order keeps its
    stored safe value (the order-fit branch is unchanged), and the feature rule needs only the geometry."""
    out = []
    for case, name in (("case1", "design"), ("case2", "PA12"), ("case2", "316L")):
        p = ROOT / f"results/verification/v6/{case}/recheck_{name}.json"
        r = load(p)
        g = r["gap"]
        items = sorted((int(n), v["stl"]) for n, v in g["edges"].items())
        ns = [n for n, _ in items]
        h = [1 / n for n in ns]
        sides = []
        for i, side in enumerate(("lo", "hi")):
            f = [v[i] for _, v in items]
            d12, d23 = f[1] - f[0], f[2] - f[1]
            toward = d12 * d23 > 0 and (d23 > 0 if side == "lo" else d23 < 0)
            p_fit = bloch._order(h, f)
            sides.append(dict(side=side, edges=f, order=p_fit, drift_toward_claim=bool(toward),
                              fails_closed=bool(toward and p_fit is None)))
        feat = certify.feature_check(r["spec"], max(ns))
        before = g["verdict"]["verdict"]
        if before != "certified":
            after = before
        elif any(s["fails_closed"] for s in sides) or not feat["passed"]:
            after = "undetermined"
        elif any(s["order"] is None for s in sides):
            after = "not decidable from the stored record (phase edges not stored)"
        else:
            after = "certified"
        out.append(dict(file=str(p.relative_to(ROOT)).replace("\\", "/"), before=before, after=after, sides=sides,
                        feature=feat, safe_interval_stored=g["safe_interval"]))
    return out


# ---------------------------------------------------------------- the twelve gaps and the reference grading
def grade(safe, R, u, side):
    """sound / marginal / unsound against R +- 2u, conservative side: lower edge higher, upper edge lower."""
    if safe is None:
        return "no safe edge"
    if side == "lo":
        return "sound" if safe >= R + 2 * u else ("marginal" if safe >= R - 2 * u else "unsound")
    return "sound" if safe <= R - 2 * u else ("marginal" if safe <= R + 2 * u else "unsound")


def judge(edges, phase, claim):
    items = sorted((int(n), v) for n, v in edges.items())
    conv = bloch.gap_convergence({n: tuple(v) for n, v in items}, claim[0], claim[1], phase_edges=phase)
    br = []
    for e in (conv["lower_edge"], conv["upper_edge"]):
        br.append("order fit" if e.get("p") is not None else
                  ("drift toward claim: fails closed" if e.get("drift_toward_claim") and e.get("reason") else
                   ("phase noise" if e.get("extrapolated") is not None else "fails closed")))
    return conv, br


def gaps():
    old = {r["case"]: r for r in load(ROOT / "results/verification/v12/gap_guard_audit.json")}
    specs = {}
    for f in sorted(glob.glob(str(ROOT / "results/verification/dolfinx/*.json"))):
        d = load(f)
        if "amm_edges" in d:
            specs[d["case"]] = (d["spec"], d)
    v1b = load(ROOT / "results/verification/v1b/summary.json")
    rows = []
    for c in gap_cases():
        conv, br = judge(c["edges"], c["phase"], c["claim"])
        if c["case"] in specs:
            spec = specs[c["case"]][0]
        elif c["case"] in v1b:
            sp = v1b[c["case"]]
            spec = dict(family=sp["family"], kind=sp.get("kind") or "sphere_ligaments",
                        params=sp.get("params") or dict(c=0.357, w=0.109))
        else:
            spec = load(ROOT / "results/verification" / {
                "mount_PA12": "v6/case1/session_design/certificates/7db650ec44d50a1d_08d26401ae0bf0dc.json",
                "filter_PA12": "v6/case2/session_PA12/certificates/e5519f4fdbef64db_e212dc39bc22b626.json",
                "filter_316L": "v6/case2/session_316L/certificates/f1d00ed043a926f1_0dc7c12bea6f73f4.json"}[c["case"]])["spec"]
        feat = certify.feature_check(spec, max(int(n) for n in c["edges"]))
        certified = bool(conv["passed"] and feat["passed"])
        rows.append(dict(case=c["case"], src=c["src"], spec=spec, claim=c["claim"], ref=c["ref"],
                         safe_before=c["safe_stored"], safe_after=conv["safe_interval"], branches=br,
                         guard_passed=conv["passed"], feature=feat, certified=certified,
                         reason=(None if certified else ("feature" if conv["passed"] else "drift toward claim"
                                                         if any("drift" in b for b in br) else "guard"))))
    # reference grading of every guarded edge (DOLFINx comparison) under the released rule
    grades = []
    for case, (spec, d) in specs.items():
        conv, br = judge(d["amm_edges"], d["amm_phase_edges"], d["claim"])
        for i, side in enumerate(("lo", "hi")):
            ref = d[f"ref_{side}"]
            R, u = ref.get("ext", ref.get("R")), ref["u"]
            g_old = grade(d["amm_safe"][i], R, u, side)
            assert g_old == d[f"verdict_{side}"], (case, side, g_old, d[f"verdict_{side}"])  # replication check
            s_new = conv["safe_interval"][i]
            margin = None if s_new is None else ((s_new - R) if side == "lo" else (R - s_new)) / (2 * u)
            width = d["ref_hi"].get("ext", d["ref_hi"].get("R")) - d["ref_lo"].get("ext", d["ref_lo"].get("R"))
            inside = None if s_new is None else ((s_new - R) if side == "lo" else (R - s_new)) / width
            grades.append(dict(case=case, side=side, before=g_old, after=grade(s_new, R, u, side), safe=s_new,
                               R=R, u=u, margin_2u=margin, inside_frac_of_ref_gap=inside, branch=br[i]))
    # Fig. 4b,c rows: the finite-cell (V1b) gap cells and the DOLFINx (V1c) cells, re-judged
    fig = []
    for cid, cc in v1b.items():
        gp = cc.get("gap")
        if not gp:
            continue
        conv, br = judge(gp["amm_edges"], gp["amm_phase_edges"], gp["claim"])
        st_old = (gp["lo_status"], gp["hi_status"])
        ref = (gp["ref_lo"]["R"], gp["ref_hi"]["R"])
        u = (gp["ref_lo"]["u"], gp["ref_hi"]["u"])
        for i, side in enumerate(("lo", "hi")):
            assert grade(gp["safe_interval"][i], ref[i], u[i], side) == st_old[i], (cid, side)
        spec = specs[cid][0] if cid in specs else dict(family="resonator", kind="sphere_ligaments",
                                                        params=dict(c=0.357, w=0.109))  # id thin_sl_c0.357_w0.109
        feat = certify.feature_check(spec, max(int(n) for n in gp["amm_edges"]))
        fig.append(dict(case=cid, src="V1b", claim=gp["claim"], ref=ref, u=u, safe=conv["safe_interval"],
                        status=[grade(conv["safe_interval"][i], ref[i], u[i], s) for i, s in enumerate(("lo", "hi"))],
                        status_before=list(st_old), branches=br, feature=feat,
                        certified=bool(conv["passed"] and feat["passed"])))
    for case, (spec, d) in specs.items():
        conv, br = judge(d["amm_edges"], d["amm_phase_edges"], d["claim"])
        ref = tuple(d[f"ref_{s}"].get("ext", d[f"ref_{s}"].get("R")) for s in ("lo", "hi"))
        u = tuple(d[f"ref_{s}"]["u"] for s in ("lo", "hi"))
        feat = certify.feature_check(spec, max(int(n) for n in d["amm_edges"]))
        fig.append(dict(case=case, src="V1c", claim=d["claim"], ref=ref, u=u, safe=conv["safe_interval"],
                        status=[grade(conv["safe_interval"][i], ref[i], u[i], s) for i, s in enumerate(("lo", "hi"))],
                        status_before=[d["verdict_lo"], d["verdict_hi"]], branches=br, feature=feat,
                        certified=bool(conv["passed"] and feat["passed"])))
    return rows, grades, fig


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    b = bench()
    assert set(b["drift_rule_alone_changes"]) <= {x["cert"] for x in b["changed"]}
    w, wrows = witnesses()
    e = engineering()
    rc = rechecks()
    g, grades, fig = gaps()
    dump(OUT / "witnesses.json", dict(summary=w, rows=wrows))
    dump(OUT / "engineering.json", e)
    dump(OUT / "rechecks.json", rc)
    dump(OUT / "gaps.json", dict(gaps=g, dolfinx_edge_grades=grades, figure_rows=fig))
    ins = [x["inside_frac_of_ref_gap"] for x in grades if x["inside_frac_of_ref_gap"] is not None]
    summary = dict(
        rules=dict(drift_toward_claim="fails closed unless the order fit holds",
                   feature_min_voxels=certify.FEATURE_MIN_VOXELS, checker=certify.checker_hash()),
        benchmark={k: v for k, v in b.items() if k != "changed"}, benchmark_changed=b["changed"],
        witnesses=w,
        engineering=[{k: x[k] for k in ("file", "kind", "params", "before", "after", "reason")} for x in e],
        rechecks=[{k: x[k] for k in ("file", "before", "after")} for x in rc],
        gaps=dict(n=len(g), certified_after=sum(x["certified"] for x in g),
                  not_certified=[(x["case"], x["reason"]) for x in g if not x["certified"]],
                  guard_changed=[x["case"] for x in g if not x["guard_passed"]],
                  feature_failed=[x["case"] for x in g if not x["feature"]["passed"]]),
        dolfinx_edges=dict(before=dict(collections.Counter(x["before"] for x in grades)),
                           after=dict(collections.Counter(x["after"] for x in grades)),
                           inside_frac_range=[min(ins), max(ins)] if ins else None,
                           no_safe_edge=[(x["case"], x["side"]) for x in grades if x["safe"] is None]),
        figure_edges=dict(before=dict(collections.Counter(s for r in fig for s in r["status_before"])),
                          after=dict(collections.Counter(s for r in fig for s in r["status"])),
                          rows_certified_after=sum(r["certified"] for r in fig), rows=len(fig)))
    dump(OUT / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("benchmark_changed",)}, indent=1, default=str))


if __name__ == "__main__":
    main()

