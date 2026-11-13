"""V1b comparison: amm certificates vs the independent Q2-FCM and scikit-fem results, two-sided, by the rules of
results/verification/v1b/NOTES.md section 0 (fixed before the comparison).

    compare.py   -> results/verification/v1b/compare_<id>.json, summary.json, T4_v1b.csv
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v1b"
STATIC_Q = ("E100", "G", "bulk", "density", "nu100")
STATIC_KEYS = {"density_max": ("density", "max"), "density_min": ("density", "min"), "E100_min": ("E100", "min"),
               "E100_max": ("E100", "max"), "G_min": ("G", "min"), "bulk_min": ("bulk", "min"),
               "nu100_min": ("nu100", "min"), "nu100_max": ("nu100", "max")}


def ref3(ns, vals, floor_rel=2e-4):
    """Reference value and uncertainty from three levels (NOTES 0.4)."""
    order = np.argsort(ns)
    ns, E = np.asarray(ns, float)[order], np.asarray(vals, float)[order]
    h = 1 / ns
    d12, d23 = E[1] - E[0], E[2] - E[1]
    floor = floor_rel * max(abs(E[2]), 1e-12)
    if d12 != 0 and d23 != 0 and d12 * d23 > 0 and abs(d23) < abs(d12):
        g = lambda p: (h[1] ** p - h[2] ** p) / (h[0] ** p - h[1] ** p) - d23 / d12
        try:
            p = brentq(g, 0.05, 12.0)
        except ValueError:
            p = 0.5 if g(0.5) < 0 else 4.0
        pc = float(np.clip(p, 0.5, 4.0))
        r = h[2] ** pc / (h[1] ** pc - h[2] ** pc)
        return dict(R=float(E[2] + d23 * r), u=float(max(abs(d23) * r, floor)), mode="order-fit", p=float(p),
                    p_used=pc, levels=ns.astype(int).tolist(), values=E.tolist())
    return dict(R=float(E[2]), u=float(max(abs(d12), abs(d23), floor)), mode="non-monotone", p=None,
                levels=ns.astype(int).tolist(), values=E.tolist())


def lower_status(B, R, u):
    return "sound" if B <= R - 2 * u else ("unsound" if B > R + 2 * u else "marginal")


def upper_status(B, R, u):
    return "sound" if B >= R + 2 * u else ("unsound" if B < R - 2 * u else "marginal")


def claim_min(t, R, u):
    return "agrees" if R - 2 * u >= t else ("disagrees" if R + 2 * u < t else "inconclusive")


def claim_max(t, R, u):
    return "agrees" if R + 2 * u <= t else ("disagrees" if R - 2 * u > t else "inconclusive")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def static_compare(cell, cert, marg):
    cid = cell["id"]
    q2 = {int(f.stem.split("_n")[-1]): load(f) for f in (OUT / "q2").glob(f"{cid}_static_n*.json")}
    sk = {int(f.stem.split("_n")[-1]): load(f) for f in (OUT / "skfem").glob(f"{cid}_n*.json")}
    ns_all = sorted(q2)
    ns = ns_all[-3:]
    conv = cert["blocks"]["static"]["convergence"]["quantities"]
    used = cert["blocks"]["static"]["used"]
    rows = {}
    for q in STATIC_Q + ("C11", "C12"):
        ref = ref3(ns, [q2[n][q] for n in ns])
        R, u = ref["R"], ref["u"]
        scale = 1.0 if q == "nu100" else abs(R)
        e = dict(quantity=q, ref=ref, q2_levels={n: q2[n][q] for n in ns_all})
        if len(ns_all) >= 4:  # the reference one level coarser (sensitivity; NOTES deviation 4)
            ra = ref3(ns_all[-4:-1], [q2[n][q] for n in ns_all[-4:-1]])
            e["ref_prev"] = ra
            if q in conv:
                e["lower_status_prev"] = lower_status(conv[q]["lower"], ra["R"], ra["u"])
                e["delta_prev"] = (conv[q]["extrapolated"] - ra["R"]) / (1.0 if q == "nu100" else abs(ra["R"]))
        if q in conv:
            b = conv[q]
            e.update(amm_ext=b["extrapolated"], amm_remaining=b["remaining"], amm_lower=b["lower"],
                     amm_upper=b["upper"], amm_converged=b["converged"], amm_means=b["means"])
            e["delta"] = (b["extrapolated"] - R) / scale
            e["lower_status"] = lower_status(b["lower"], R, u)
            e["upper_status"] = upper_status(b["upper"], R, u)
            e["conservatism_lower"] = (R - b["lower"]) / scale
            e["conservatism_upper"] = (b["upper"] - R) / scale
            ea = b["remaining"] if b["remaining"] is not None else abs(b["means"][-1] - b["means"][-2])
            e["consistent"] = bool(abs(b["extrapolated"] - R) <= 2 * np.hypot(u, ea))
        else:  # C11, C12: amm records them per solve, not in the guard: phase mean at the finest rung resolution
            n3 = used[-1]
            vals = [cert["blocks"]["static"]["resolutions"][str(n3)][q]] + [
                v[q] for k, v in cert["blocks"]["static"]["phase_rows"].items() if k.startswith(f"{n3}@")]
            e.update(amm_finest_phase_mean=float(np.mean(vals)), amm_finest_n=n3)
            e["delta_finest"] = (float(np.mean(vals)) - R) / scale
        if sk and q in ("E100", "G", "bulk", "C11", "C12", "nu100"):
            sn = sorted(sk)
            e["skfem_periodic"] = {n: sk[n]["periodic"][q] for n in sn}
            e["skfem_kubc"] = {n: sk[n]["kubc"][q] for n in sn}
            hi, lo = sk[sn[-1]]["periodic"][q], sk[sn[0]]["periodic"][q]
            e["skfem_delta"] = (hi - R) / scale
            e["skfem_agrees"] = bool(abs(hi - R) <= 2 * u + 2 * abs(hi - lo))
            if q in ("E100", "G", "bulk"):
                kb = sk[sn[-1]]["kubc"][q]
                e["kubc_ge_periodic"] = bool(kb >= hi * (1 - 1e-9))
                if "amm_lower" in e:
                    e["kubc_ge_amm_lower"] = bool(kb >= e["amm_lower"])
        rows[q] = e
    claims = []
    for label, targets in (("nominal", cell["targets"]),) + ((("marginal", marg["targets"]),) if marg else ()):
        for key, t in targets.items():
            if key not in STATIC_KEYS:
                continue
            q, kind = STATIC_KEYS[key]
            R, u = rows[q]["ref"]["R"], rows[q]["ref"]["u"]
            claims.append(dict(claim=label, key=key, target=t, ref=R, u=u,
                               status=(claim_min if kind == "min" else claim_max)(t, R, u),
                               amm_bound=rows[q]["amm_lower"] if kind == "min" else rows[q]["amm_upper"],
                               margin_rel=((rows[q]["amm_lower"] - t) if kind == "min" else (t - rows[q]["amm_upper"]))
                               / max(abs(t), 1e-12)))
    return dict(levels=ns, skfem_levels=sorted(sk), quantities=rows, claims=claims,
                q2_density_fine256=q2[ns[0]].get("density_fine256"))


def edges_of(rows, keys=None):
    lo = [r["lo"] for r in rows if r["lo"] is not None and (keys is None or (r["set"], r["i"]) in keys)]
    hi = [r["hi"] for r in rows if r["hi"] is not None and (keys is None or (r["set"], r["i"]) in keys)]
    return (max(lo) if lo else None), (min(hi) if hi else None)


def gap_compare(cell, cert, marg, ammk):
    cid = cell["id"]
    qb = load(OUT / "q2" / f"{cid}_bloch.json")
    g = cert["blocks"]["bloch"]
    cv = g.get("convergence") or {}
    s_lo, s_hi = cv.get("safe_interval") or (None, None)
    nb = qb["below_band"]
    lv = [str(n) for n in qb["levels"]]
    sub = {(r["set"], r["i"]) for r in qb["levels_data"][lv[-1]]["rows"]}
    per_level = {n: edges_of(qb["levels_data"][n]["rows"], sub) for n in lv}
    ref_lo = ref3([int(n) for n in lv], [per_level[n][0] for n in lv])
    ref_hi = ref3([int(n) for n in lv], [per_level[n][1] for n in lv])
    prev = None
    xf = OUT / "q2" / f"{cid}_bloch_extra.json"
    if xf.exists():  # deviation 6: extra levels on the same k subset; the reference uses the three finest levels
        qx = load(xf)
        for n in qx["levels_data"]:
            per_level[n] = edges_of(qx["levels_data"][n]["rows"], sub)
        allv = sorted(per_level, key=int)
        if len(allv) > 3:
            prev = dict(levels=[int(n) for n in lv], ref_lo=ref_lo, ref_hi=ref_hi)
            fin3 = allv[-3:]
            ref_lo = ref3([int(n) for n in fin3], [per_level[n][0] for n in fin3])
            ref_hi = ref3([int(n) for n in fin3], [per_level[n][1] for n in fin3])
    out = dict(below_band=nb, claim=qb["claim"], safe_interval=[s_lo, s_hi], q2_edges=per_level,
               ref_lo=ref_lo, ref_hi=ref_hi, amm_edges=cv.get("edges"), amm_phase_edges=cv.get("phase_edges"))
    if prev and s_lo is not None:
        a, b = prev["ref_lo"], prev["ref_hi"]
        prev["lo_status"] = "sound" if s_lo >= a["R"] + 2 * a["u"] else ("unsound" if s_lo < a["R"] - 2 * a["u"] else "marginal")
        prev["hi_status"] = "sound" if s_hi <= b["R"] - 2 * b["u"] else ("unsound" if s_hi > b["R"] + 2 * b["u"] else "marginal")
        out["ref_prev"] = prev
    le, ue = cv.get("lower_edge") or {}, cv.get("upper_edge") or {}
    out["amm_ext"] = [le.get("extrapolated"), ue.get("extrapolated")]
    out["amm_remaining"] = [le.get("remaining"), ue.get("remaining")]
    R1, u1, R2, u2 = ref_lo["R"], ref_lo["u"], ref_hi["R"], ref_hi["u"]
    if s_lo is not None:
        out["lo_status"] = "sound" if s_lo >= R1 + 2 * u1 else ("unsound" if s_lo < R1 - 2 * u1 else "marginal")
        out["hi_status"] = "sound" if s_hi <= R2 - 2 * u2 else ("unsound" if s_hi > R2 + 2 * u2 else "marginal")
        out["conservatism"] = [(s_lo - R1) / R1, (R2 - s_hi) / R2]
        out["uncertified_fraction_of_ref_gap"] = 1 - (s_hi - s_lo) / (R2 - R1)
    if le.get("extrapolated") is not None:
        out["delta_ext"] = [(le["extrapolated"] - R1) / R1, (ue["extrapolated"] - R2) / R2]
        out["consistent_ext"] = [bool(abs(le["extrapolated"] - R1) <= 2 * np.hypot(u1, le.get("remaining") or 0)),
                                 bool(abs(ue["extrapolated"] - R2) <= 2 * np.hypot(u2, ue.get("remaining") or 0))]
    # claims
    claims = []
    for label, tg in (("nominal", cell["targets"].get("gap")),) + ((("marginal", marg["targets"].get("gap")),)
                                                                    if marg else ()):
        if not tg:
            continue
        f_lo, f_hi = tg["f_lo"], tg["f_hi"]
        st = ("agrees" if (f_lo >= R1 + 2 * u1 and f_hi <= R2 - 2 * u2) else
              "disagrees" if (f_lo < R1 - 2 * u1 or f_hi > R2 + 2 * u2) else "inconclusive")
        claims.append(dict(claim=label, f_lo=f_lo, f_hi=f_hi, status=st,
                           margin_to_ref=[(f_lo - R1) / R1, (R2 - f_hi) / R2],
                           margin_to_safe=None if s_lo is None else [(f_lo - s_lo) / s_lo, (s_hi - f_hi) / s_hi]))
    out["claims"] = claims
    # k coverage at level 1
    rows1 = qb["levels_data"][lv[0]]["rows"]
    amm_sets = {"amm_path", "amm_interior", "amm_adversarial"}
    lo_a, hi_a = edges_of([r for r in rows1 if r["set"] in amm_sets])
    lo_all, hi_all = edges_of(rows1)
    arg_lo = max((r for r in rows1 if r["lo"] is not None), key=lambda r: r["lo"])
    arg_hi = min((r for r in rows1 if r["hi"] is not None), key=lambda r: r["hi"])
    out["k_coverage"] = dict(level=int(lv[0]), lo_amm_set=lo_a, lo_all=lo_all, hi_amm_set=hi_a, hi_all=hi_all,
                             delta_lo=lo_all - lo_a, delta_hi=hi_a - hi_all,
                             k_lo=arg_lo["k"], set_lo=arg_lo["set"], k_hi=arg_hi["k"], set_hi=arg_hi["set"],
                             by_set={s: edges_of([r for r in rows1 if r["set"] == s]) for s in
                                     sorted({r["set"] for r in rows1})})
    # rule (iii): the refinement subset contains the 3 most extreme level-1 k of every set (own search and full
    # zone included), so the reference edges R_lo / R_hi already include any independent k beyond amm's sample;
    # record which set holds the extreme k at the finest level
    fin = qb["levels_data"][lv[-1]]["rows"]
    out["extreme_k_finest"] = dict(lo=max((r for r in fin if r["lo"] is not None), key=lambda r: r["lo"])["set"],
                                   hi=min((r for r in fin if r["hi"] is not None), key=lambda r: r["hi"])["set"])
    out["search"] = qb.get("search")
    # band-index mismatches
    mism = []
    lvd = dict(qb["levels_data"], **(load(xf)["levels_data"] if xf.exists() else {}))
    for n in lvd:
        for r in lvd[n]["rows"]:
            if r["n_below"] != nb:
                mism.append(dict(n=int(n), set=r["set"], k=r["k"], n_below=r["n_below"]))
    out["band_index_mismatch"] = mism
    out["q2_numerics"] = dict(max_eig_res=max(r["eig_res"] for n in lv for r in qb["levels_data"][n]["rows"]
                                              if any(abs(x) > 1e-12 for x in r["k"])),  # Gamma: rigid modes

                              max_perturbed=max(r["n_perturbed"] for n in lv for r in qb["levels_data"][n]["rows"]),
                              any_odd=any(r["odd"] for n in lv for r in qb["levels_data"][n]["rows"]))
    # per-k two-sided discrepancies
    if ammk:
        A = {n: {(r["set"], r["i"]): r for r in ammk["levels"][n]["rows"]} for n in ammk["levels"]}
        perk = []
        for r in rows1:
            key = (r["set"], r["i"])
            a = A["20"].get(key)
            if not a:
                continue
            e = dict(set=r["set"], i=r["i"], k=r["k"], amm_n_below=a["n_below"], q2_n_below=r["n_below"])
            if a["n_below"] == nb and r["n_below"] == nb:
                e["d_lo_sampled"] = a["below_fc"] - r["lo"]
                e["d_hi_sampled"] = a["above_fc"] - r["hi"]
            perk.append(e)
        out["per_k_sampled"] = dict(amm_n=20, q2_n=int(lv[0]), rows=perk)
        perx = []
        for key in sorted(sub):
            if not all(key in A[n] for n in ("20", "30", "40")):
                continue
            qa = [next(r for r in qb["levels_data"][n]["rows"] if (r["set"], r["i"]) == key) for n in lv]
            if any(x["n_below"] != nb for x in qa) or any(A[n][key]["n_below"] != nb for n in ("20", "30", "40")):
                perx.append(dict(set=key[0], i=key[1], skipped="band index differs"))
                continue
            e = dict(set=key[0], i=key[1], k=qa[0]["k"])
            for side, qk, ak in (("lo", "lo", "below_fc"), ("hi", "hi", "above_fc")):
                rq = ref3([int(n) for n in lv], [x[qk] for x in qa])
                ra = ref3([20, 30, 40], [A[n][key][ak] for n in ("20", "30", "40")])
                e[side] = dict(q2=rq, amm=ra, delta=(ra["R"] - rq["R"]) / rq["R"],
                               consistent=bool(abs(ra["R"] - rq["R"]) <= 2 * np.hypot(rq["u"], ra["u"])))
            perx.append(e)
        out["per_k_extrapolated"] = perx
    return out


def cluster_ids(f, rtol=1e-4):
    """Cluster index of each sorted eigenvalue (degenerate copies share one index)."""
    f = np.asarray(f)
    return np.concatenate([[0], np.cumsum(np.diff(f) > rtol * f[1:])]).astype(int)


def same_cluster(ids, j):
    """True if band j sits in clusters with the same membership (same first and last band index) at every level."""
    sig = [(int(np.flatnonzero(c == c[j])[0]), int(np.flatnonzero(c == c[j])[-1])) for c in ids]
    return all(x == sig[0] for x in sig)


def band_compare(cell, ammk):
    cid = cell["id"]
    qb = load(OUT / "q2" / f"{cid}_bloch.json")
    lv = [str(n) for n in qb["levels"]]
    sub = [(r["set"], r["i"]) for r in qb["levels_data"][lv[-1]]["rows"]]
    A = {n: {(r["set"], r["i"]): r for r in ammk["levels"][n]["rows"]} for n in ammk["levels"]} if ammk else None
    rows = []
    for key in sub:
        qa = [next(r for r in qb["levels_data"][n]["rows"] if (r["set"], r["i"]) == key) for n in lv]
        isG = all(abs(x) < 1e-12 for x in qa[0]["k"])
        have_a = bool(A and all(key in A[n] for n in ("20", "30", "40")))
        cq = [cluster_ids(x["f"]) for x in qa]
        ca = [cluster_ids(A[n][key]["f"]) for n in ("20", "30", "40")] if have_a else None
        for j in range(3 if isG else 0, qb["nev"]):
            rq = ref3([int(n) for n in lv], [x["f"][j] for x in qa])
            e = dict(set=key[0], i=key[1], k=qa[0]["k"], band=j + 1, q2=rq,
                     crossing_q2=not same_cluster(cq, j))
            if have_a:
                ra = ref3([20, 30, 40], [A[n][key]["f"][j] for n in ("20", "30", "40")])
                fa, fq = A["40"][key]["f"][j], qa[-1]["f"][j]
                e.update(amm=ra, delta=(ra["R"] - rq["R"]) / rq["R"],
                         consistent=bool(abs(ra["R"] - rq["R"]) <= 2 * np.hypot(rq["u"], ra["u"])),
                         crossing_amm=not same_cluster(ca, j), finest=dict(amm_n=40, q2_n=int(lv[-1]),
                                                                           rel=(fa - fq) / fq))
            rows.append(e)
    samp = []
    if A:
        for r in qb["levels_data"][lv[0]]["rows"]:
            a = A["20"].get((r["set"], r["i"]))
            if a:
                isG = all(abs(x) < 1e-12 for x in r["k"])
                samp.append(dict(set=r["set"], i=r["i"], k=r["k"],
                                 rel=[(a["f"][j] - r["f"][j]) / r["f"][j] for j in range(3 if isG else 0, qb["nev"])]))
    d = [abs(r["delta"]) for r in rows if "delta" in r]
    clean = [r for r in rows if "delta" in r and not (r["crossing_q2"] or r["crossing_amm"])]
    fin = [r["finest"]["rel"] for r in rows if "finest" in r]
    return dict(levels=qb["levels"], rows=rows, sampled=dict(amm_n=20, q2_n=int(lv[0]), rows=samp),
                max_abs_delta=max(d) if d else None, n_consistent=sum(r.get("consistent", False) for r in rows),
                n_rows=len(rows),
                # post hoc (deviation 5): rows whose band index changes cluster across the levels of either code
                # (mode crossing / degenerate ordering) are not extrapolable per index; reported separately
                n_crossing=len(d) - len(clean),
                max_abs_delta_no_crossing=max((abs(r["delta"]) for r in clean), default=None),
                n_consistent_no_crossing=sum(r["consistent"] for r in clean), n_rows_no_crossing=len(clean),
                finest_rel_range=[min(fin), max(fin)] if fin else None)


def main():
    cells = load(OUT / "cells.json")["cells"]
    mcl = load(OUT / "marginal_claims.json")["claims"] if (OUT / "marginal_claims.json").exists() else {}
    summary, csv_rows = {}, []
    for cell in cells:
        cid = cell["id"]
        if not (OUT / f"{cid}_amm.json").exists():
            continue
        cert = load(OUT / f"{cid}_amm.json")
        mc = load(OUT / f"{cid}_amm_marginal.json") if (OUT / f"{cid}_amm_marginal.json").exists() else None
        marg = dict(mcl[cid], amm_verdict=mc["verdict"] if mc else None,
                    amm_static=mc["blocks"]["static"]["verdict"] if mc else None,
                    amm_gap=(mc["blocks"].get("bloch") or {}).get("verdict") if mc else None) if cid in mcl else None
        res = dict(id=cid, family=cell["family"], amm_verdict=cert["verdict"], checker=cert["checker"],
                   amm_seconds=cert.get("seconds"), marginal=marg)
        if list((OUT / "q2").glob(f"{cid}_static_n*.json")):
            res["static"] = static_compare(cell, cert, marg)
        ammk = load(OUT / f"{cid}_amm_k.json") if (OUT / f"{cid}_amm_k.json").exists() else None
        if (OUT / "q2" / f"{cid}_bloch.json").exists():
            if "bloch" in cert["blocks"]:
                res["gap"] = gap_compare(cell, cert, marg, ammk)
            else:
                res["bands"] = band_compare(cell, ammk)
        (OUT / f"compare_{cid}.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
        summary[cid] = res
        # CSV rows (T4)
        st = res.get("static")
        if st:
            for q, e in st["quantities"].items():
                if "amm_ext" not in e:
                    continue
                csv_rows.append(dict(cell=cid, family=cell["family"], check=f"static:{q}", amm_estimate=e["amm_ext"],
                                     amm_lower=e["amm_lower"], amm_upper=e["amm_upper"], ref=e["ref"]["R"],
                                     ref_u=e["ref"]["u"], delta_rel=e["delta"], status_lower=e["lower_status"],
                                     status_upper=e["upper_status"], conservatism_lower=e["conservatism_lower"],
                                     conservatism_upper=e["conservatism_upper"], consistent=e["consistent"],
                                     skfem_delta=e.get("skfem_delta"), skfem_agrees=e.get("skfem_agrees"),
                                     kubc_ge_amm_lower=e.get("kubc_ge_amm_lower")))
            for c in st["claims"]:
                csv_rows.append(dict(cell=cid, family=cell["family"], check=f"claim:{c['claim']}:{c['key']}",
                                     amm_estimate=c["amm_bound"], ref=c["ref"], ref_u=c["u"], target=c["target"],
                                     claim_status=c["status"], margin_rel=c["margin_rel"]))
        gp = res.get("gap")
        if gp:
            for side, j, stt in (("lo", 0, gp.get("lo_status")), ("hi", 1, gp.get("hi_status"))):
                rr = gp["ref_" + side]
                csv_rows.append(dict(cell=cid, family=cell["family"], check=f"gap:{side}_edge",
                                     amm_estimate=gp["amm_ext"][j], amm_lower=gp["safe_interval"][j] if j == 0 else None,
                                     amm_upper=gp["safe_interval"][j] if j == 1 else None, ref=rr["R"], ref_u=rr["u"],
                                     delta_rel=(gp.get("delta_ext") or [None, None])[j],
                                     status_lower=stt if j == 0 else None, status_upper=stt if j == 1 else None,
                                     conservatism_lower=(gp.get("conservatism") or [None, None])[0] if j == 0 else None,
                                     conservatism_upper=(gp.get("conservatism") or [None, None])[1] if j == 1 else None,
                                     consistent=(gp.get("consistent_ext") or [None, None])[j],
                                     k_coverage_delta=gp["k_coverage"]["delta_" + side]))
            for c in gp["claims"]:
                csv_rows.append(dict(cell=cid, family=cell["family"], check=f"claim:{c['claim']}:gap",
                                     target=f"{c['f_lo']:.5f}-{c['f_hi']:.5f}", claim_status=c["status"],
                                     margin_rel=min(c["margin_to_safe"]) if c["margin_to_safe"] else None))
        bd = res.get("bands")
        if bd:
            csv_rows.append(dict(cell=cid, family=cell["family"], check="bands:4-15 at G,X,M,R+4 interior",
                                 delta_rel=bd["max_abs_delta"], consistent=f"{bd['n_consistent']}/{bd['n_rows']}"))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    keys = []
    for r in csv_rows:
        keys += [k for k in r if k not in keys]
    with open(OUT / "T4_v1b.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in csv_rows:
            w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})
    print("cells compared:", list(summary))


if __name__ == "__main__":
    main()
