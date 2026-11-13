"""V4 tables: throughput.csv, latency.csv, cert_times.csv (+ cert_times_summary.csv), scaling.csv, workflow.csv,
T6_v4.csv, from the raw files of throughput.py, latency.py, scaling.py and reuse.py. No computation of physics.

    python scripts/verify/v4/tables.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

O, RAW = common.OUT, common.RAW


def q(v, p):
    return float(np.percentile(v, p)) if len(v) else None


def r3(x, d=3):
    return None if x is None else round(float(x), d)


def stats(v, d=2):
    v = [float(x) for x in v if x not in (None, "")]
    if not v:
        return dict(n=0)
    return dict(n=len(v), median=r3(np.median(v), d), p25=r3(q(v, 25), d), p75=r3(q(v, 75), d), min=r3(min(v), d),
                max=r3(max(v), d), mean=r3(np.mean(v), d))


def read_csv(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(x):
    return None if x in (None, "", "None") else float(x)


# ---------------------------------------------------------------------------------------------------- throughput
def throughput():
    rows = []
    for r in common.read_jsonl(RAW / "throughput.jsonl"):
        c = r["calls"]
        warm = [x for x in c if x["phase"] == "warm"]
        same = [x for x in c if x["phase"] == "warm_same_as_cold"]
        cps = [x["cells_per_s"] for x in warm]
        B = r["batch"]
        rows.append(dict(
            family=r["family"], kind=r["kind"], batch=B, mkl_threads=int(r["env"]["MKL_NUM_THREADS"]),
            omp_threads=int(r["env"]["OMP_NUM_THREADS"]), static_workers=4, import_s=r["import_s"],
            cold_wall_s=c[0]["wall_s"], cold_cells_per_s=c[0]["cells_per_s"],
            warm_calls=len(warm), warm_cells_per_s_median=r3(np.median(cps), 4), warm_cells_per_s_min=min(cps),
            warm_cells_per_s_max=max(cps), warm_s_per_cell_median=r3(1.0 / np.median(cps), 4),
            warm_same_specs_cells_per_s=same[0]["cells_per_s"] if same else None,
            cold_over_same_spec_warm=r3(c[0]["wall_s"] / same[0]["wall_s"], 3) if same else None,
            warm_static_s_per_cell=r3(np.median([x["sum_static_s"] / B for x in warm]), 4),
            warm_bloch_s_per_cell=r3(np.median([x["sum_bloch_s"] / B for x in warm]), 4),
            valid_fraction=r3(sum(x["n_valid"] for x in c) / (B * len(c)), 3),
            gpu_peak_alloc_mb=max(x["gpu_peak_alloc_mb"] for x in c),
            gpu_peak_reserved_mb=max(x["gpu_peak_reserved_mb"] for x in c),
            process_peak_wset_mb=max(x["peak_wset_mb"] for x in c),
            cells_total=B * len(c)))
    rows.sort(key=lambda r: (r["mkl_threads"] != 16, r["family"], r["batch"]))
    common.write_csv(O / "throughput.csv", rows)
    return rows


# ---------------------------------------------------------------------------------------------------- latency
def latency():
    calls = common.read_jsonl(RAW / "latency_calls.jsonl")
    common.write_csv(RAW / "latency_calls.csv", [{k: v for k, v in c.items() if k != "env"} for c in calls])
    groups = defaultdict(list)
    for c in calls:
        if c["tool"] == "Session()":
            continue
        key = c["tool"] + (f" ({c['n_designs']} design{'s' if c['n_designs'] > 1 else ''})"
                           if c["tool"] == "evaluate" else "")
        groups[key].append(c)
    order = ["set_material", "set_constraints", "set_target", "check_bounds", "atlas_suggest", "evaluate (1 design)",
             "evaluate (16 designs)", "screen_manufacturing", "export", "search", "certify"]
    notes = {"set_material": "first call loads the nu = 0.39 atlas; later calls switch material (atlas cached or "
                             "loaded for a new nu)",
             "check_bounds": "M05 spec (PA12, combined target); bounds + atlas oracle",
             "atlas_suggest": "atlas lookup, top 5, M05 spec",
             "evaluate (1 design)": "6 different designs over 3 families; call 1 includes first CUDA use",
             "evaluate (16 designs)": "same 16 designs (gyroid, bcc, cube_bars) each call",
             "screen_manufacturing": "6 designs, defaults (tiles 3, resolution 64)",
             "export": "6 designs, defaults (tiles 3, resolution 64, tile_resolution 32); writes STL + report",
             "search": "default budget 32; one call per V3 target M13, S14, G06, S11, G07, S20 (one each)",
             "certify": "tool defaults incl. as-built flag; V3 repeats S20 (static), G15 (gap), M05 (combined)"}
    rows = []
    for k in order:
        g = groups.get(k, [])
        if not g:
            continue
        w = [c["wall_s"] for c in g]
        warm = [c["wall_s"] for c in g if c["label"] == "warm"]
        st, sw = stats(w, 3), stats(warm, 3)
        rows.append(dict(tool=k, source="V4 fresh (Session.call, actor agent)", n_calls=len(g),
                         cold_s=r3(g[0]["wall_s"], 3), median_s=st["median"], min_s=st["min"], max_s=st["max"],
                         warm_median_s=sw.get("median"), warm_min_s=sw.get("min"), warm_max_s=sw.get("max"),
                         all_ok=all(c["ok"] for c in g), notes=notes.get(k, ""),
                         per_call_s=" ".join(f"{x:.3g}" for x in w)))
    # reused: E4 agent sessions (tool dt_s logged inside Session.call)
    e4 = read_csv(RAW / "e4_tool_calls.csv")
    eg = defaultdict(list)
    for r in e4:
        if r["ok"] != "True":
            continue
        k = r["tool"]
        if k == "evaluate":
            n = int(fnum(r["n_designs"]) or 0)
            k = "evaluate (1 design)" if n == 1 else ("evaluate (16 designs)" if n == 16 else "evaluate (2-15 designs)")
        eg[k].append(float(r["dt_s"]))
        if r["tool"] == "search":
            eg[f"search (budget {int(fnum(r['budget']))})"].append(float(r["dt_s"]))
    for k in sorted(eg, key=lambda k: (order.index(k) if k in order else 99, k)):
        st = stats(eg[k], 3)
        rows.append(dict(tool=k, source="E4 agent sessions (reused; logged dt_s; code 90f3823f15cbeff4)",
                         n_calls=st["n"], median_s=st["median"], min_s=st["min"], max_s=st["max"],
                         p25_s=st["p25"], p75_s=st["p75"], notes="234 sessions, Codex agent, profiles B and C; "
                         "successful calls only"))
    # reused: V3 M4 search (library call, budget 48)
    wf = read_csv(RAW / "workflow_rows.csv")
    s4 = [float(r["search_s"]) for r in wf if r["method"] == "M4"]
    st = stats(s4, 3)
    rows.append(dict(tool="search (library, budget 48)", source="V3 M4 runs (reused)", n_calls=st["n"],
                     median_s=st["median"], min_s=st["min"], max_s=st["max"], p25_s=st["p25"], p75_s=st["p75"],
                     notes="amm.search.search, budget 48, 24 targets, MKL 4 threads + 4 static workers"))
    common.write_csv(O / "latency.csv", rows, ["tool", "source", "n_calls", "cold_s", "median_s", "min_s", "max_s",
                                               "p25_s", "p75_s", "warm_median_s", "warm_min_s", "warm_max_s",
                                               "all_ok", "per_call_s", "notes"])
    return rows, calls


# ---------------------------------------------------------------------------------------------------- certificates
def cert_times():
    rows = read_csv(RAW / "cert_times_rows.csv")
    common.write_csv(O / "cert_times.csv", rows)
    out = []

    def add(label, sel, **kw):
        if not sel:
            return
        d = dict(group=label, **kw)
        for col in ("total_s", "static_s", "bloch_s", "as_built_s"):
            st = stats([fnum(r[col]) for r in sel], 1)
            for k in ("n", "median", "p25", "p75", "min", "max"):
                d[f"{col}_{k}"] = st.get(k)
        d["n_certified"] = sum(r["verdict"] == "certified" for r in sel)
        d["checker"] = ";".join(sorted({r["checker"] for r in sel}))
        out.append(d)

    for src in ("V3", "V1b", "E4", "V4 fresh"):
        s = [r for r in rows if r["source"] == src]
        add(f"{src} all", s, source=src)
        for fam in ("tpms", "struts", "resonator"):
            add(f"{src} {fam}", [r for r in s if r["family"] == fam], source=src, family=fam)
        for tt in ("static", "gap", "combined"):
            add(f"{src} {tt}", [r for r in s if r["target_type"] == tt], source=src, target_type=tt)
        for v in ("certified", "undetermined", "refuted"):
            add(f"{src} {v}", [r for r in s if r["verdict"] == v], source=src, verdict=v)
    common.write_csv(O / "cert_times_summary.csv", out)
    return rows, out


# ---------------------------------------------------------------------------------------------------- workflow
def workflow():
    rows = read_csv(RAW / "workflow_rows.csv")
    out = []
    names = {"M1": "atlas-only", "M2": "Sobol", "M3": "differential evolution", "M4": "BO full (amm search)",
             "M5": "BO without atlas seeding", "M6": "BO without error correction"}
    for sset in ("primary", "calibration"):
        for m in ("M1", "M2", "M3", "M4", "M5", "M6"):
            s = [r for r in rows if r["method"] == m and r["set"] == sset]
            if not s:
                continue
            ok = [r for r in s if r["certified"] == "True"]
            wf, se, ce = ([float(r[c]) for r in s] for c in ("workflow_s", "search_s", "cert_s"))
            st, sok = stats(wf, 1), stats([float(r["workflow_s"]) for r in ok], 1)
            out.append(dict(set=sset, method=m, method_name=names[m], n_targets=len(s), n_certified=len(ok),
                            cert_calls=sum(int(r["cert_calls"]) for r in s),
                            search_s_median=stats(se, 1).get("median"), cert_s_median=stats(ce, 1).get("median"),
                            workflow_s_median=st["median"], workflow_s_p25=st["p25"], workflow_s_p75=st["p75"],
                            workflow_s_min=st["min"], workflow_s_max=st["max"],
                            workflow_s_median_certified=sok.get("median"), workflow_s_min_certified=sok.get("min"),
                            workflow_s_max_certified=sok.get("max"),
                            workflow_total_h=r3(sum(wf) / 3600, 3),
                            workflow_s_per_certified_design=r3(sum(wf) / len(ok), 1) if ok else None))
    common.write_csv(O / "workflow.csv", out)
    return out


# ---------------------------------------------------------------------------------------------------- scaling
def scaling():
    out = []
    for r in common.read_jsonl(RAW / "scaling.jsonl"):
        if r["kind"] == "probe":
            continue
        th = int(r["env"]["MKL_NUM_THREADS"])
        d = dict(path=r["kind"], n=r["n"], mkl_threads=th, ndof=r["ndof"], density=r.get("density"),
                 t_geometry_s=r.get("t_geometry_s"), t_mesh_s=r.get("t_mesh_s"))
        if r["kind"] == "static":
            d.update(device="CPU (PARDISO mtype 2)", t_solve_s=min(r["t_homogenize_s"]),
                     t_solve_reps_s=" ".join(map(str, r["t_homogenize_s"])), t_assemble_s=r["t_assemble_s"],
                     t_factor_s=r["t_factor_s"], t_solve6_s=r["t_solve6_s"], nnz=r["nnz"],
                     solve_definition="homog.homogenize (assembly, factorization, 6 load cases, C*)",
                     peak_wset_mb=r["mem_after"]["peak_wset_mb"],
                     mem_before_solve_mb=r["mem_before_solve"]["rss_mb"],
                     pardiso_iparm15_kb=r["pardiso"]["iparm15"], pardiso_iparm16_kb=r["pardiso"]["iparm16"],
                     pardiso_iparm17_kb=r["pardiso"]["iparm17"], pardiso_iparm18=r["pardiso"]["iparm18"])
        elif r["kind"] == "bloch_cpu":
            d.update(device="CPU (PARDISO mtype -2, real 2N form)", t_solve_s=r["t_count_per_factor_s"],
                     t_count_first_s=r["t_count_first_s"], t_edge_lanczos_s=r["t_edge_lanczos_s"],
                     solve_definition="one inertia count (LDL^T factorization at one shift, pattern reused)",
                     peak_wset_mb=r["mem_after"]["peak_wset_mb"], mem_before_solve_mb=r["mem_before"]["rss_mb"],
                     pardiso_iparm15_kb=r["pardiso"]["iparm15"], pardiso_iparm16_kb=r["pardiso"]["iparm16"],
                     pardiso_iparm17_kb=r["pardiso"]["iparm17"], pardiso_iparm18=r["pardiso"]["iparm18"])
        else:
            d.update(device="GPU (dense complex64)", dense_per_k_gb=r.get("dense_per_k_gb"),
                     solve_definition="bands at one k-point (dense assembly, Cholesky, eigvalsh)")
            if "skipped" in r:
                d.update(skipped=r["skipped"])
            else:
                d.update(t_solve_s=min(r["t_1k_s"][1:]), t_1k_cold_s=r["t_1k_s"][0],
                         t_solve_reps_s=" ".join(map(str, r["t_1k_s"])), t_setup_s=r["t_setup_s"],
                         t_path21_s=r.get("t_path21_s"), gpu_peak_alloc_mb=r["gpu_peak_alloc_mb"],
                         peak_wset_mb=r["mem_after"]["peak_wset_mb"])
        out.append(d)
    out.sort(key=lambda d: (d["path"], d["mkl_threads"] != 16, d["n"], d["mkl_threads"]))
    common.write_csv(O / "scaling.csv", out, ["path", "device", "n", "mkl_threads", "ndof", "nnz", "density",
                                              "t_geometry_s", "t_mesh_s", "t_solve_s", "solve_definition",
                                              "t_solve_reps_s", "t_assemble_s", "t_factor_s", "t_solve6_s",
                                              "t_count_first_s", "t_edge_lanczos_s", "t_setup_s", "t_1k_cold_s",
                                              "t_path21_s", "peak_wset_mb", "mem_before_solve_mb",
                                              "gpu_peak_alloc_mb", "dense_per_k_gb", "pardiso_iparm15_kb",
                                              "pardiso_iparm16_kb", "pardiso_iparm17_kb", "pardiso_iparm18",
                                              "skipped"])
    return out


# ---------------------------------------------------------------------------------------------------- T6
def t6(tp, lat, certsum, wf, sc):
    rows = []

    def add(block, metric, value, unit, conditions, source):
        rows.append(dict(block=block, metric=metric, value=value, unit=unit, conditions=conditions, source=source))

    for r in tp:
        if r["mkl_threads"] == 16 and r["batch"] in (1, 16, 64):
            add("throughput", f"search tier, {r['kind']}, batch {r['batch']}",
                f"{r['warm_cells_per_s_median']} (cold {r['cold_cells_per_s']})", "cells/s",
                "warm median; static n=20 CPU 4 workers, Bloch n=10 GPU, MKL/OMP 16", "throughput.csv")
    for r in tp:
        if r["mkl_threads"] == 4:
            add("throughput", f"search tier, {r['kind']}, batch 16, 4 MKL threads",
                f"{r['warm_cells_per_s_median']}", "cells/s", "V3 search-process setting", "throughput.csv")
    for r in lat:
        if r["source"].startswith("V4"):
            add("latency", r["tool"], f"{r['median_s']} [{r['min_s']}, {r['max_s']}]", "s",
                f"median [range], n = {r['n_calls']}; cold first call {r['cold_s']} s", "latency.csv")
    for r in lat:
        if r["source"].startswith("E4") and r["tool"] in ("search", "search (budget 32)", "certify", "evaluate (1 design)",
                                                           "evaluate (16 designs)", "check_bounds", "atlas_suggest"):
            add("latency (agent sessions)", r["tool"], f"{r['median_s']} [{r['min_s']}, {r['max_s']}]", "s",
                f"median [range], n = {r['n_calls']}, E4 sessions", "latency.csv")
    for r in certsum:
        if r["group"] in ("V3 all", "V3 static", "V3 gap", "V3 combined", "V1b all", "E4 all", "V4 fresh all"):
            add("certificate", f"total, {r['group']}",
                f"{r['total_s_median']} [{r['total_s_min']}, {r['total_s_max']}]", "s",
                f"median [range], n = {r['total_s_n']}; static median {r['static_s_median']}, Bloch median "
                f"{r['bloch_s_median']}, as-built median {r['as_built_s_median']}; checker {r['checker']}",
                "cert_times_summary.csv")
    for r in wf:
        if r["set"] == "primary":
            add("workflow", f"spec to certified design, {r['method_name']}",
                f"{r['workflow_s_median_certified']} [{r['workflow_s_min_certified']}, "
                f"{r['workflow_s_max_certified']}]", "s",
                f"certified successes {r['n_certified']}/{r['n_targets']}; median over all targets "
                f"{r['workflow_s_median']} s; {r['workflow_s_per_certified_design']} s per certified design",
                "workflow.csv")
    for r in sc:
        if r["mkl_threads"] == 16 and r.get("t_solve_s") is not None:
            mem = r.get("gpu_peak_alloc_mb") if r["path"] == "bloch_gpu" else r.get("peak_wset_mb")
            add("scaling", f"{r['path']} n={r['n']} (ndof {r['ndof']})", r["t_solve_s"], "s",
                f"{r['solve_definition']}; peak memory {mem} MB "
                f"({'GPU allocated' if r['path'] == 'bloch_gpu' else 'process working set'})", "scaling.csv")
    for r in sc:
        if r["path"] in ("static", "bloch_cpu") and r["n"] in (48, 30) and r.get("t_solve_s") is not None:
            add("threads", f"{r['path']} n={r['n']}, {r['mkl_threads']} MKL threads", r["t_solve_s"], "s",
                r["solve_definition"], "scaling.csv")
    common.write_csv(O / "T6_v4.csv", rows)
    return rows


def main():
    tp = throughput()
    lat, _ = latency()
    _, cs = cert_times()
    wf = workflow()
    sc = scaling()
    t6(tp, lat, cs, wf, sc)
    print("tables written")


if __name__ == "__main__":
    main()
