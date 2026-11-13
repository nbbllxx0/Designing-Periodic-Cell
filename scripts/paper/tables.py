"""Tables T2, T3, T4, T5, T6, T8, T11, T13 (plan item A1) from result files and checker source text.

Run through `make_all.py` (which also writes the claims ledger). Each builder takes the shared Ledger and returns
the paths it wrote.
"""
from __future__ import annotations

import collections
import glob
import json
import re
import statistics as st
from pathlib import Path

from common import (ROOT, Ledger, find_line, fnum, function_defaults, g, module_constants, pct, read_csv,
                    read_json, read_jsonl, read_text, sha16, write_table)

S = "scripts/paper/tables.py"


# ============================================================================================================ T2
def t2_contract(L: Ledger):
    # the newest written contract (another work package may add a schema version; the table follows the newest)
    cands = sorted(glob.glob(str(ROOT / "results/software/contract_amm-tools-*.json")),
                   key=lambda p: int(re.search(r"amm-tools-(\d+)\.json$", p).group(1)))
    src = "results/software/" + Path(cands[-1]).name
    c = read_json(src)
    L.add("T2", "contract_versions_present", ", ".join(Path(p).stem.replace("contract_", "") for p in cands),
          "results/software/contract_amm-tools-*.json", "files present; the newest is tabulated", status="derived",
          script=S)
    tools = c["tools"]
    groups = [("Specification", ["set_material", "set_constraints", "set_target", "set_source", "undo", "get_session",
                                 "ask_clarification"]),
              ("Exploration (search tier, not certified)", ["list_families", "atlas_suggest", "evaluate", "search"]),
              ("Verification", ["check_bounds", "certify", "as_built"]),
              ("Output", ["screen_manufacturing", "export", "submit"])]
    listed = {t for _, ts in groups for t in ts}
    rest = [t for t in tools if t not in listed]
    if rest:
        groups.append(("Other", rest))

    def purpose(doc):
        """First clause of the tool doc: up to the first '. ', ': ' or '; ' outside parentheses."""
        d = " ".join(doc.split())
        depth, cut = 0, len(d)
        for i, ch in enumerate(d):
            depth += (ch == "(") - (ch == ")")
            if depth == 0 and ch in ".:;" and (i + 1 == len(d) or d[i + 1] == " "):
                cut = i
                break
        s = d[:cut]
        return s if len(s) <= 120 else s[:117].rstrip() + "..."

    rows = []
    for gname, names in groups:
        rows.append(f"## {gname}")
        for n in names:
            if n not in tools:
                continue
            t = tools[n]
            args = list(t["args"].get("properties", {}).keys())
            res = ", ".join(f"{k or 'result'}: {v}" for k, v in t["result_schemas"].items()) or "-"
            rows.append([f"`{n}`", "/".join(t["profiles"]), "yes" if t["mutates"] else "no",
                         ", ".join(args) if args else "-", res, t["since"].replace("amm-tools/", ""),
                         purpose(t["doc"])])
            L.add("T2", f"{n}.profiles", "/".join(t["profiles"]), src, f"tools.{n}.profiles", script=S)
            L.add("T2", f"{n}.n_args", len(args), src, f"len(tools.{n}.args.properties)", status="derived",
                  script=S)
    n_tools = len(tools)
    nB = sum("B" in t["profiles"] for t in tools.values())
    nC = sum("C" in t["profiles"] for t in tools.values())
    L.add("T2", "n_tools", n_tools, src, "len(tools)", status="derived", script=S)
    L.add("T2", "n_tools_profile_B", nB, src, "count of tools with B in profiles", status="derived", script=S)
    L.add("T2", "n_tools_profile_C", nC, src, "count of tools with C in profiles", status="derived", script=S)
    L.add("T2", "schema_version", c["schema_version"], src, "schema_version", script=S)
    L.add("T2", "outcome_schema", c["outcome_schema"], src, "outcome_schema", script=S)
    outs = c["outcomes"]
    L.add("T2", "n_outcomes", len(outs), src, "len(outcomes)", status="derived", script=S)
    rule = c["refusal_rule"]
    notes = [
        f"Contract {c['schema_version']} ({n_tools} tools; profile B {nB}, profile C {nC}); results carry the "
        f"outcome schema {c['outcome_schema']}. Source: `{src}` (written by `scripts/software/write_contract.py`).",
        "Outcomes: " + "; ".join(f"{v['title']} (`{k}`)" for k, v in outs.items()) +
        ". Five are physical outcomes; `need_info` stops the session and asks.",
        "Refusal rule (profile " + "/".join(c["refusal_rule_profiles"]) + "; not applied in ablation profile B): "
        + "; ".join(f"{k} needs one of {', '.join(v)}" for k, v in rule.items()) + ".",
        "Interfaces: every tool is called through `amm.tools.Session.call` (Python library); the MCP server "
        "(`amm/mcp_server.py`) registers the tools of the session's profile; the browser GUI backend (`app/`) calls "
        "the same Session; the command line (`amm/cli.py`, added in V2) passes its arguments unchanged to "
        "`Session.call`. Interface acceptance through library, MCP, GUI and CLI: table T12 (V2).",
        "'Changes spec' = the tool mutates the session's specification (logged and replayable).",
    ]
    for k in sorted(x for x in c if x.startswith("added_in_schema_")):
        notes.append(f"Added in schema {k.rsplit('_', 1)[1]}: " + _short_json(c[k]) + ".")
    return write_table("T2_tool_contract", f"Tool contract ({c['schema_version']}): tools, inputs, outputs and profiles",
                       ["Tool", "Profiles", "Changes spec", "Inputs", "Result schema", "Since", "Purpose"], rows,
                       notes, colspec="lllp{3.2cm}p{2.2cm}lp{5.2cm}", label="tab:contract")


# ============================================================================================================ T3
def t3_checks(L: Ledger):
    cf, bf, gf = "amm/certify.py", "amm/bloch.py", "amm/geometry.py"
    cc, bc, gc = module_constants(cf), module_constants(bf), module_constants(gf)
    cd, bd = function_defaults(cf), function_defaults(bf)
    src_ids = {cf: sha16(cf), bf: sha16(bf), gf: sha16(gf)}

    def const(mod, name, file):
        v, line, com = mod[name]
        return v, f"{file}:{line}", com

    def dflt(d, fn, arg, file):
        v, line = d[fn][arg]
        return v, f"{file}:{line}"

    def lit(file, pattern, rx):
        ln = find_line(file, pattern)
        line = read_text(file).splitlines()[ln - 1]
        return re.search(rx, line).group(1), f"{file}:{ln}"

    rows = []

    def add(block, check, value, loc, assumption, key):
        rows.append([check, str(value), loc, assumption])
        L.add("T3", key, str(value), loc.split(":")[0], f"{loc} (sha256 {src_ids.get(loc.split(':')[0], '')})",
              script=S)

    rows.append("## Static block (stiffness, density, nu100)")
    v, loc = dflt(cd, "certify", "static_ladder", cf)
    add("static", "Resolution ladder (n1, n2, n3), tried in order", " → ".join(str(tuple(r)) for r in v), loc,
        "first rung that converges and whose guarded bounds meet every target is used; else next rung", "ladder")
    v, loc, com = const(cc, "STATIC_PHASES", cf)
    add("static", "Grid phases solved at every resolution (voxel widths)", "0, " + ", ".join(map(str, v)), loc,
        "spread over phases is discretization error from where surfaces cut voxels", "phases")
    v, loc = dflt(cd, "certify", "tol_static", cf)
    add("static", "Convergence tolerance on remaining error and phase spread", f"{v} (relative; absolute for nu100)",
        loc, "quantities carrying a target must converge", "tol_static")
    v, loc = dflt(cd, "static_convergence", "flat", cf)
    add("static", "Flat-sequence threshold", f"{v} (relative change)", loc,
        "changes below it, or within 2x the phase spread, count as converged noise", "flat")
    v, loc, com = const(cc, "STATIC_P_MAX", cf)
    add("static", "Cap on the fitted convergence order", v, loc, com.replace("results/g2/NOTES.md", "G2"), "p_max")
    v, loc, com = const(cc, "STATIC_SAFETY", cf)
    add("static", "Guard factor on the remaining error", f"{v} (bounds = ext ± {v} e and every computed value)", loc,
        "calibrated on G2 cells; not a continuum theorem", "static_safety")
    v, loc = lit(cf, r'max_residual"\] <= ', r'max_residual"\] <= ([0-9.e+-]+)')
    add("static", "FP64 residual, all six load cases", f"≤ {v}", loc, "per solve; failure → undetermined", "residual")
    v, loc = lit(cf, r'asymmetry"\] <= ', r'asymmetry"\] <= ([0-9.e+-]+)')
    add("static", "Asymmetry |C − Cᵀ|/|C|", f"≤ {v}", loc, "per solve", "asymmetry")
    v, loc = lit(cf, r'min_eig"\] > ', r'min_eig"\] > ([0-9.e+-]+)')
    add("static", "Positive definiteness (min eigenvalue of C*)", f"> {v}", loc, "per solve", "min_eig")
    v, loc = lit(cf, r'removed_fraction"\] <= ', r'removed_fraction"\] <= ([0-9.e+-]+)')
    add("static", "Solid removed as floating islands", f"≤ {v}", loc,
        "more, or no percolation in x, y, z → invalid geometry → refuted", "islands")
    v, loc, com = const(gc, "C_MIN", gf)
    add("static", "Void floor (voxel solid coverage)", f"< {v} → void", loc, com, "c_min")
    v, loc, com = const(cc, "FCM_ALPHA", cf)
    add("static", "Finite-cell stiffness floor on solver retry", v, loc, com.split(";")[0], "fcm_alpha")
    v, loc, com = const(cc, "FROM_ABOVE", cf)
    add("static", "Quantities that converge from above", ", ".join(v), loc,
        "a min target on these is refuted by the largest computed value even before convergence", "from_above")

    rows.append("## Bloch block (complete gap claim [f_lo, f_hi], f* = f a / c_t)")
    v, loc = dflt(cd, "certify", "res_bloch", cf)
    add("bloch", "Counted resolutions (inertia counts)", ", ".join(map(str, v)), loc,
        "exact statements about the discretized model at each sampled k", "res_bloch")
    v, loc = dflt(cd, "certify", "n_path", cf)
    path = " ".join(bc["SC_PATH"][0])
    add("bloch", "Irreducible-zone path, points per leg", f"{v} ({path})", loc,
        "cubic point symmetry of the cell is assumed", "n_path")
    v, loc = dflt(cd, "certify", "n_interior", cf)
    add("bloch", "Random interior k (seed 0)", v, loc, "sampling; no unsampled-k guarantee", "n_interior")
    v, loc = dflt(cd, "certify", "adversarial_n", cf)
    ai, li = bd["adversarial_ks"]["n_interior"]
    tp, _ = bd["adversarial_ks"]["top"]
    rd, _ = bd["adversarial_ks"]["rounds"]
    add("bloch", "Adversarial k search (GPU, coarse mesh)",
        f"n = {v}; path + {ai} interior, top {tp} starts per edge, {rd} pattern rounds (26 directions)",
        f"{loc}; {bf}:{li}", "finds interior extrema missed by path and random sampling", "adversarial")
    v, loc = dflt(bd, "certify_gap", "zero_tol_f", bf)
    add("bloch", "Count condition at every k", f"count(f_lo) = count(f_hi) = band index; Γ: exactly 3 modes below "
        f"f* = {v}", loc, "a non-percolating cell fails at Γ; no perturbed pivots, even raw counts", "counts")
    v, loc, com = const(cc, "BLOCH_EDGE_RES", cf)
    add("bloch", "Edge-only third resolution (Lanczos at the 2 extreme k)", ", ".join(map(str, v)), loc,
        "gives the three-resolution order fit", "edge_res")
    v, loc, com = const(cc, "BLOCH_PHASES", cf)
    add("bloch", "Grid phases at the finest counted resolution", ", ".join(map(str, v)), loc,
        "phase spread enters the edge guard", "bloch_phases")
    v, loc, com = const(bc, "CONVERGENCE_SAFETY", bf)
    add("bloch", "Edge guard factor on the remaining error", v, loc,
        "calibrated on one published case (Lucklum and Vellekoop 2018); empirical, not a proof", "edge_safety")
    v, loc, com = const(bc, "P_MAX", bf)
    v2, loc2, _ = const(bc, "P_MIN", bf)
    add("bloch", "Fitted order range for the edge guard", f"capped at {v}; below {v2} fails closed",
        f"{loc}; {bf}:{loc2.split(':')[1]}", "non-monotone beyond the phase noise fails closed", "edge_p")
    v, loc = lit(cf, r'density_spread"\] <= ', r'density_spread"\] <= ([0-9.e+-]+)')
    add("bloch", "Density agreement between counted resolutions", f"≤ {v}", loc, "", "density_spread")
    v, loc = lit(bf, r"probe = e \* \(1 \+ ", r"\(1 \+ ([0-9.e+-]+)\)")
    add("bloch", "Screening probe at the current edge (relative)", v, loc,
        "every non-solved k is screened by one inertia count", "probe")

    rows.append("## As-built flag (robustness; not required for release)")
    v, loc = dflt(cd, "certify", "as_built_offset", cf)
    add("as_built", "Surface erosion and dilation", f"± {v} a (fraction of the cell edge)", loc,
        "static targets (densities excluded) and gap counts re-checked at coarse n", "as_built_offset")

    notes = ["Every check is acceptance under the stated discretization, sampling and guard assumptions, not a "
             "continuum theorem. Values are read from the checker source with `ast`/regex at generation time; "
             "'Source' gives file:line at that time (file hashes in the ledger).",
             "Verdicts: certified (guarded bound clears every target), refuted (the opposite guarded bound misses "
             "it, or the geometry is not a connected load-bearing solid), undetermined (target inside the guard "
             "band, not converged, or a solver failure). Only certified releases a design."]
    return write_table("T3_acceptance_checks", "Acceptance checks per certificate block, thresholds and assumptions",
                       ["Check", "Value", "Source", "Assumption / effect"], rows, notes,
                       colspec="p{4.6cm}p{3.6cm}p{2.6cm}p{4.6cm}", label="tab:checks")


# ============================================================================================================ T4
def t4_verification(L: Ledger):
    rows = []
    notes = []
    # ---------- earlier one-sided and identity checks
    rows.append("## Earlier checks (V1a): one-sided bounds, identity and a published gap")
    rsrc = "results/verification/registry_rows.csv"
    rr = read_csv(rsrc)
    lb = [r for r in rr if r["load_bearing"] == "True"]
    agree = [r for r in lb if float(r["rel_err"]) <= 1e-8]
    dis = [r for r in lb if float(r["rel_err"]) > 1e-8]
    max_agree = max(float(r["rel_err"]) for r in agree)
    med = st.median(float(r["rel_err"]) for r in lb)
    dis_rho = sum(r["rho_mismatch"] == "True" for r in dis)
    L.add("T4", "registry.rows", len(rr), rsrc, "row count", status="derived", script=S)
    L.add("T4", "registry.load_bearing", len(lb), rsrc, "load_bearing == True", status="derived", script=S)
    L.add("T4", "registry.agree", len(agree), rsrc, "load-bearing rows with rel_err <= 1e-8", status="derived",
          script=S)
    L.add("T4", "registry.max_rel_err_agree", max_agree, rsrc, "max rel_err over agreeing rows", status="derived",
          script=S)
    L.add("T4", "registry.median_rel_err", med, rsrc, "median rel_err, load-bearing", status="derived", script=S)
    L.add("T4", "registry.disagree_rho_mismatch", dis_rho, rsrc, "disagreeing rows with rho_mismatch", status="derived",
          script=S)
    sm = read_json("results/verification/registry_rows_summary.json")
    if (sm["rows"], sm["load_bearing"], sm["n_above_1e_8"]) != (len(rr), len(lb), len(dis)):
        L.conflict("T4", "registry counts", {"registry_rows.csv": (len(rr), len(lb), len(dis)),
                                             "registry_rows_summary.json": (sm["rows"], sm["load_bearing"],
                                                                            sm["n_above_1e_8"])}, script=S)
    rows.append(["Registry catalogue rows (arXiv 2609.14741), same mask and element", "two-sided (identity)",
                 f"{len(agree)}/{len(lb)} load-bearing rows agree",
                 f"≤ {max_agree:.2g} relative (median {med:.2g}); the {len(dis)} others have a stored density that "
                 f"differs from the rebuilt mask ({dis_rho}/{len(dis)}), all flagged infeasible in the registry",
                 "registry_rows.csv"])

    gsrc = "results/g2/classification_v5.json"
    cells = read_json(gsrc)
    pair = collections.Counter((c["verdict"], c["truth"]) for c in cells)
    tg = collections.Counter(t["cls"] for c in cells for t in c["targets"])
    fc = sum(1 for c in cells if c["verdict"] == "certified" and c["truth"] == "false")
    fr = sum(1 for c in cells if c["verdict"] == "refuted" and c["truth"] == "true")
    for k, v in pair.items():
        L.add("T4", f"G2.cells.{k[0]}|{k[1]}", v, gsrc, "count (verdict, truth)", status="derived", script=S)
    L.add("T4", "G2.n_cells", len(cells), gsrc, "len", status="derived", script=S)
    L.add("T4", "G2.targets_certified", tg["certified"], gsrc, "count targets cls == certified", status="derived",
          script=S)
    L.add("T4", "G2.targets_abstention", tg["abstention"], gsrc, "count targets cls == abstention",
          status="derived", script=S)
    L.add("T4", "G2.false_certifications", fc, gsrc, "certified & truth false", status="derived", script=S)
    L.add("T4", "G2.false_refutations", fr, gsrc, "refuted & truth true", status="derived", script=S)
    ntrue = sum(v for k, v in pair.items() if k[1] == "true")
    rows.append([f"G2: {len(cells)} clean cells (three-way verdict; definition set after the data)",
                 "against converged references",
                 f"false certifications {fc}, false refutations {fr}",
                 f"certified {pair[('certified', 'true')]} of {ntrue} true cells; undetermined: "
                 f"{pair[('undetermined', 'true')]} true, {pair[('undetermined', 'undetermined')]} "
                 f"undetermined-truth, {pair[('undetermined', 'false')]} false; targets {tg['certified']} certified, "
                 f"{tg['abstention']} abstentions", "g2/classification_v5.json"])

    # published gap
    lsrc = "results/verification/lucklum2018_ball079_beam005.json"
    lk = {r["n"]: r for r in read_json(lsrc)}
    gl = lambda n: lk[n]["gaps_fa_over_cl"][0]
    r_ = (1 / 60) / (1 / 40 - 1 / 60)
    ext_lo = gl(60)["f_lo"] + (gl(60)["f_lo"] - gl(40)["f_lo"]) * r_
    ext_hi = gl(60)["f_hi"] + (gl(60)["f_hi"] - gl(40)["f_hi"]) * r_
    p_lo, p_hi = lk[60]["paper"]["lo"], lk[60]["paper"]["hi"]
    L.add("T4", "lucklum.ext_lo", round(ext_lo, 4), lsrc, "O(h) extrapolation from n = 40, 60: f60 + (f60 - f40) * 2",
          status="derived", script=S)
    L.add("T4", "lucklum.ext_hi", round(ext_hi, 4), lsrc, "O(h) extrapolation from n = 40, 60", status="derived",
          script=S)
    L.add("T4", "lucklum.paper_lo", p_lo, lsrc, "paper.lo", script=S)
    L.add("T4", "lucklum.paper_hi", p_hi, lsrc, "paper.hi", script=S)
    L.add("T4", "lucklum.dev_hi", pct(ext_hi / p_hi - 1, 2), lsrc, "ext_hi / paper_hi - 1", status="derived",
          script=S)
    L.add("T4", "lucklum.dev_lo", pct(ext_lo / p_lo - 1, 2), lsrc, "ext_lo / paper_lo - 1", status="derived",
          script=S)
    notes_txt = read_text("results/verification/NOTES.md")
    m = re.search(r"O\(h\) extrapolation from 40, 60 \| \*\*([0-9.]+)\*\* \| \*\*([0-9.]+)\*\*", notes_txt)
    if m and (m.group(1) != f"{ext_lo:.4f}" or m.group(2) != f"{ext_hi:.4f}"):
        L.conflict("T4", "Lucklum extrapolated edges",
                   {"results/verification/NOTES.md (section 4 table)": f"{m.group(1)}, {m.group(2)}",
                    f"{lsrc} (recomputed from n = 40, 60)": f"{ext_lo:.4f}, {ext_hi:.4f}"}, script=S,
                   note="last-digit difference on the upper edge (0.47221 rounds to 0.4722)")
    rows.append(["Published gap (Lucklum and Vellekoop 2018), ball 0.79a / beam 0.05a, n = 20-60",
                 "two-sided (published value)", f"lower {ext_lo:.4f} vs {p_lo}; upper {ext_hi:.4f} vs {p_hi}",
                 f"{pct(ext_lo / p_lo - 1, 1)} / {pct(ext_hi / p_hi - 1, 1)} (O(h) extrapolation, n = 40, 60)",
                 "lucklum2018_*.json"])

    gsrc2 = "results/verification/gap_convergence_guard.json"
    gg = read_json(gsrc2)
    a, b = gg["overstated_upper_0.478|guard=True"], gg["conservative_0.46|guard=True"]
    a0 = gg["overstated_upper_0.478|guard=False"]
    L.add("T4", "guard.overstated_counts_pass", a0["passed"], gsrc2, "overstated_upper_0.478|guard=False.passed",
          script=S)
    L.add("T4", "guard.overstated_guard_pass", a["passed"], gsrc2, "overstated_upper_0.478|guard=True.passed",
          script=S)
    L.add("T4", "guard.conservative_guard_pass", b["passed"], gsrc2, "conservative_0.46|guard=True.passed", script=S)
    L.add("T4", "guard.safe_hi", a["safe_interval_fa_over_cl"][1], gsrc2, "safe_interval_fa_over_cl[1]", script=S)
    rows.append(["Edge guard on the same cell (mutation: claim true at n = 20, 30, false in the limit)",
                 "one-sided (refusal)",
                 f"claim {a['claim_fa_over_cl'][0]}-{a['claim_fa_over_cl'][1]}: counts pass, guard "
                 f"{'refuses' if not a['passed'] else 'passes'}; claim {b['claim_fa_over_cl'][0]}-"
                 f"{b['claim_fa_over_cl'][1]}: {'passes' if b['passed'] else 'refused'}",
                 f"upper safe edge {a['safe_interval_fa_over_cl'][1]} (paper {p_hi})", "gap_convergence_guard.json"])

    isrc = "results/verification/indep/summary.json"
    ind = read_json(isrc)
    n_chk = n_ok = 0
    gap_rows = []
    for r in ind["rows"]:
        for n, v in r["indep"].items():
            for q, s in v["static"].items():
                if "necessary_check_passed" in s:
                    n_chk += 1
                    n_ok += bool(s["necessary_check_passed"])
            if "gap" in v and v["gap"]["amm_gap_verdict"] == "certified":
                gap_rows.append((r["name"], n, v["gap"]))
    n_case = len(ind["rows"])
    combos = {re.sub(r"_g2$", "", r["name"]) for r in ind["rows"]}
    L.add("T4", "q2.checks", n_chk, isrc, "count necessary_check_passed fields", status="derived", script=S)
    L.add("T4", "q2.passed", n_ok, isrc, "count necessary_check_passed == True", status="derived", script=S)
    L.add("T4", "q2.cases", n_case, isrc, "len(rows)", status="derived", script=S)
    L.add("T4", "q2.geometry_nu_combinations", len(combos), isrc, "distinct names without _g2", status="derived",
          script=S)
    rows.append([f"Independent Q2 FE (own code), {n_case} cube-and-bars cases ({len(combos)} geometry-ν "
                 "combinations), n = 20, 40", "one-sided (necessary)",
                 f"amm guarded lower ≤ Q2 upper bound: {n_ok}/{n_chk}", "E100, G, bulk", "indep/summary.json"])
    ssrc = "results/verification/skfem/summary.json"
    sk = read_json(ssrc)
    L.add("T4", "skfem.n_checks", sk["n_checks"], ssrc, "n_checks", script=S)
    L.add("T4", "skfem.n_passed", sk["n_passed"], ssrc, "n_passed", script=S)
    L.add("T4", "skfem.kubc_ge_periodic", f"{sk['kubc_ge_periodic'][0]}/{sk['kubc_ge_periodic'][1]}", ssrc,
          "kubc_ge_periodic", script=S)
    L.add("T4", "skfem.homogeneous_C_error", sk["homogeneous_C_error"], ssrc, "homogeneous_C_error", script=S)
    skn = sorted({r["n"] for r in sk["rows"]})
    rows.append([f"scikit-fem KUBC (third-party assembly), same cases, n = {', '.join(map(str, skn))}",
                 "one-sided (upper bound)",
                 f"amm guarded lower ≤ KUBC: {sk['n_passed']}/{sk['n_checks']}",
                 f"KUBC ≥ periodic Q2 {sk['kubc_ge_periodic'][0]}/{sk['kubc_ge_periodic'][1]}; homogeneous solid "
                 f"{sk['homogeneous_C_error']:.1g}", "skfem/summary.json"])
    up = sum(bool(x[2]["upper_edge_check_passed"]) for x in gap_rows)
    lo = sum(bool(x[2]["consistent_lower_edge"]) for x in gap_rows)
    ncert = len({x[0] for x in gap_rows})
    L.add("T4", "q2gap.certified_cases", ncert, isrc, "cases with certified gap and Q2 Bloch", status="derived",
          script=S)
    L.add("T4", "q2gap.checks", len(gap_rows), isrc, "(case, n) pairs", status="derived", script=S)
    L.add("T4", "q2gap.upper_pass", up, isrc, "upper_edge_check_passed", status="derived", script=S)
    L.add("T4", "q2gap.lower_consistent", lo, isrc, "consistent_lower_edge", status="derived", script=S)
    rows.append([f"Q2 Bloch at high-symmetry k on the {ncert} certified gap cases", "one-sided (upper edge)",
                 f"upper-edge check {up}/{len(gap_rows)}; lower edge consistent {lo}/{len(gap_rows)}",
                 f"{len(gap_rows)} resolution-level checks", "indep/summary.json"])

    # ---------- V1b two-sided
    vsrc = "results/verification/v1b/T4_v1b.csv"
    v = read_csv(vsrc)
    stat = [r for r in v if r["check"].startswith("static:") or r["check"].startswith("gap:")]
    statuses = [r[k] for r in stat for k in ("status_lower", "status_upper") if r[k]]
    sc = collections.Counter(statuses)
    claims = [r for r in v if r["check"].startswith("claim:")]
    cc = collections.Counter(r["claim_status"] for r in claims)
    cells_ = list(dict.fromkeys(r["cell"] for r in v))
    L.add("T4", "v1b.cells", len(cells_), vsrc, "distinct cell", status="derived", script=S)
    L.add("T4", "v1b.bounds", len(statuses), vsrc, "status_lower/upper entries of static and gap rows",
          status="derived", script=S)
    for k in ("sound", "marginal", "unsound"):
        L.add("T4", f"v1b.bounds_{k}", sc.get(k, 0), vsrc, f"count {k}", status="derived", script=S)
    L.add("T4", "v1b.claims", len(claims), vsrc, "claim rows", status="derived", script=S)
    for k in ("agrees", "inconclusive", "disagrees"):
        L.add("T4", f"v1b.claims_{k}", cc.get(k, 0), vsrc, f"count claim_status {k}", status="derived", script=S)
    # cross-check against NOTES verdict text
    nt = read_text("results/verification/v1b/NOTES.md")
    m = re.search(r"0 of (\d+) guarded bounds / safe edges are unsound \((\d+) sound, (\d+) marginal\)", nt)
    if m and (int(m.group(1)), int(m.group(2)), int(m.group(3))) != (len(statuses), sc["sound"], sc["marginal"]):
        L.conflict("T4", "V1b bound counts", {"v1b/NOTES.md": m.groups(), vsrc: (len(statuses), sc["sound"],
                                                                                  sc["marginal"])}, script=S)
    # stale per-k sentence in NOTES (mid-point finding 2, only partly corrected)
    sl = [r for r in v if r["cell"].startswith("thin_sl_c0.402") and r["check"] == "gap:lo_edge"][0]
    m2 = re.search(r"certificate's own extrapolated SL c\.40 lower edge is ([+-][0-9.]+) %", nt)
    if m2 and abs(float(m2.group(1)) - 100 * float(sl["delta_rel"])) > 0.05:
        L.conflict("T4", "V1b SL c.40 extrapolated lower-edge delta",
                   {"v1b/NOTES.md section 1.3 (per-k paragraph)": f"{m2.group(1)} %",
                    vsrc + " (gap:lo_edge delta_rel)": pct(float(sl["delta_rel"]))}, script=S,
                   note="the 2026-11-08 correction fixed the gap-edge bullet but not this later sentence; the "
                        "tables use the CSV value")
    # cross-check CSV vs summary.json gap deltas
    vs = read_json("results/verification/v1b/summary.json")
    for cid, c in vs.items():
        if c.get("gap"):
            d_sum = c["gap"]["delta_ext"]
            d_csv = [float(r["delta_rel"]) for r in v if r["cell"] == cid and r["check"] in ("gap:lo_edge",
                                                                                             "gap:hi_edge")]
            if any(abs(a - b) > 1e-6 for a, b in zip(d_sum, d_csv)):
                L.conflict("T4", f"V1b gap delta {cid}", {"summary.json": d_sum, "T4_v1b.csv": d_csv}, script=S)
    # static deltas per family (E100, G, bulk)
    fam = collections.defaultdict(list)
    for r in v:
        if r["check"] in ("static:E100", "static:G", "static:bulk"):
            fam[r["family"]].append((abs(float(r["delta_rel"])), r["cell"], r["check"]))
    rows.append("## Two-sided comparison V1b: six representative cells, Q2-FCM reference (own independent code)")
    n_dens_marg = sum(r[k] == "marginal" for r in stat if r["check"] == "static:density"
                      for k in ("status_lower", "status_upper"))
    L.add("T4", "v1b.marginal_density_bounds", n_dens_marg, vsrc, "marginal statuses on static:density rows",
          status="derived", script=S)
    inc = [f"{r['cell'].split('_nu')[0]} {r['check'].split(':', 1)[1]}" for r in claims
           if r["claim_status"] == "inconclusive"]
    rows.append(["Guarded static bounds and gap safe edges", "two-sided (reference ± 2u)",
                 f"{sc.get('unsound', 0)} unsound of {len(statuses)} ({sc['sound']} sound, {sc['marginal']} marginal)",
                 f"{n_dens_marg} of the marginal are density bounds (guard band narrower than the reference "
                 "uncertainty)", "v1b/T4_v1b.csv"])
    rows.append(["Certified claims (nominal and marginal)", "two-sided",
                 f"{cc.get('disagrees', 0)} disagree of {len(claims)} ({cc['agrees']} agree, "
                 f"{cc['inconclusive']} inconclusive)", "inconclusive: " + "; ".join(inc),
                 "v1b/T4_v1b.csv"])
    famname = {"tpms": "TPMS", "struts": "struts", "resonator": "thin resonators"}
    for f in ("tpms", "struts", "resonator"):
        xs = sorted(fam[f], reverse=True)
        worst = xs[0]
        L.add("T4", f"v1b.static_max_abs_delta.{f}", pct(worst[0], 1, sign=False), vsrc,
              f"max |delta_rel| over E100/G/bulk, family {f} ({worst[1]} {worst[2]})", status="derived", script=S)
        extra = ""
        if f == "resonator":
            nog = [x for x in xs if x[2] != "static:G"]
            L.add("T4", "v1b.static_max_abs_delta.resonator_E100_bulk", pct(nog[0][0], 1, sign=False), vsrc,
                  "max |delta_rel| over E100/bulk, resonators", status="derived", script=S)
            extra = f"; E100 and bulk ≤ {pct(nog[0][0], 1, sign=False)} (G of SL c 0.40 is flagged unconverged by " \
                    "amm, no claim uses it)"
        rows.append([f"Static E100, G, bulk, {famname[f]}", "two-sided", f"max |δ| {pct(worst[0], 1, sign=False)}",
                     f"{worst[1].split('_nu')[0]} {worst[2].split(':')[1]}{extra}", "v1b/T4_v1b.csv"])
    gaps = [r for r in v if r["check"] in ("gap:lo_edge", "gap:hi_edge")]
    gmax = max(gaps, key=lambda r: abs(float(r["delta_rel"])))
    kcov = max(float(r["k_coverage_delta"]) for r in gaps)
    L.add("T4", "v1b.gap_max_abs_delta", pct(abs(float(gmax["delta_rel"])), 2, sign=False), vsrc,
          f"max |delta_rel| of gap edges ({gmax['cell']} {gmax['check']})", status="derived", script=S)
    L.add("T4", "v1b.k_coverage_max", kcov, vsrc, "max k_coverage_delta", status="derived", script=S)
    bim = sum(len(c["gap"]["band_index_mismatch"]) for c in vs.values() if c.get("gap"))
    L.add("T4", "v1b.band_index_mismatch", bim, "results/verification/v1b/summary.json",
          "sum len(gap.band_index_mismatch)", status="derived", script=S)
    rows.append([f"Gap edges, {len(gaps) // 2} gap cells (extrapolated amm edge vs reference)", "two-sided",
                 f"max |δ| {pct(abs(float(gmax['delta_rel'])), 2, sign=False)}",
                 f"{gmax['cell'].split('_nu')[0]} {gmax['check'].split(':')[1]}; k beyond amm's sample ≤ "
                 f"{kcov:.1g}; band-index mismatches {bim}", "v1b/T4_v1b.csv"])
    rows.append(["V1b verdict (registered rule)", "", "PASS",
                 "with qualifications: reference levels extended after first comparisons (deviations 4, 6)",
                 "v1b/NOTES.md 1.2"])

    # ---------- V1c third party
    dsrc = "results/verification/dolfinx/summary.csv"
    dv = read_csv(dsrc)
    ev = collections.Counter([r["verdict_lo"] for r in dv] + [r["verdict_hi"] for r in dv])
    cin = sum(r["claim_inside_ref"] == "True" for r in dv)
    kb = sum(r["k_beyond_safe"] == "True" for r in dv)
    for k in ("sound", "marginal", "unsound"):
        L.add("T4", f"v1c.edges_{k}", ev.get(k, 0), dsrc, f"count verdict_lo/hi == {k}", status="derived", script=S)
    L.add("T4", "v1c.cases", len(dv), dsrc, "rows", status="derived", script=S)
    L.add("T4", "v1c.claims_inside", cin, dsrc, "claim_inside_ref == True", status="derived", script=S)
    L.add("T4", "v1c.k_beyond", kb, dsrc, "k_beyond_safe == True", status="derived", script=S)
    # variants and literal identity from case JSONs
    var = collections.Counter()
    res_dfx, res_amm, fmax = 0.0, 0.0, 0.0
    for r in dv:
        cj = read_json(f"results/verification/dolfinx/{r['case']}.json")
        for vk, key in (("final", None), ("coarse", "coarse_reference"), ("hmax", "hmax_reference"),
                        ("per_k", "per_k_reference")):
            blk = cj if key is None else cj[key]
            var[(vk, "marginal")] += [blk["verdict_lo"], blk["verdict_hi"]].count("marginal")
            var[(vk, "unsound")] += [blk["verdict_lo"], blk["verdict_hi"]].count("unsound")
        for row in cj["identity"]["rows"]:
            res_dfx = max(res_dfx, row["res_dfx"])
            res_amm = max(res_amm, row["res_amm"])
        fmax = max(fmax, cj["identity"]["max_rel_diff"])
    for vk in ("final", "coarse", "hmax", "per_k"):
        L.add("T4", f"v1c.variant_{vk}_marginal", var[(vk, "marginal")], "results/verification/dolfinx/<case>.json",
              f"count marginal ({vk} reference)", status="derived", script=S)
        L.add("T4", f"v1c.variant_{vk}_unsound", var[(vk, "unsound")], "results/verification/dolfinx/<case>.json",
              f"count unsound ({vk} reference)", status="derived", script=S)
    L.add("T4", "v1c.identity_max_rel_freq", fmax, "results/verification/dolfinx/<case>.json",
          "max identity.max_rel_diff", status="derived", script=S)
    L.add("T4", "v1c.identity_max_res_dolfinx", res_dfx, "results/verification/dolfinx/<case>.json",
          "max identity.rows[].res_dfx", status="derived", script=S)
    L.add("T4", "v1c.identity_max_res_amm", res_amm, "results/verification/dolfinx/<case>.json",
          "max identity.rows[].res_amm", status="derived", script=S)
    literal_identity = fmax <= 1e-6 and res_dfx <= 1e-8 and res_amm <= 1e-8
    _dn = "results/verification/dolfinx/NOTES.md"
    _ln = next(i for i, x in enumerate(read_text(_dn).splitlines(), 1) if "eigen residuals <= 1e-8 on both sides" in x)
    L.add("T4", "v1c.identity_residual_tol", "1e-8", _dn, f"registered identity criterion, {_dn}:{_ln}", script=S)
    literal = "weak" if (not literal_identity or ev.get("unsound", 0) or cin < len(dv)) else (
        "strong" if ev.get("marginal", 0) <= 1 and kb == 0 else "adequate")
    L.add("T4", "v1c.literal_gate", literal, "results/verification/dolfinx/<case>.json; dolfinx/NOTES.md protocol",
          "registered gate applied to identity (freq <= 1e-6 and residuals <= 1e-8 both sides), edges, claims",
          status="derived", script=S)
    csv_id = all(r["identity_passed"] == "True" for r in dv)
    if csv_id != literal_identity:
        L.conflict("T4", "V1c identity test", {"dolfinx/summary.csv identity_passed": "True (8/8)" if csv_id else
                                               "False", "registered criterion (residual <= 1e-8 both sides)":
                                               f"fails: DOLFINx residual {res_dfx:.2g}"}, script=S,
                   note="documented in dolfinx/NOTES.md correction log: compare.py checks frequencies only")
    gnc = sorted(float(r["gap_not_certified"]) for r in dv)
    L.add("T4", "v1c.gap_not_certified_range", f"{pct(gnc[0], 0, False)}-{pct(gnc[-2], 0, False)}; "
          f"{pct(gnc[-1], 0, False)}", dsrc, "sorted gap_not_certified (7 smallest range; largest)", status="derived",
          script=S)
    mc = collections.Counter(r["model"] for r in dv)
    L.add("T4", "v1c.cells_exact", mc["exact"], dsrc, "model == exact", status="derived", script=S)
    L.add("T4", "v1c.cells_fcm", mc["fcm"], dsrc, "model == fcm (amm voxel occupancy)", status="derived", script=S)
    rows.append(f"## Third-party comparison V1c: DOLFINx 0.11 + dolfinx_mpc, {len(dv)} cells ({mc['exact']} exact "
                f"geometry, {mc['fcm']} on amm's voxel occupancy)")
    rows.append(["Guarded gap edges (16)", "two-sided (reference ± 2u)",
                 f"{ev.get('unsound', 0)} unsound ({ev['sound']} sound, {ev['marginal']} marginal)",
                 f"amended procedure; with the levels as first planned: {var[('coarse', 'marginal')]} marginal, "
                 f"{var[('coarse', 'unsound')]} unsound", "dolfinx/summary.csv, <case>.json"])
    rows.append(["Claims inside the reference interval; third-party k beyond amm's safe interval", "two-sided",
                 f"{cin}/{len(dv)} inside; {kb} beyond", "", "dolfinx/summary.csv"])
    rows.append(["Bloch implementation identity (Q1 midpoint model, n = 20, 6 k)", "identity",
                 f"frequencies ≤ {fmax:.2g} relative (tolerance 1e-6)",
                 f"residual criterion ≤ 1e-8 not met by the letter: DOLFINx side up to {res_dfx:.2g} (amm side "
                 f"{res_amm:.2g})",
                 "dolfinx/<case>.json"])
    rows.append(["Uncertified share of the reference gap", "descriptive",
                 f"{pct(gnc[0], 0, False)}-{pct(gnc[-2], 0, False)} (7 cells)", f"bcc strut {pct(gnc[-1], 0, False)}",
                 "dolfinx/summary.csv"])
    rows.append(["V1c gate verdict", "", f"literal registered verdict: {literal.upper()}",
                 "qualified assessment: ADEQUATE (identity frequencies agree far inside tolerance; deviations 5, 9 "
                 "post-result; deviation 7 undated); does not establish unsampled-k soundness",
                 "dolfinx/NOTES.md correction log"])
    notes += ["δ = (amm extrapolated estimate − reference)/|reference|. Sound/marginal/unsound: the guarded bound "
              "lies beyond, within or short of the reference ± 2u (u: reference uncertainty from three levels).",
              "Q2-FCM and amm share design formulas, numpy/scipy and MKL PARDISO; scikit-fem shares the Q2 geometry "
              "evaluator (semi-independent). On the three curved V1c cells DOLFINx uses amm's voxel occupancy, so "
              "geometry representation is not tested there.",
              "Every check is acceptance under stated discretization, sampling and guard assumptions; none "
              "establishes soundness at unsampled k."]
    return write_table("T4_verification", "Verification summary: one-sided, identity and two-sided checks",
                       ["Check", "Type", "Result", "Worst case / qualification", "Source"], rows, notes,
                       colspec="p{4.2cm}p{2.2cm}p{3.6cm}p{4.6cm}p{2.2cm}", label="tab:verification")


# ============================================================================================================ T5
def t5_search(L: Ledger):
    src, ssrc, rsrc = ("results/verification/v14/bench/T5_v3.csv", "results/verification/v14/bench/summary.json",
                       "results/verification/v14/bench/runs.csv")
    t5 = read_csv(src)
    sm = read_json(ssrc)
    runs = read_csv(rsrc)
    rows = []
    for r in t5:
        m = r["id"]
        pm = sm["per_method"][m]
        vd = pm["verdicts"]
        # recount from runs.csv
        rr = [x for x in runs if x["set"] == "primary" and x["method"] == m]
        rc = collections.Counter(x["cert_verdict"] for x in rr)
        if (rc["certified"], rc["undetermined"], rc["refuted"], rc["not_certified_search_tier_miss"]) != (
                int(r["certified"]), vd.get("undetermined", 0), vd.get("refuted", 0),
                vd.get("not_certified_search_tier_miss", 0)):
            L.conflict("T5", f"{m} verdict counts", {"runs.csv": dict(rc), "summary.json/T5_v3.csv": dict(vd)},
                       script=S)
        ci = json.loads(r["rate_ci"])
        L.add("T5", f"{m}.certified", int(r["certified"]), src, "certified", script=S)
        L.add("T5", f"{m}.rate_ci", f"{ci[0]:.2f}-{ci[1]:.2f}", src, "rate_ci", script=S)
        for k in ("undetermined", "refuted", "not_certified_search_tier_miss"):
            L.add("T5", f"{m}.{k}", vd.get(k, 0), ssrc, f"per_method.{m}.verdicts.{k}", script=S)
        for k in ("evals_spent_mean", "evals_to_final_mean", "cost_C_mean", "median_certified_slack", "cert_calls",
                  "search_tier_found_nominal"):
            L.add("T5", f"{m}.{k}", fnum(r[k]), src, k, script=S)
        p = r["mcnemar_vs_M4_p"]
        ptxt = "-" if not p else f"{float(p):.3g} / {float(r['holm_p']):.3g}"
        ctxt = "-" if not p else f"{float(r['cost_signflip_p']):.3g} / {float(r['cost_holm_p']):.3g}"
        if p:
            for k in ("mcnemar_vs_M4_p", "holm_p", "cost_signflip_p", "cost_holm_p"):
                L.add("T5", f"{m}.{k}", float(r[k]), src, k, script=S)
        rows.append([f"{m} {r['method']}", f"{r['certified']}/{r['n']}", f"{ci[0]:.2f}-{ci[1]:.2f}",
                     str(vd.get("undetermined", 0)), str(vd.get("refuted", 0)),
                     str(vd.get("not_certified_search_tier_miss", 0)), f"{float(r['evals_spent_mean']):.0f}",
                     f"{float(r['evals_to_final_mean']):.1f}", f"{float(r['cost_C_mean']):.2f}",
                     f"{float(r['median_certified_slack']):.3f}", r["cert_calls"], ptxt, ctxt])
    vd = sm["verdict"]
    L.add("T5", "verdict", vd["verdict"], ssrc, "verdict.verdict", script=S)
    L.add("T5", "budget", sm["budget"], ssrc, "budget", script=S)
    L.add("T5", "n_targets", sm["n_primary_targets"], ssrc, "n_primary_targets", script=S)
    L.add("T5", "unique_certificates", sm["unique_certificates"], ssrc, "unique_certificates", script=S)
    # certificate populations (final asset audit, finding 10): requests by the primary methods, unique certificates per
    # set (a certificate is keyed by design hash and target; identical requests shared one certificate)
    att = [x for x in runs if x["certify_attempted"] == "True"]
    pop = {st: {(x["final_hash"], x["target_id"]) for x in att if x["set"] == st} for st in ("primary", "calibration")}
    n_req_primary = sum(x["set"] == "primary" for x in att)
    assert not (pop["primary"] & pop["calibration"])
    if len(pop["primary"]) + len(pop["calibration"]) != sm["unique_certificates"]:
        L.conflict("T5", "unique certificates", {f"{rsrc} (recount)": len(pop["primary"]) + len(pop["calibration"]),
                                                 ssrc: sm["unique_certificates"]}, script=S)
    L.add("T5", "certificates.primary_requested", n_req_primary, rsrc,
          "rows with set == primary and certify_attempted == True (methods M1-M6, before sharing)", status="derived",
          script=S)
    L.add("T5", "certificates.primary_unique", len(pop["primary"]), rsrc,
          "distinct (final_hash, target_id) among attempted primary rows", status="derived", script=S)
    L.add("T5", "certificates.calibration_unique", len(pop["calibration"]), rsrc,
          "distinct (final_hash, target_id) among attempted calibration rows", status="derived", script=S)
    cal = collections.defaultdict(list)
    for c in sm["calibration_targets"]:
        cal[c["method"]].append(c)
    caltxt = []
    for m, cs in sorted(cal.items()):
        k = sum(c["certified"] for c in cs)
        L.add("T5", f"calibration.{m}.certified", f"{k}/{len(cs)}", ssrc, f"calibration_targets method {m}",
              status="derived", script=S)
        caltxt.append(f"{m} {k}/{len(cs)}")
    notes = [f"{sm['n_primary_targets']} held-out targets from witnessed feasible confirmatory E4 specifications "
             f"(atlas-derived witnesses), one seed per method, budget {sm['budget']} search-tier evaluations; a "
             "certificate only for each method's final design (nominal search-tier slack > 0). Certificate "
             f"populations: the primary methods M1-M6 requested {n_req_primary} certifications; identical (design, "
             f"target) requests shared one certificate, giving {len(pop['primary'])} unique primary certificates, plus "
             f"{len(pop['calibration'])} unique calibration certificates: {sm['unique_certificates']} unique "
             "certificates in all.",
             "C = evaluations to the final design for a certified success, 48 for a failure (atlas-only spends 0). "
             "p: exact McNemar (certified success) and paired sign-flip (C) against M4, raw / Holm (Holm over M1-M3; "
             "over M5-M6 for the ablations).",
             f"Registered verdict: {vd['verdict'].upper()} (criterion A {vd['criterion_A']}, criterion B "
             f"{vd['criterion_B']}). Wording: on 20 held-out, atlas-derived feasible targets, BO certified 14 designs, "
             "atlas-only 12, Sobol 6 and DE 9; BO showed no clear advantage under the registered rule. Its penalized "
             "final-candidate-index cost was lower than Sobol's; the DE comparison was nonsignificant after Holm "
             "adjustment. No equivalence claim.",
             "Calibration targets at ν 0.342 / 0.39 (not in any test): " + ", ".join(caltxt) + " certified."]
    return write_table("T5_search_benchmark", "Search benchmark V3 (held out, budget matched, no LLM)",
                       ["Method", "Certified", "95 % CI", "Undet.", "Refuted", "Search-tier miss", "Evals",
                        "Evals to final", "Mean C", "Median cert. slack", "Cert. calls", "p success (raw/Holm)",
                        "p cost (raw/Holm)"], rows, notes, colspec="l" + "r" * 12, label="tab:search")


# ============================================================================================================ T6
def t6_performance(L: Ledger):
    src = "results/verification/v4/T6_v4.csv"
    t6 = read_csv(src)
    rows = []
    cur = None
    names = {"throughput": "Search-tier throughput (cells/s)", "latency": "Tool latency, fresh process (s)",
             "latency (agent sessions)": "Tool latency in E4 agent sessions, older code (s)",
             "certificate": "Certificate time (s)", "workflow": "Workflow time, spec to certified design (s)",
             "scaling": "Scaling with resolution, cube_bars c 0.6 w 0.2 (s)", "threads": "MKL threads (s)"}
    for r in t6:
        if r["block"] != cur:
            cur = r["block"]
            rows.append("## " + names.get(cur, cur))
        rows.append([r["metric"], r["value"], r["unit"], r["conditions"]])
        L.add("T6", f"{r['block']}|{r['metric']}", r["value"], src, f"value ({r['source']})", unit=r["unit"],
              script=S)
    notes = ["RTX 4090 + i9-13900KF, Windows 11; one machine, one run per point (V4 NOTES caveats). Throughput, "
             "response latency, certificate time and workflow time are separate metrics. Values: median [range] "
             "unless stated; workflow medians are over certified successes.",
             "E4 rows used the frozen pre-B3 code (checker f2e482d81382b400); all other rows the checker at the V4 "
             "run, f141e46cb67a78db. Batching gives no throughput gain."]
    return write_table("T6_performance", "Performance V4: throughput, latency, certificate and workflow time, scaling",
                       ["Metric", "Value", "Unit", "Conditions"], rows, notes,
                       colspec="p{5.2cm}p{3.0cm}lp{6.6cm}", label="tab:performance")


# ============================================================================================================ T8
def t8_agent(L: Ledger):
    src, ssrc = "results/bench/e4/analysis_A2.json", "results/bench/e4/scores.json"
    a = read_json(src)
    assert a["amendment"] == "A2"
    p = a["primary_C_minus_B_correct"]
    rows = ["## Primary (H1): correct on decided specifications, C − B"]
    rows.append(["correct, C − B", str(p["n_specs"]), f"{p['mean_a']:.3f}", f"{p['mean_b']:.3f}",
                 f"{p['diff']:+.3f}", f"[{p['ci95'][0]:.3f}, {p['ci95'][1]:.3f}]",
                 f"{p['specs_a_better']} / {p['specs_b_better']}", "< 1e-4 (test floor)"])
    for k in ("n_specs", "mean_a", "mean_b", "diff", "specs_a_better", "specs_b_better", "p"):
        L.add("T8", f"primary.{k}", p[k], src, f"primary_C_minus_B_correct.{k}", script=S)
    L.add("T8", "primary.ci95", f"[{p['ci95'][0]:.3f}, {p['ci95'][1]:.3f}]", src, "primary_C_minus_B_correct.ci95",
          script=S)
    rows.append("## Secondary (Holm over 5)")
    lab = {"unsupported_release_B_minus_C": "unsupported releases, B − C",
           "false_refusal_B_minus_C": "false refusals (witnessed), B − C",
           "overclaim_B_minus_C": "overclaims (unresolved), B − C", "correct_C_minus_D": "correct, C − D",
           "resolved_ambiguous_C_minus_B": "ambiguity resolved, C − B"}
    for k, s in a["secondary"].items():
        rows.append([lab.get(k, k), str(s["n_specs"]), f"{s['mean_a']:.3f}", f"{s['mean_b']:.3f}",
                     f"{s['diff']:+.3f}", f"[{s['ci95'][0]:.3f}, {s['ci95'][1]:.3f}]",
                     f"{s['specs_a_better']} / {s['specs_b_better']}", f"{s['p_holm']:.2g}"])
        for kk in ("n_specs", "mean_a", "mean_b", "diff", "p_holm"):
            L.add("T8", f"{k}.{kk}", s[kk], src, f"secondary.{k}.{kk}", script=S)
        L.add("T8", f"{k}.ci95", f"[{s['ci95'][0]:.3f}, {s['ci95'][1]:.3f}]", src, f"secondary.{k}.ci95", script=S)
    sc = read_json(ssrc)
    conf = [x for x in sc if x["partition"] == "confirmatory"]
    oc = collections.Counter((x["arm"], x["outcome"]) for x in conf)
    order = ["success", "correct_refusal", "false_refusal", "abstention", "overclaim", "no_answer"]
    labels = {"success": "success (released, certificate holds)", "correct_refusal": "correct refusal (proven)",
              "false_refusal": "false refusal (witnessed feasible)", "abstention": "abstention (unresolved)",
              "overclaim": "overclaim", "no_answer": "no answer", "unsupported_release": "unsupported release"}
    rows2 = []
    for o in order:
        vals = [oc.get((arm, o), 0) for arm in "DBC"]
        rows2.append([labels[o]] + [str(v) for v in vals])
        for arm, v in zip("DBC", vals):
            L.add("T8", f"outcome.{arm}.{o}", v, ssrc, f"count partition=confirmatory, arm={arm}, outcome={o}",
                  status="derived", script=S)
    tot = [sum(oc.get((arm, o), 0) for o in order) for arm in "DBC"]
    extra = set(o for (_, o) in oc) - set(order)
    assert not extra, extra
    rows2.append(["briefs"] + [str(t) for t in tot])
    smsrc = "results/bench/e4/summary.json"
    sm = read_json(smsrc)
    ur = [sm[f"codex/{arm}/1"]["confirmatory"]["unsupported_releases"] for arm in "DBC"]
    rel_ = [sm[f"codex/{arm}/1"]["confirmatory"]["releases"] for arm in "DBC"]
    rows2.append(["releases (all)"] + [str(x) for x in rel_])
    rows2.append(["unsupported releases (refuted + unverified)"] + [str(x) for x in ur])
    for arm, x, y in zip("DBC", ur, rel_):
        L.add("T8", f"outcome.{arm}.unsupported_releases", x, smsrc, f"codex/{arm}/1.confirmatory.unsupported_releases",
              script=S)
        L.add("T8", f"outcome.{arm}.releases", y, smsrc, f"codex/{arm}/1.confirmatory.releases", script=S)
    # cross-check against RESULT_A2.md
    txt = read_text("results/bench/e4/RESULT_A2.md")
    for o, lbl in (("success", "success"), ("false_refusal", "false refusal"), ("abstention", "abstention")):
        m = re.search(rf"\| {lbl}[^|]*\| (\d+) \| (\d+) \| (\d+) \|", txt)
        if m and tuple(int(x) for x in m.groups()) != tuple(oc.get((arm, o), 0) for arm in "DBC"):
            L.conflict("T8", f"outcome {o}", {"RESULT_A2.md": m.groups(),
                                              "scores.json": [oc.get((arm, o), 0) for arm in "DBC"]}, script=S)
    meta = a["scores_meta"]
    run0 = read_json("results/bench/e4/jobs/codex-C-r1-M13/run.json")
    jm = read_json("results/bench/e4/jobs.json")["meta"]
    b1 = read_json("results/software/b1_refusal_audit.json")
    acc, rej = b1["counts"]["e4 profile C accepted"], b1["counts"]["e4 profile C REJECTED"]
    L.add("T8", "b1.e4_C_refusals_rejected", f"{rej} of {acc + rej}", "results/software/b1_refusal_audit.json",
          "counts e4 profile C REJECTED / (accepted + REJECTED)", status="derived", script=S)
    n_all = a["secondary"]["unsupported_release_B_minus_C"]["n_specs"]
    notes = [f"E4, amendment A2: Codex {run0['model']} ({run0['effort']}), repeat 1, confirmatory partition, "
             f"{tot[0]} briefs per arm; units are specifications ({p['n_specs']} decided for H1, {n_all} in all). "
             f"Scored {meta['created']} with the "
             f"frozen checker {meta['checker']} (scorer {meta['scoring']}). Arms: D = LLM alone; B = spec, search "
             "and evaluate tools + submit; C = B + check_bounds + certify (a bundled intervention).",
             "Tests: two-sided paired sign-flip permutation (1e5 draws), cluster bootstrap CI over specifications. "
             "Phases 2-5 were cut by amendments A1/A2 before any confirmatory outcome was scored; repeat-level "
             "reliability is not estimable.",
             f"Scope: the frozen E4 implementation (code {jm['code']}). The B1 refusal-evidence rule added later "
             f"would have rejected {rej} of {acc + rej} profile-C refusals "
             f"({', '.join(Path(c['session']).name for c in b1['changed'])}), so E4 does not measure final-release "
             "refusal behaviour. The gain chiefly reflects fewer false refusals; unsupported releases were 0 in "
             "every arm. Certificates' own causal contribution is not isolated."]
    p1 = write_table("T8_agent_evaluation", "Agent evaluation E4 (amended confirmatory analysis, amendment A2)",
                     ["Test", "Specs", "a", "b", "Difference", "95 % CI", "Specs a / b better", "p (Holm)"],
                     rows, notes, colspec="lrrrrrrr", label="tab:agent")
    p2 = write_table("T8b_agent_outcomes", "Agent evaluation E4 (amendment A2): outcome counts per arm, 78 "
                     "confirmatory briefs each", ["Outcome", "D", "B", "C"], rows2,
                     [f"Counted from `{ssrc}` (partition confirmatory); equal to RESULT_A2.md."], colspec="lrrr",
                     label="tab:agent-outcomes")
    return p1 + p2


# ============================================================================================================ T11
def t11_bounds(L: Ledger):
    f = "amm/bounds.py"
    txt = read_text(f)
    calls = [(m.group(1), m.group(2)) for m in re.finditer(r'v\("(\w+)", f?"([^"]+)"', txt)]
    hs_ln = find_line(f, r'bound="HS"')
    bounds = [
        ("V1", "Voigt: C* ≤ φ C_s as quadratic forms", "E100_min > φ_max E_s; G_min (C44) > φ_max μ_s; "
         "bulk_min > φ_max K_s", "any geometry, any symmetry", "PROVEN_INFEASIBLE",
         "two-phase solid + void; solid isotropic (E_s, ν_s); φ = solid fraction; φ_max = density_max (1 if absent)",
         r'v\("V1"'),
        ("S1", "Stability: C* positive definite", "ν100_min ≥ 1/2 or ν100_max ≤ −1", "cubic (or isotropic) "
         "effective symmetry", "PROVEN_INFEASIBLE (scoped to the cubic design space)",
         "cubic: C11 > |C12|, C11 + 2C12 > 0, C44 > 0 confine ν100 to (−1, 1/2)", r'v\("S1"'),
        ("P1", "Positivity and consistency", "a minimum above its maximum (density, E100, ν100); solid fraction "
         "outside (0, 1]; E100_max ≤ 0", "any", "PROVEN_INFEASIBLE", "moduli of a load-bearing cell are positive",
         r'v\("P1"'),
        ("W1", "Complete gap cannot contain f = 0", "f_lo ≤ 0, or f_hi ≤ f_lo", "any", "PROVEN_INFEASIBLE",
         "three acoustic branches start at 0 at Γ and are continuous", r'v\("W1"'),
        ("HS", "Hashin–Shtrikman upper bounds (porous)", "bulk_min > K_HS; G_min > μ_HS; E100_min > E_HS(φ_max)",
         "isotropic composites", "advisory for cubic requests; PROVEN only when isotropy is requested",
         "rigorous for isotropic composites only", r'bound="HS"'),
        ("-", "Missing information", "request cannot be stated in solver units (e.g. Hz without a cell size)", "-",
         "UNDERSPECIFIED (ask, never guess)", "", r"UNDERSPECIFIED, missing"),
    ]
    rows = []
    for bid, name, trig, scope, eff, ass, pat in bounds:
        ln = find_line(f, pat)
        assert ln, (bid, pat)
        n_calls = sum(1 for c in calls if c[0] == bid)
        rows.append([bid, name, trig, scope, eff, ass, f"{f}:{ln}"])
        L.add("T11", f"{bid}.source_line", f"{f}:{ln}", f, f"first line matching {pat} (sha256 {sha16(f)})",
              script=S, note=f"{n_calls} violation call(s) in source" if bid not in ("HS", "-") else "")
    # HS audit (advisory margin)
    hsrc = "results/verification/hs_audit.json"
    hs = read_json(hsrc)
    notes = ["Checked before any search (`check_bounds`); a violated rigorous bound gives the outcome 'proven "
             "infeasible' with the bound named. `ratio_to_bound` = target / bound is reported as a margin.",
             "Bounds are rigorous for the stated scope only; outside the declared cubic design space S1 does not apply.",
             "Statements of the bounds and references (Hill 1952; Milton 2002, ch. 13) are in the module docstring of "
             "`amm/bounds.py`."]
    mx = _hs_max(hs)
    if mx:
        for k, v in mx.items():
            L.add("T11", f"hs_audit.max_{k}", round(v, 3), hsrc, f"max {k} over cells", status="derived", script=S)
        ncell = len(hs["rows"])
        L.add("T11", "hs_audit.cells", ncell, hsrc, "len(rows)", status="derived", script=S)
        m_ = re.search(r"Hashin.Shtrikman audit\*\* \(`scripts/experiments/hs_audit.py`, (\d+) cubic cells",
                       read_text("results/verification/NOTES.md"))
        if m_ and int(m_.group(1)) != ncell:
            L.conflict("T11", "HS audit cell count", {"results/verification/NOTES.md": f"{m_.group(1)} cubic cells",
                                                      hsrc: f"{ncell} rows"}, script=S,
                       note="table uses the row count of hs_audit.json")
        res = re.search(r"design_cell\(s, (\d+)\)", read_text("scripts/experiments/hs_audit.py"))
        notes.append(f"HS audit, {ncell} cubic cells at n = {res.group(1) if res else '?'} "
                     "(`results/verification/hs_audit.json`, `scripts/experiments/hs_audit.py`): largest ratios "
                     + ", ".join(f"{k} {v:.3f}" for k, v in mx.items()) + "; no cell exceeds the isotropic HS bounds, "
                     "so HS stays advisory for cubic requests.")
    return write_table("T11_bounds", "Bounds used for refusal, with their assumptions",
                       ["ID", "Bound", "Refuses when", "Rigorous for", "Effect", "Assumptions", "Source"], rows,
                       notes, colspec="lp{2.6cm}p{3.4cm}p{2.0cm}p{2.4cm}p{3.4cm}p{1.6cm}", label="tab:bounds")


def _short_json(d) -> str:
    """{'evaluate': {'args': ['bands']}} -> 'evaluate: args bands' (compact, for table notes)."""
    out = []
    for tool, v in d.items():
        if isinstance(v, dict):
            out.append(f"{tool}: " + ", ".join(f"{k} {' '.join(map(str, x))}" for k, x in v.items()))
        else:
            out.append(f"{tool}: " + " ".join(map(str, v)))
    return "; ".join(out)


def _literal(expr: str):
    """ast.literal_eval that also accepts dict(k=v, ...) calls (how e4.py writes PHASES and AMENDMENTS)."""
    import ast

    def conv(n):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "dict" and not n.args:
            return {kw.arg: conv(kw.value) for kw in n.keywords}
        if isinstance(n, ast.Dict):
            return {conv(k): conv(v) for k, v in zip(n.keys, n.values)}
        if isinstance(n, ast.Tuple):
            return tuple(conv(e) for e in n.elts)
        if isinstance(n, ast.List):
            return [conv(e) for e in n.elts]
        return ast.literal_eval(n)
    return conv(ast.parse(expr, mode="eval").body)


def _hs_max(hs):
    """Largest ratio to the HS bound per quantity in hs_audit.json (structure read defensively)."""
    rows = hs.get("rows") if isinstance(hs, dict) else hs
    if not isinstance(rows, list):
        return {}
    keys = {}
    for r in rows:
        for k, v in r.items():
            if isinstance(v, (int, float)) and "_over_" in k:
                keys[k] = max(keys.get(k, -1e9), float(v))
    return keys


# ============================================================================================================ T13
def t13_jobs(L: Ledger):
    jsrc = "results/bench/e4/jobs.json"
    J = read_json(jsrc)
    jobs, meta = J["jobs"], J["meta"]
    e4src = "scripts/bench/e4.py"
    txt = read_text(e4src)
    m = re.search(r"^PHASES = (\{.*?\})\nPRIMARY", txt, re.S | re.M)
    PH = _literal(m.group(1))
    assert all(set(v) == {"provider", "arms", "reps", "partition"} for v in PH.values())
    m2 = re.search(r"^AMENDMENTS = (\{.*?\})\n# provider", txt, re.S | re.M)
    AM = _literal(m2.group(1))
    ph_ln = find_line(e4src, r"^PHASES = ")
    am_ln = find_line(e4src, r"^AMENDMENTS = ")

    def in_phase(j, ph):
        return (j["provider"] == ph["provider"] and j["arm"] in ph["arms"] and j["rep"] in ph["reps"]
                and (ph["partition"] is None or j["partition"] == ph["partition"]))

    runs = {}
    for f in glob.glob(str(ROOT / "results/bench/e4/jobs/*/run.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        runs[d["job"]] = d
    attempts = [Path(p).name for p in glob.glob(str(ROOT / "results/bench/e4/attempts/*"))]
    q = read_json("results/bench/e4/amendments/quota_check.json")
    sc = read_json("results/bench/e4/scores.json")
    scored = {x["job"] for x in sc}
    a1 = read_json("results/bench/e4/amendments/A1.json")[0]
    desc = {1: "Codex repeat 1, confirmatory (D, B, C)", 2: "Codex repeats 2-3, confirmatory",
            3: "arm O (no LLM, oracle spec), all partitions", 4: "Codex repeats 1-3, development",
            5: "Claude Code, repeat 1, all partitions"}
    rows = []
    total = 0
    for k in sorted(PH):
        js = [j for j in jobs if in_phase(j, PH[k])]
        total += len(js)
        ran = [j for j in js if j["job"] in runs]
        done = sum(runs[j["job"]]["status"] == "done" for j in ran)
        hv = collections.Counter((runs[j["job"]].get("amendment") or "plan-time",
                                  runs[j["job"]].get("harness") or "(none recorded)") for j in ran)
        cut = [a for a, v in AM.items() if k in v["cut_phases"]]
        first_cut = cut[0] if cut else ""
        status = f"cut by {first_cut}" if cut and not ran else ("run" if ran else "not run")
        hvt = "; ".join(f"{n} at plan time (no harness hash recorded)" if h == "(none recorded)" else
                        f"{n} under {a} (harness {h})" for (a, h), n in sorted(hv.items())) or "-"
        if k == min(PH):
            pre_a1 = sum(n for (a, h), n in hv.items() if h == "(none recorded)")
            ph1_n = len(js)
            L.add("T13", "phase1.before_A1", pre_a1, "results/bench/e4/jobs/*/run.json",
                  "phase-1 jobs without a harness hash (run before A1)", status="derived", script=S)
        nsc = sum(j["job"] in scored for j in js)
        rows.append([str(k), desc[k], str(len(js)), status, str(len(ran)), str(done), str(nsc), hvt])
        L.add("T13", f"phase{k}.jobs", len(js), jsrc, f"jobs matching e4.PHASES[{k}] ({e4src}:{ph_ln})",
              status="derived", script=S)
        L.add("T13", f"phase{k}.ran", len(ran), "results/bench/e4/jobs/*/run.json", "jobs with run.json",
              status="derived", script=S)
        L.add("T13", f"phase{k}.done", done, "results/bench/e4/jobs/*/run.json", "status == done", status="derived",
              script=S)
        L.add("T13", f"phase{k}.scored", nsc, "results/bench/e4/scores.json", "jobs scored", status="derived",
              script=S)
        L.add("T13", f"phase{k}.status", status, e4src, f"AMENDMENTS cut_phases ({e4src}:{am_ln})",
              status="derived", script=S)
        for (a, h), n in hv.items():
            L.add("T13", f"phase{k}.harness.{a}.{h}", n, "results/bench/e4/jobs/*/run.json",
                  "count (amendment, harness)", status="derived", script=S)
    if total != meta["n_jobs"]:
        L.conflict("T13", "manifest job count", {"jobs.json meta.n_jobs": meta["n_jobs"],
                                                 "sum over e4.PHASES": total}, script=S)
    L.add("T13", "manifest.n_jobs", meta["n_jobs"], jsrc, "meta.n_jobs", script=S)
    L.add("T13", "manifest.created", meta["created"], jsrc, "meta.created", script=S)
    L.add("T13", "attempts.archived", len(attempts), "results/bench/e4/attempts/", "directory count",
          status="derived", script=S)
    L.add("T13", "quota.checked", q["checked"], "results/bench/e4/amendments/quota_check.json", "checked", script=S)
    L.add("T13", "quota.events", len(q["quota_events"]), "results/bench/e4/amendments/quota_check.json",
          "len(quota_events)", status="derived", script=S)
    idrows = []
    for key in ("code", "checker", "full_source", "briefs", "data", "prereg"):
        idrows.append([key, a1["plan_identity"][key], a1["amended_identity"][key],
                       "same" if a1["plan_identity"][key] == a1["amended_identity"][key] else "changed"])
        L.add("T13", f"identity.{key}.plan", a1["plan_identity"][key], "results/bench/e4/amendments/A1.json",
              f"plan_identity.{key}", script=S)
        L.add("T13", f"identity.{key}.A1", a1["amended_identity"][key], "results/bench/e4/amendments/A1.json",
              f"amended_identity.{key}", script=S)
    am_txt = "; ".join(f"{a} ({v['date']}): run phases {list(v['run_phases'])}, cut {list(v['cut_phases'])}"
                       for a, v in AM.items())
    notes = [f"Manifest `{jsrc}` written {meta['created']} ({meta['n_jobs']} jobs, seed {meta['seed']}); phases "
             f"from `e4.PHASES` ({e4src}:{ph_ln}); amendments from `e4.AMENDMENTS` ({e4src}:{am_ln}) and "
             "plan/E4_PREREG.md section 9: " + am_txt + ".",
             f"A1 and A2 were decided before any confirmatory outcome was scored or read (A1: {pre_a1} of {ph1_n} "
             f"phase-1 jobs done, reason overlap and LLM cost; A2: after phase 1 finished, compute cap). A1 allows "
             f"changes only "
             f"in {', '.join(a1['allowed_changes'])}; changed: {', '.join(a1['changed_files'])}. A2 has no record "
             "under amendments/ (it is logged in e4.py and the pre-registration only).",
             f"Archived interrupted attempts: {len(attempts)} ({', '.join(attempts)}), rerun as the same manifest job. "
             f"Quota check: {q['checked']} jobs checked, {len(q['quota_events'])} usage-limit events.",
             "Harness versions: 'plan time (no harness hash recorded)' marks the jobs run before A1 under the "
             f"plan-time identity (full source {a1['plan_identity']['full_source']})."]
    p1 = write_table("T13_job_accounting", "E4 job accounting: which jobs ran, under which harness, which were cut",
                     ["Phase", "Content", "Jobs", "Status", "Ran", "Done", "Scored", "Harness versions"], rows,
                     notes, colspec="rp{4.0cm}rlrrrp{5.6cm}", label="tab:jobs")
    p2 = write_table("T13b_identity", "E4 frozen identity: plan time versus amendment A1",
                     ["Component", "Plan time", "Under A1", "Status"], idrows,
                     ["Source: results/bench/e4/amendments/A1.json. Only the harness (scripts/bench/e4.py) and the "
                      "pre-registration differ; tool code, checker, briefs and data are unchanged."],
                     colspec="llll", label="tab:identity")
    return p1 + p2


ALL = [t2_contract, t3_checks, t4_verification, t5_search, t6_performance, t8_agent, t11_bounds, t13_jobs]
