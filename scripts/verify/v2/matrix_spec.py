"""V2 capability and interface acceptance matrix: the scenarios and their PRE-DEFINED expectations.

Written before any row was run (2026-11-08). Every checked step of a scenario becomes one matrix row per interface
it runs on: (scenario, check id, capability, interface, expected, observed, pass/fail, session log).

Expectations come from the documented contract (docs/, amm.tools docstrings), the rigorous bounds of amm/bounds.py
(numbers derived by hand below), the material table of amm/units.py, and facts read from the search-atlas files
before the run (results/atlas/atlas_nu*.jsonl: density range 0.014-0.724; tpms complete gaps start at f* >= 0.41;
max f_hi 1.85; schwarz_p network density 0.06-0.16 is invalid at the search tier, i.e. does not percolate) and from
the recorded E4 certificates of the designs reused here (results/bench/e4/jobs/codex-C-r1-M03, -G05) and tutorial 02.
No tool call was made to set an expectation.

Predicates (on the normalized call output {ok, seq, result | error}):
  ("ok", bool)                 the call succeeded / was refused
  ("eq", path, v)              value at path equals v          ("approx", path, v, rtol)
  ("in", path, [..])           value at path is one of         ("has", path, text)  str(value) contains text (case-insens.)
  ("all_in", path[*], [..])    every value is one of           ("len", path, n) / ("len_ge", path, n)
  ("true", path) / ("false", path) / ("none", path) / ("notnone", path)
Paths: dotted, with [i] and [*]; "$LABEL.path" in a value refers to an earlier labelled step of the same session.
"""
from __future__ import annotations

import math

# ---- materials (amm/units.py) and the hand conversions used in the expectations ---------------------------------
MAT = {"PA12": (1.70e9, 0.39, 1010.0), "Ti6Al4V": (113.8e9, 0.342, 4430.0), "316L": (193.0e9, 0.30, 8000.0),
       "AlSi10Mg": (70.0e9, 0.33, 2670.0)}


def c_t(E, nu, rho):
    return math.sqrt(E / (2 * (1 + nu)) / rho)


def fstar(f_hz, a_m, mat):
    return f_hz * a_m / c_t(*MAT[mat])


# ---- designs ---------------------------------------------------------------------------------------------------
D_SL = {"kind": "sphere_ligaments", "params": {"c": 0.12, "w": 0.181739}}      # tutorial 02, PA12 certified (20 s)
D_SL_OTHER = {"kind": "sphere_ligaments", "params": {"c": 0.125, "w": 0.181739}}  # a design change
D_BCC = {"kind": "bcc", "params": {"r": 0.08, "R": 0.0}}                         # tutorial 03 (screening)
D_M03 = {"kind": "sphere_ligaments", "params": {"c": 0.289, "w": 0.124}}         # E4 M03: combined, certified (150 s)
D_G05 = {"kind": "sphere_ligaments", "params": {"c": 0.326957, "w": 0.06}}       # E4 G05: gap, undetermined (122 s)
D_GYR = {"kind": "gyroid", "params": {"density": 0.3, "mode": "sheet"}}
D_OCT = {"kind": "octet", "params": {"r": 0.06, "R": 0.0}}
D_CB = {"kind": "cube_bars", "params": {"c": 0.6, "w": 0.2}}
D_SP_LOW = [{"kind": "schwarz_p", "params": {"density": d, "mode": "network"}} for d in (0.06, 0.08, 0.10, 0.12)]
TPMS_KINDS = ["gyroid", "schwarz_p", "diamond", "iwp"]
STRUT_KINDS = ["sc", "bcc", "octet"]
RES_KINDS = ["cube_bars", "sphere_ligaments"]
OUTCOME_SET = ["certified_candidate", "refuted_candidate", "proven_infeasible", "not_found_in_families",
               "numerically_undetermined", "need_info"]

ALL4 = ("lib", "mcp", "gui", "cli")
LMG = ("lib", "mcp", "gui")


def st(tool, args=None, label=None, cap=None, check=None, expect=(), ifaces=None, note=""):
    """One step. With `check` (a short id) and `expect`, it is a matrix row."""
    return dict(tool=tool, args=args or {}, label=label, cap=cap, check=check, expect=list(expect), ifaces=ifaces,
                note=note)


def cli(argv, check, cap, expect, note=""):
    """A CLI-only step: `amm <argv>` with the scenario's accumulated spec appended (see drivers.CliDriver)."""
    return dict(tool="__cli__", argv=list(argv), check=check, cap=cap, expect=list(expect), ifaces=("cli",),
                note=note, label=None, args={})


def tgt(**kw):
    return dict(kw, clear=True)


S = []  # scenarios

# =================================================================================================================
# S01 target types: feasible and infeasible per type, combinations, contradictory / negative bounds (CPU only)
# Voigt limits at nu_s = 0.3 (316L): E <= phi E_s, mu_s = 1/2.6 = 0.3846, K_s = 1/(3*0.4) = 0.8333.
# =================================================================================================================
FEAS = ("in", "result.verdict", ["FEASIBLE"])
S.append(dict(id="S01_targets", profile="C", ifaces=ALL4, title="target types, feasible and infeasible (316L)", steps=[
    st("set_material", {"name": "316L"}),
    st("set_target", tgt(density_max=0.3)),
    st("check_bounds", cap="target: density (feasible)", check="density_feasible",
       expect=[("ok", True), FEAS, ("len", "result.violated", 0)]),
    st("set_target", tgt(density_min=0.9)),
    st("check_bounds", cap="target: density (infeasible: above every family)", check="density_infeasible",
       expect=[("ok", True), ("eq", "result.verdict", "NOT_FOUND_IN_FAMILIES"), ("len", "result.violated", 0)],
       note="atlas density range 0.014-0.724; no rigorous bound below 1"),
    st("set_target", tgt(density_max=0.2, E100_min={"value": 3.86, "unit": "GPa"})),
    st("check_bounds", cap="target: E100 in GPa (feasible) + density", check="E100_feasible",
       expect=[("ok", True), FEAS, ("approx", "result.normalized_targets.E100_min", 0.02, 1e-12)],
       note="3.86 GPa / 193 GPa = 0.02 E_s"),
    st("set_target", tgt(density_max=0.2, E100_min={"value": 0.02, "unit": "E_s"})),
    st("check_bounds", cap="units: normalized E_s equals the GPa form", check="E100_Es_equals_GPa",
       expect=[("ok", True), FEAS, ("approx", "result.normalized_targets.E100_min", 0.02, 1e-15)]),
    st("set_target", tgt(density_max=0.2, E100_min={"value": 96.5, "unit": "GPa"})),
    st("check_bounds", cap="target: E100 (infeasible, Voigt)", check="E100_infeasible",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "V1")],
       note="0.5 E_s > 0.2 E_s"),
    st("set_target", tgt(density_max=0.3, G_min={"value": 0.01, "unit": "E_s"})),
    st("check_bounds", cap="target: G (feasible)", check="G_feasible", expect=[("ok", True), FEAS]),
    st("set_target", tgt(density_max=0.3, G_min={"value": 0.2, "unit": "E_s"})),
    st("check_bounds", cap="target: G (infeasible, Voigt)", check="G_infeasible",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "V1")],
       note="0.2 > 0.3 * 0.3846 = 0.115"),
    st("set_target", tgt(density_max=0.3, bulk_min={"value": 0.03, "unit": "E_s"})),
    st("check_bounds", cap="target: bulk (feasible)", check="bulk_feasible", expect=[("ok", True), FEAS]),
    st("set_target", tgt(density_max=0.3, bulk_min={"value": 0.5, "unit": "E_s"})),
    st("check_bounds", cap="target: bulk (infeasible, Voigt)", check="bulk_infeasible",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "V1")],
       note="0.5 > 0.3 * 0.8333 = 0.25"),
    st("set_target", tgt(nu100_max=0.1)),
    st("check_bounds", cap="target: nu100 (feasible)", check="nu100_feasible", expect=[("ok", True), FEAS],
       note="resonator nu100 0.007-0.15 in the atlas"),
    st("set_target", tgt(nu100_min=0.6)),
    st("check_bounds", cap="target: nu100 (infeasible, cubic stability)", check="nu100_infeasible",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "S1")]),
    st("set_target", tgt(gap={"f_lo": 0.3, "f_hi": 0.4, "unit": "f*"})),
    st("check_bounds", cap="target: complete gap (feasible)", check="gap_feasible", expect=[("ok", True), FEAS]),
    st("set_target", tgt(gap={"f_lo": 2.5, "f_hi": 3.0, "unit": "f*"})),
    st("check_bounds", cap="target: complete gap (infeasible: above every atlas gap)", check="gap_infeasible",
       expect=[("ok", True), ("eq", "result.verdict", "NOT_FOUND_IN_FAMILIES")], note="atlas max f_hi 1.85"),
    st("set_target", {"gap": {"f_lo": 0.0, "f_hi": 0.3, "unit": "f*"}}, cap="target: gap containing f = 0 (W1)",
       check="gap_contains_zero", expect=[("ok", False), ("has", "error", "cannot contain f = 0")]),
    st("set_target", tgt(density_max=0.12, E100_min={"value": 3.53, "unit": "GPa"},
                         gap={"f_lo": 0.2856092479018259, "f_hi": 0.4448281964447978, "unit": "f*"})),
    st("check_bounds", cap="combination: stiffness + gap + density (feasible)", check="combo_feasible",
       expect=[("ok", True), ("in", "result.verdict", ["FEASIBLE", "BORDERLINE"]), ("len", "result.violated", 0)],
       note="E4 M03 certified a design for this spec"),
    st("set_target", tgt(density_max=0.12, E100_min={"value": 0.5, "unit": "E_s"},
                         gap={"f_lo": 0.3, "f_hi": 0.4, "unit": "f*"})),
    st("check_bounds", cap="combination: stiffness + gap (infeasible, Voigt)", check="combo_infeasible",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE")]),
    st("set_target", tgt(density_min=0.5, density_max=0.3)),
    st("check_bounds", cap="invalid: contradictory bounds (density)", check="contradictory_density",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "P1")]),
    st("set_target", tgt(E100_min={"value": 0.05, "unit": "E_s"}, E100_max={"value": 0.01, "unit": "E_s"})),
    st("check_bounds", cap="invalid: contradictory bounds (E100)", check="contradictory_E100",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "P1")]),
    st("set_target", tgt(E100_max={"value": -1.0, "unit": "GPa"})),
    st("check_bounds", cap="invalid: negative bound (E100_max)", check="negative_E100_max",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "P1")]),
    st("set_target", tgt(density_max=-0.1)),
    st("check_bounds", cap="invalid: negative bound (density_max)", check="negative_density",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "P1")]),
    st("set_target", tgt(density_max=0.3, G_min={"value": -5.0, "unit": "GPa"}), label="negmin"),
    st("check_bounds", cap="invalid: negative minimum (G_min < 0)", check="negative_G_min",
       expect=[("refused_or", "P1")],
       note="bounds.py P1: 'requested minima must be positive where the quantity is a modulus'; expected: rejected "
            "at input or PROVEN_INFEASIBLE by P1, not a silent FEASIBLE"),
    st("set_target", {"porosity_max": 0.5}, cap="invalid: unknown target", check="unknown_target",
       expect=[("ok", False), ("has", "error", "porosity_max")]),
    st("set_target", {"zener_min": 0.9}, cap="invalid: Zener as a target (output only)", check="zener_target",
       expect=[("ok", False), ("has", "error", "zener"), ("has", "error", "output")],
       note="refused, and the message must say Zener is a computed output, not a target"),
    st("set_target", {"E100_min": {"value": 5, "unit": "GPA"}}, cap="invalid: unknown unit", check="unknown_unit",
       expect=[("ok", False), ("has", "error", "unit")]),
    st("set_target", {"density_max": "abc"}, cap="invalid: wrong value type", check="wrong_type",
       expect=[("ok", False), ("has", "error", "density_max")]),
]))

# =================================================================================================================
# S02 materials and physical units (CPU only)
# =================================================================================================================
mat_steps = []
for m in ("PA12", "Ti6Al4V", "316L", "AlSi10Mg"):
    E = MAT[m][0]
    mat_steps += [
        st("set_material", {"name": m}, cap=f"material {m}", check=f"material_{m}",
           expect=[("ok", True), ("eq", "result.E_Pa", E), ("eq", "result.nu", MAT[m][1]),
                   ("eq", "result.atlas_available", m != "AlSi10Mg")]),
        st("set_target", tgt(E100_min={"value": 1.0, "unit": "GPa"}, G_min={"value": 50.0, "unit": "MPa"},
                             gap={"f_lo": 20.0, "f_hi": 30.0, "unit": "kHz"}),
           cap=f"units: GPa, MPa, kHz with cell size ({m})", check=f"units_{m}",
           expect=[("ok", True), ("approx", "result.normalized.E100_min", 1e9 / E, 1e-12),
                   ("approx", "result.normalized.G_min", 50e6 / E, 1e-12),
                   ("approx", "result.normalized.gap.f_lo", fstar(20e3, 0.01, m), 1e-12),
                   ("approx", "result.normalized.gap.f_hi", fstar(30e3, 0.01, m), 1e-12),
                   ("len", "result.cannot_normalize_yet", 0)]),
        st("check_bounds", cap=f"material {m}: bounds + atlas availability", check=f"bounds_{m}",
           expect=[("ok", True)] + ([("eq", "result.atlas.verdict", "UNAVAILABLE"),
                                     ("has", "result.atlas.note", "0.33")] if m == "AlSi10Mg" else
                                    [("notnone", "result.atlas.n_cells")])),
    ]
S.append(dict(id="S02_materials_units", profile="C", ifaces=ALL4, title="every material; GPa/MPa/kHz with a cell size",
              steps=[st("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"})] + mat_steps + [
    st("set_material", {"E_Pa": 2.0e9, "nu": 0.35, "rho_kg_m3": 1200.0}, cap="material: custom (E, nu, rho)",
       check="material_custom", expect=[("ok", True), ("eq", "result.nu", 0.35), ("eq", "result.atlas_available", False)]),
    st("set_material", {"E_Pa": 2.0e9, "nu": 0.6, "rho_kg_m3": 1200.0}, cap="invalid: custom material nu >= 0.5",
       check="material_bad_nu", expect=[("ok", False), ("has", "error", "nu < 0.5")]),
    st("set_material", {"name": "steel"}, cap="invalid: unknown material name", check="material_unknown",
       expect=[("ok", False), ("has", "error", "name")]),
    # mid-session material change: the same physical target, other material -> other normalized target and verdict
    st("set_material", {"name": "316L"}),
    st("set_target", tgt(E100_min={"value": 5.0, "unit": "GPa"})),
    st("check_bounds", cap="material change mid-session (before: 316L)", check="matchange_before",
       expect=[("ok", True), ("approx", "result.normalized_targets.E100_min", 5e9 / 193e9, 1e-12),
               ("len", "result.violated", 0)]),
    st("set_material", {"name": "PA12"}),
    st("check_bounds", cap="material change mid-session (after: PA12)", check="matchange_after",
       expect=[("ok", True), ("approx", "result.normalized_targets.E100_min", 5e9 / 1.7e9, 1e-12),
               ("eq", "result.verdict", "PROVEN_INFEASIBLE"), ("eq", "result.violated[0].bound", "V1")],
       note="5 GPa on PA12 is 2.94 E_s > phi E_s <= 1"),
]))

# Hz without a cell size; GPa without a material -> UNDERSPECIFIED / information needed
S.append(dict(id="S03_underspecified", profile="C", ifaces=ALL4, title="Hz without a cell size; GPa without material",
              steps=[
    st("set_target", tgt(E100_min={"value": 5.0, "unit": "GPa"}), cap="units: GPa without a material",
       check="gpa_no_material", expect=[("ok", True), ("has", "result.cannot_normalize_yet", "no material")]),
    st("check_bounds", cap="GPa without a material: check refused", check="gpa_no_material_check",
       expect=[("ok", False), ("has", "error", "no material")]),
    st("set_material", {"name": "PA12"}),
    st("set_target", tgt(gap={"f_lo": 1000.0, "f_hi": 2000.0, "unit": "Hz"}), cap="units: Hz without a cell size",
       check="hz_no_cell", expect=[("ok", True), ("has", "result.cannot_normalize_yet", "no cell size")]),
    st("check_bounds", cap="Hz without a cell size: check refused (nothing normalizable)", check="hz_no_cell_check",
       expect=[("ok", False), ("has", "error", "no cell size")]),
    st("set_target", {"density_max": 0.3}),
    st("check_bounds", cap="Hz without a cell size + a normalizable target: UNDERSPECIFIED", check="hz_partial_check",
       expect=[("ok", True), ("eq", "result.bounds_verdict", "UNDERSPECIFIED"),
               ("has", "result.cannot_normalize", "no cell size"), ("eq", "result.verdict", "UNDERSPECIFIED")],
       note="the top-level verdict must not present a FEASIBLE / NOT_FOUND verdict for a request that cannot be "
            "stated in solver units"),
    st("certify", {"design": D_SL}, cap="Hz without a cell size: certify refused", check="hz_no_cell_certify",
       expect=[("ok", False), ("has", "error", "cannot be normalized")], ifaces=("lib", "mcp", "gui", "cli")),
    st("submit", {"decision": "need_info", "note": "cell size missing"}, cap="outcome: need_info",
       check="need_info", expect=[("ok", True), ("eq", "result.outcome_card.outcome", "need_info")], ifaces=LMG),
]))

# =================================================================================================================
# S04 families: each restricted alone and all together (gap target f* [0.25, 0.35]; tpms gaps start at 0.41)
# =================================================================================================================
GAPT = tgt(gap={"f_lo": 0.25, "f_hi": 0.35, "unit": "f*"})
S.append(dict(id="S04_families", profile="C", ifaces=ALL4, title="families alone and together", steps=[
    st("set_material", {"name": "316L"}),
    st("set_target", GAPT),
    st("set_constraints", {"families": ["tpms"]}),
    st("check_bounds", cap="family restriction: tpms only (gap below every tpms gap)", check="fam_tpms_bounds",
       expect=[("ok", True), ("eq", "result.verdict", "NOT_FOUND_IN_FAMILIES"), ("in", "result.atlas.n_cells", [212, 224])]),
    st("atlas_suggest", {"top": 5}, cap="family restriction: tpms only (suggestions)", check="fam_tpms_suggest",
       expect=[("ok", True), ("all_in", "result.best[*].design.kind", TPMS_KINDS)]),
    st("set_constraints", {"families": ["struts"]}),
    st("check_bounds", cap="family restriction: struts only", check="fam_struts_bounds",
       expect=[("ok", True), ("in", "result.verdict", ["FEASIBLE", "BORDERLINE"]), ("eq", "result.atlas.n_cells", 1395)],
       note="8 struts atlas cells cover a wider gap nominally"),
    st("atlas_suggest", {"top": 5}, cap="family restriction: struts only (suggestions)", check="fam_struts_suggest",
       expect=[("ok", True), ("all_in", "result.best[*].design.kind", STRUT_KINDS)]),
    st("set_constraints", {"families": ["resonator"]}),
    st("check_bounds", cap="family restriction: resonators only", check="fam_res_bounds",
       expect=[("ok", True), ("eq", "result.verdict", "FEASIBLE"), ("eq", "result.atlas.n_cells", 1103)]),
    st("atlas_suggest", {"top": 5}, cap="family restriction: resonators only (suggestions)", check="fam_res_suggest",
       expect=[("ok", True), ("all_in", "result.best[*].design.kind", RES_KINDS)]),
    st("set_constraints", {"families": ["tpms", "struts", "resonator"]}),
    st("check_bounds", cap="families: all three", check="fam_all_bounds",
       expect=[("ok", True), ("eq", "result.verdict", "FEASIBLE"), ("in", "result.atlas.n_cells", [2710, 2722])]),
    st("evaluate", {"designs": [D_GYR, D_OCT, D_CB]}, cap="evaluate one design per family (C*, Zener output)",
       check="evaluate_families",
       expect=[("ok", True), ("len", "result.results", 3), ("eq", "result.tier", "search (not certified)"),
               ("len", "result.results[0].C", 6), ("notnone", "result.results[2].derived.zener"),
               ("all_in", "result.results[*].valid", [True])]),
    st("set_constraints", {"families": []}, cap="invalid: empty family list", check="fam_empty",
       expect=[("ok", False), ("has", "error", "must not be empty")]),
    st("set_constraints", {"families": ["lattice"]}, cap="invalid: unknown family", check="fam_unknown",
       expect=[("ok", False), ("has", "error", "families")]),
]))

# =================================================================================================================
# S05 invalid requests: designs, ranges, unknown tools (evaluate rejects before spending)
# =================================================================================================================
S.append(dict(id="S05_invalid", profile="C", ifaces=ALL4, title="invalid designs, ranges and tools", steps=[
    st("set_material", {"name": "316L"}),
    st("set_target", tgt(density_max=0.3)),
    st("evaluate", {"designs": [{"kind": "cube_bars", "params": {"c": 0.95, "w": 0.2}}]},
       cap="invalid: out-of-box parameter", check="out_of_box",
       expect=[("ok", False), ("has", "error", "outside the family box")]),
    st("evaluate", {"designs": [{"kind": "cube_bars", "params": {"c": 0.5, "w": 0.48}}]},
       cap="invalid: family validity rule", check="validity_rule",
       expect=[("ok", False), ("has", "error", "validity rule")]),
    st("evaluate", {"designs": [{"kind": "gyroid", "params": {"density": 0.3}}]}, cap="invalid: TPMS without mode",
       check="tpms_no_mode", expect=[("ok", False), ("has", "error", "mode")]),
    st("evaluate", {"designs": [{"kind": "honeycomb", "params": {"t": 0.1}}]}, cap="invalid: unknown kind",
       check="unknown_kind", expect=[("ok", False), ("has", "error", "kind")]),
    st("evaluate", {"designs": [D_BCC] * 17}, cap="invalid: more than 16 designs", check="too_many",
       expect=[("ok", False), ("has", "error", "1-16")]),
    st("atlas_suggest", {"top": 50}, cap="invalid: top out of range", check="top_range",
       expect=[("ok", False), ("has", "error", "1-10")]),
    st("set_constraints", {"cell_size": -5}, cap="invalid: negative cell size", check="neg_cell",
       expect=[("ok", False), ("has", "error", "positive")]),
    st("get_session", {}, label="gs", cap="rejections spend no budget", check="no_spend",
       expect=[("ok", True), ("eq", "result.budget_used.designs", 0)], ifaces=LMG),
    st("design_everything", {}, cap="invalid: unknown tool", check="unknown_tool",
       expect=[("ok", False), ("has", "error", "unknown tool")], ifaces=LMG),
    cli(["evaluate", "--design", "{bad json"], "malformed_json_cli", "invalid: malformed JSON (CLI)",
        [("exit", 2), ("has", "usage_error", "not valid JSON")]),
    cli(["frobnicate"], "unknown_command_cli", "invalid: unknown subcommand (CLI)", [("exit", 2)]),
]))

# =================================================================================================================
# S06 profile B vs C: tools offered; refusal evidence not required in B
# =================================================================================================================
S.append(dict(id="S06_profile_B", profile="B", ifaces=ALL4, title="profile B (ablation arm)", steps=[
    st("get_session", {}, cap="profile B: tool set (no check_bounds / certify / as_built)", check="B_tools",
       expect=[("ok", True), ("len", "result.tools", 14), ("not_contains", "result.tools", "certify"),
               ("not_contains", "result.tools", "check_bounds")], ifaces=LMG),
    st("set_material", {"name": "Ti6Al4V"}),
    st("set_target", tgt(density_max=0.2, E100_min={"value": 0.5, "unit": "E_s"})),
    st("check_bounds", {}, cap="profile B: check_bounds not offered", check="B_no_bounds",
       expect=[("ok", False), ("has", "error", "unknown tool")]),
    st("certify", {"design": D_SL}, cap="profile B: certify not offered", check="B_no_certify",
       expect=[("ok", False), ("has", "error", "unknown tool")]),
    st("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"},
       cap="profile B: refusal without evidence accepted, evidence not checked", check="B_refuse_unchecked",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "proven_infeasible"),
               ("eq", "result.outcome_card.evidence_checked", False), ("len", "result.outcome_card.evidence", 0)],
       ifaces=LMG),
]))
S.append(dict(id="S07_profile_B_release", profile="B", ifaces=LMG, title="profile B uncertified release", steps=[
    st("set_material", {"name": "PA12"}),
    st("set_target", tgt(density_max=0.25)),
    st("submit", {"decision": "release", "design": D_BCC}, cap="profile B: release without certificate",
       check="B_release_uncertified",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "uncertified_release"),
               ("eq", "result.outcome_card.evidence_checked", False)]),
]))

# =================================================================================================================
# S08 proven infeasible and not found in families (profile C refusal evidence; stale evidence after edits)
# =================================================================================================================
S.append(dict(id="S08_refusals", profile="C", ifaces=LMG, title="refusal evidence: proven infeasible, not found", steps=[
    st("set_material", {"name": "Ti6Al4V"}),
    st("set_target", tgt(density_max=0.2, E100_min={"value": 0.5, "unit": "E_s"})),
    st("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"},
       cap="profile C: refusal without evidence rejected", check="C_refuse_no_evidence",
       expect=[("ok", False), ("has", "error", "refusal needs evidence")]),
    st("check_bounds", {}, label="cb1"),
    st("set_target", {"density_max": 0.21}),
    st("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"},
       cap="stale evidence: bound record after a spec edit", check="stale_bound_record",
       expect=[("ok", False), ("has", "error", "refusal needs evidence")]),
    st("undo", {}),
    st("submit", {"decision": "refuse", "verdict": "NOT_FOUND_IN_FAMILIES"},
       cap="refusal with the wrong verdict for the evidence held", check="wrong_verdict",
       expect=[("ok", False), ("has", "error", "refusal needs evidence")]),
    st("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE", "evidence": [9999]},
       cap="refusal citing an unknown record", check="unknown_evidence_seq",
       expect=[("ok", False), ("has", "error", "not an evidence record")]),
    st("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE", "evidence": ["$cb1.seq"]},
       cap="outcome: proven_infeasible (cites the bound record)", check="proven_infeasible",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "proven_infeasible"),
               ("eq", "result.outcome_card.evidence[0].seq", "$cb1.seq"),
               ("eq", "result.outcome_card.evidence[0].kind", "bound_violation")]),
    st("submit", {"decision": "need_info"}, cap="second submit refused", check="already_submitted",
       expect=[("ok", False), ("has", "error", "already submitted")]),
]))
S.append(dict(id="S09_not_found", profile="C", ifaces=LMG, title="not found in families; stale family edit", steps=[
    st("set_material", {"name": "316L"}),
    st("set_target", GAPT),
    st("set_constraints", {"families": ["tpms"]}),
    st("check_bounds", {}, label="cb", cap="atlas NOT_FOUND evidence (tpms)", check="nf_bounds",
       expect=[("ok", True), ("eq", "result.verdict", "NOT_FOUND_IN_FAMILIES")]),
    st("set_constraints", {"families": ["tpms", "resonator"]}),
    st("submit", {"decision": "refuse", "verdict": "NOT_FOUND_IN_FAMILIES"},
       cap="stale evidence: atlas record after widening the families", check="stale_family_record",
       expect=[("ok", False), ("has", "error", "refusal needs evidence")]),
    st("set_constraints", {"families": ["tpms"]}),
    st("get_session", {}, cap="evidence check: record holds again for the original families", check="nf_holds",
       expect=[("ok", True), ("eq", "result.evidence[0].holds_for_current_spec", True),
               ("eq", "result.evidence[0].kind", "atlas_not_found")]),
    st("submit", {"decision": "refuse", "verdict": "NOT_FOUND_IN_FAMILIES"}, cap="outcome: not_found_in_families",
       check="not_found_in_families",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "not_found_in_families"),
               ("eq", "result.outcome_card.evidence[0].seq", "$cb.seq")]),
]))

# =================================================================================================================
# S10 refuted certificates (geometry-only: schwarz_p network below its percolation density) and budget exhaustion
# =================================================================================================================
S.append(dict(id="S10_refuted_budget", profile="C", ifaces=LMG, title="refuted certificates; certify budget", steps=[
    st("set_material", {"name": "316L"}),
    st("set_target", tgt(density_max=0.3, E100_min={"value": 0.001, "unit": "E_s"})),
    st("certify", {"design": D_SP_LOW[0]}, label="c1", cap="certify: refuted (invalid geometry)", check="refuted_cert",
       expect=[("ok", True), ("eq", "result.verdict", "refuted"), ("eq", "result.outcome", "refuted_candidate")],
       note="schwarz_p network density 0.06 does not percolate (atlas: invalid)"),
    st("certify", {"design": D_SP_LOW[1]}),
    st("certify", {"design": D_SP_LOW[2]}),
    st("certify", {"design": D_SP_LOW[3]}),
    st("certify", {"design": D_SL}, cap="invalid: budget exhaustion (5th certificate)", check="budget_exhausted",
       expect=[("ok", False), ("has", "error", "session budget exhausted")]),
    st("submit", {"decision": "release", "design": D_SP_LOW[0]}, cap="release of a refuted design rejected",
       check="release_refuted", expect=[("ok", False), ("has", "error", "verdict was refuted")]),
    st("submit", {"decision": "refuse", "verdict": "OTHER", "evidence": ["$c1.seq"]}, cap="outcome: refuted_candidate",
       check="refuted_candidate",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "refuted_candidate"),
               ("eq", "result.outcome_card.evidence[0].kind", "certificate_refuted")]),
]))

# =================================================================================================================
# S11 certified static design through MCP, GUI and CLI (identical spec and design: the same certificate key);
#     stale certificate after a spec edit, a material change and a design change; screening; export
# =================================================================================================================
PA12_SPEC = [st("set_material", {"name": "PA12"}),
             st("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"}),
             st("set_target", tgt(E100_min={"value": 25, "unit": "MPa"}, density_max=0.25))]
S.append(dict(id="S11_certified_static", profile="C", ifaces=("mcp", "gui"), title="PA12 static certificate", steps=PA12_SPEC + [
    st("check_bounds", {}, cap="combination density + stiffness (MPa): feasible", check="pa12_bounds",
       expect=[("ok", True), ("eq", "result.verdict", "FEASIBLE")]),
    st("evaluate", {"designs": [D_SL]}, cap="evaluate (search tier) before certify", check="pa12_eval",
       expect=[("ok", True), ("len", "result.results[0].C_MPa", 6)]),
    st("certify", {"design": D_SL}, label="cert", cap="certify: certified (static, density + E100 in MPa)",
       check="pa12_certify",
       expect=[("ok", True), ("eq", "result.verdict", "certified"), ("eq", "result.outcome", "certified_candidate"),
               ("eq", "result.spec_hash", "c3816dab1e980508")], note="tutorial 02 certified this design (20 s)"),
    st("get_session", {}, label="gs1", cap="certificate key recorded", check="pa12_cert_key",
       expect=[("ok", True), ("len", "result.certificates", 1)]),
    st("as_built", {"design": D_SL}, cap="as_built reuses the certificate (no new solve, no budget)",
       check="as_built_from_cert", expect=[("ok", True), ("has", "result.source", "no new solve"),
                                           ("eq", "result.passed", True)]),
    st("set_target", {"density_max": 0.24}),
    st("get_session", {}, cap="stale certificate after a spec edit: evidence check", check="stale_spec_evidence",
       expect=[("ok", True), ("eq", "result.evidence[0].kind", "certificate_certified"),
               ("eq", "result.evidence[0].holds_for_current_spec", False)]),
    st("submit", {"decision": "release", "design": D_SL}, cap="stale certificate after a spec edit: release refused",
       check="stale_spec_release", expect=[("ok", False), ("has", "error", "release needs a certificate")]),
    st("export", {"design": D_SL, "tiles": 1, "resolution": 32, "tile_resolution": 16},
       cap="stale certificate after a spec edit: export not certified", check="stale_spec_export",
       expect=[("ok", True), ("eq", "result.outcome", "not_certified")]),
    st("undo", {}),
    st("set_material", {"name": "Ti6Al4V"}),
    st("submit", {"decision": "release", "design": D_SL}, cap="stale certificate after a material change: release refused",
       check="stale_material_release", expect=[("ok", False), ("has", "error", "release needs a certificate")]),
    st("get_session", {}, cap="stale certificate after a material change: evidence check", check="stale_material_evidence",
       expect=[("ok", True), ("eq", "result.evidence[0].holds_for_current_spec", False)]),
    st("undo", {}),
    st("submit", {"decision": "release", "design": D_SL_OTHER},
       cap="stale certificate after a design change: release refused", check="stale_design_release",
       expect=[("ok", False), ("has", "error", "release needs a certificate")]),
    st("screen_manufacturing", {"design": D_SL, "tiles": 2, "resolution": 48}, cap="screening pass (PA12 0.8 mm)",
       check="screen_pass", expect=[("ok", True), ("eq", "result.passed", True)],
       note="ligaments about 1.8 mm on a 10 mm cell"),
    st("screen_manufacturing", {"design": D_SL, "tiles": 2, "resolution": 48, "printer_min_feature_mm": 3.0},
       cap="screening fail (stated limit 3.0 mm)", check="screen_fail",
       expect=[("ok", True), ("eq", "result.passed", False), ("eq", "result.min_feature.passed", False)]),
    st("submit", {"decision": "release", "design": D_SL}, cap="outcome: certified_candidate (release)",
       check="pa12_release",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "certified_candidate"),
               ("eq", "result.outcome_card.evidence[0].seq", "$cert.seq")]),
    st("export", {"design": D_SL, "tiles": 2, "resolution": 48, "tile_resolution": 24}, label="exp",
       cap="export: single cell + tiled, report references the certificate", check="pa12_export",
       expect=[("ok", True), ("eq", "result.outcome", "certified_candidate"), ("notnone", "result.files.cell.sha256"),
               ("notnone", "result.files.tiled.sha256"), ("has", "result.files.tiled.path", "tiled_2x2x2.stl"),
               ("report", "certificate.verdict", "certified"), ("report", "certificate.certify_seq", "$cert.seq"),
               ("report", "outcome.outcome", "certified_candidate"), ("report", "submission.outcome", "certified_candidate"),
               ("report", "screening.verdict", "screen passed")]),
]))
# the same certificate through the CLI (one invocation: certify, release, export)
PA12_CLI = ["--material", "PA12", "--cell-size", "10", "--target", '{"E100_min": {"value": 25, "unit": "MPa"}, '
            '"density_max": 0.25}']
S.append(dict(id="S12_cli", profile="C", ifaces=("cli",), title="CLI subcommands", steps=[
    cli(["check-bounds"] + PA12_CLI, "cli_check_bounds", "CLI check-bounds (density + stiffness)",
        [("exit", 0), ("eq", "result.verdict", "FEASIBLE")]),
    cli(["atlas-suggest", "--top", "3"] + PA12_CLI, "cli_atlas_suggest", "CLI atlas-suggest",
        [("exit", 0), ("len", "result.best", 3)]),
    cli(["evaluate", "--design", '{"kind":"bcc","params":{"r":0.08,"R":0.0}}', "--bands"] + PA12_CLI, "cli_evaluate_bands",
        "CLI evaluate with bands (schema 3)", [("exit", 0), ("notnone", "result.results[0].bands.f_star"),
                                              ("len", "result.results[0].C", 6)]),
    cli(["certify", "--design", '{"kind":"sphere_ligaments","params":{"c":0.12,"w":0.181739}}', "--release",
         "--export", "--tiles", "2", "--resolution", "48", "--tile-resolution", "24"] + PA12_CLI, "cli_certify_release_export",
        "CLI certify + release + export (report references the certificate)",
        [("exit", 0), ("eq", "calls[3].result.verdict", "certified"), ("eq", "calls[3].result.spec_hash", "c3816dab1e980508"),
         ("eq", "calls[4].result.outcome_card.outcome", "certified_candidate"),
         ("eq", "result.outcome", "certified_candidate"), ("report", "certificate.verdict", "certified"),
         ("report", "certificate.certify_seq", 4)]),
    cli(["replay", "$last_cli_session"], "cli_replay", "CLI replay of a CLI session (certificate + export)",
        [("exit", 0), ("eq", "result.exact", True)]),
    cli(["export", "--design", '{"kind":"bcc","params":{"r":0.08,"R":0.0}}', "--tiles", "1", "--resolution", "64",
         "--tile-resolution", "32"] + PA12_CLI, "cli_export_uncertified", "CLI export without certificate; screening pass 10 mm",
        [("exit", 0), ("eq", "result.outcome", "not_certified"), ("eq", "result.screening.passed", True),
         ("report", "certificate", None), ("has", "result.files.tiled.path", "tiled_1x1x1.stl")]),
    cli(["export", "--design", '{"kind":"bcc","params":{"r":0.08,"R":0.0}}', "--tiles", "1", "--resolution", "64",
         "--tile-resolution", "32", "--material", "PA12", "--cell-size", "4"], "cli_export_screen_fail",
        "CLI export: screening fail at 4 mm (0.64 mm struts vs 0.8 mm)",
        [("exit", 0), ("eq", "result.screening.passed", False)]),
    cli(["export", "--design", '{"kind":"bcc","params":{"r":0.08,"R":0.0}}', "--nosession"], "cli_export_no_session",
        "CLI export without --session refused by amm", [("exit", 1), ("has", "error.error", "session directory")]),
    cli(["check-bounds", "--profile", "B", "--material", "316L", "--target", '{"density_max": 0.3}'], "cli_profile_B",
        "CLI profile B: check-bounds refused", [("exit", 1), ("has", "error.error", "unknown tool")]),
    cli(["check-bounds", "--material", "316L", "--target", '{"zener_min": 0.9}'], "cli_zener",
        "CLI Zener target refused clearly", [("exit", 1), ("has", "error.error", "output")]),
]))

# =================================================================================================================
# S13 library: combined stiffness + gap certificate (316L, Hz/kHz with a cell size), stale certificate, export
# S14 library: undetermined gap certificate, stale certificate evidence, refusal UNDETERMINED
# =================================================================================================================
S.append(dict(id="S13_lib_combined", profile="C", ifaces=("lib",), title="316L stiffness + gap certificate", steps=[
    st("set_material", {"name": "316L"}),
    st("set_constraints", {"cell_size": 5, "cell_size_unit": "mm"}),
    st("set_target", tgt(density_max=0.12, E100_min={"value": 3.53, "unit": "GPa"},
                         gap={"f_lo": 174.0, "f_hi": 271.0, "unit": "kHz"}), cap="units: kHz with a cell size (316L)",
       check="combo_units", expect=[("ok", True), ("approx", "result.normalized.gap.f_lo", fstar(174e3, 0.005, "316L"), 1e-12),
                                    ("approx", "result.normalized.gap.f_hi", fstar(271e3, 0.005, "316L"), 1e-12)]),
    st("check_bounds", {}),
    st("evaluate", {"designs": [D_M03]}),
    st("certify", {"design": D_M03}, label="cert", cap="certify: certified (stiffness + gap)", check="combo_certify",
       expect=[("ok", True), ("eq", "result.verdict", "certified"), ("eq", "result.gap.verdict.verdict", "certified")],
       note="E4 M03: certified in 150 s"),
    st("as_built", {"design": D_M03}, cap="as_built from the certificate", check="combo_as_built",
       expect=[("ok", True), ("has", "result.source", "no new solve")]),
    st("set_target", {"gap": {"f_lo": 174.0, "f_hi": 280.0, "unit": "kHz"}}),
    st("submit", {"decision": "release", "design": D_M03}, cap="stale certificate after a gap edit: release refused",
       check="combo_stale_spec", expect=[("ok", False), ("has", "error", "release needs a certificate")]),
    st("export", {"design": D_M03, "tiles": 1, "resolution": 32, "tile_resolution": 16},
       cap="stale certificate after a gap edit: export report has no certificate", check="combo_stale_export",
       expect=[("ok", True), ("eq", "result.outcome", "not_certified"), ("report", "certificate", None)]),
    st("undo", {}),
    st("set_material", {"name": "Ti6Al4V"}),
    st("submit", {"decision": "release", "design": D_M03}, cap="stale certificate after a material change",
       check="combo_stale_material", expect=[("ok", False), ("has", "error", "release needs a certificate")]),
    st("undo", {}),
    st("submit", {"decision": "release", "design": {"kind": "sphere_ligaments", "params": {"c": 0.29, "w": 0.124}}},
       cap="stale certificate after a design change", check="combo_stale_design",
       expect=[("ok", False), ("has", "error", "release needs a certificate")]),
    st("screen_manufacturing", {"design": D_M03, "tiles": 2, "resolution": 48}, cap="screening pass (316L 0.3 mm)",
       check="combo_screen_pass", expect=[("ok", True), ("eq", "result.min_feature.passed", True)],
       note="ligaments 0.124 * 5 mm = 0.62 mm"),
    st("screen_manufacturing", {"design": D_M03, "tiles": 2, "resolution": 48, "printer_min_feature_mm": 1.0},
       cap="screening fail (stated 1.0 mm)", check="combo_screen_fail",
       expect=[("ok", True), ("eq", "result.min_feature.passed", False)]),
    st("submit", {"decision": "release", "design": D_M03}, cap="outcome: certified_candidate (gap)", check="combo_release",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "certified_candidate")]),
    st("export", {"design": D_M03, "tiles": 3, "resolution": 48, "tile_resolution": 24},
       cap="export tiled 3x3x3; report references the certificate", check="combo_export",
       expect=[("ok", True), ("eq", "result.outcome", "certified_candidate"), ("report", "certificate.certify_seq", "$cert.seq"),
               ("report", "certificate.gap.verdict", "certified"), ("has", "result.files.tiled.path", "tiled_3x3x3.stl")]),
]))
S.append(dict(id="S14_lib_undetermined", profile="C", ifaces=("lib",), title="Ti6Al4V gap: undetermined", steps=[
    st("set_material", {"name": "Ti6Al4V"}),
    st("set_constraints", {"cell_size": 1, "cell_size_unit": "cm"}),
    st("set_target", tgt(gap={"f_lo": 0.4008147294965229, "f_hi": 0.7078905303204719, "unit": "f*"})),
    st("certify", {"design": D_G05}, label="cert", cap="certify: undetermined (gap inside the guard)", check="undet_certify",
       expect=[("ok", True), ("eq", "result.verdict", "undetermined"), ("eq", "result.outcome", "numerically_undetermined")],
       note="E4 G05: undetermined in 122 s"),
    st("set_target", {"gap": {"f_lo": 0.40, "f_hi": 0.7078905303204719, "unit": "f*"}}),
    st("submit", {"decision": "refuse", "verdict": "UNDETERMINED"},
       cap="stale undetermined certificate after a spec edit: refusal rejected", check="undet_stale",
       expect=[("ok", False), ("has", "error", "refusal needs evidence")]),
    st("undo", {}),
    st("submit", {"decision": "refuse", "verdict": "UNDETERMINED"}, cap="outcome: numerically_undetermined",
       check="numerically_undetermined",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "numerically_undetermined"),
               ("eq", "result.outcome_card.evidence[0].seq", "$cert.seq")]),
]))
S.append(dict(id="S15_lib_release_without_cert", profile="C", ifaces=LMG, title="release without certificate (C)", steps=[
    st("set_material", {"name": "PA12"}),
    st("set_target", tgt(density_max=0.25)),
    st("submit", {"decision": "release", "design": D_BCC}, cap="profile C: release without a certificate refused",
       check="C_release_uncertified", expect=[("ok", False), ("has", "error", "call certify first")]),
    st("submit", {"decision": "release"}, cap="invalid: release without a design", check="release_no_design",
       expect=[("ok", False), ("has", "error", "needs a design")]),
]))

# =================================================================================================================
# S16 ADDENDUM, defined after run 1 (2026-11-08 08:25), before it was run. It replaces rows of run 1 whose
# pre-defined expectation or design was wrong (the run-1 rows stay in the matrix as failures, cause "V2 expectation"):
#   S05 validity_rule: the design cube_bars c 0.5, w 0.48 is outside the box (w <= 0.36), so the box message came
#       first; here w 0.33 <= 0.36 but > c - 0.04 = 0.31 (validity rule only);
#   S08 wrong_verdict: check_bounds of an infeasible spec also holds an atlas NOT_FOUND record (test_outcomes), so a
#       NOT_FOUND refusal was correctly accepted and the rest of S08 ran on a submitted session; here the wrong verdict
#       is UNDETERMINED (no certificate held), then the unknown-seq and proven_infeasible rows;
#   S04/S09 tpms-only gap f* [0.25, 0.35]: the atlas verdict counts the optimistic error ranges and the interpolation
#       between cells (amm.atlas.oracle), so it is BORDERLINE, not NOT_FOUND; here the gap f* [2.5, 3.0] (max f_hi of
#       every family 1.85; NOT_FOUND for all families in run 1, S01 gap_infeasible) with families tpms + struts.
# =================================================================================================================
S.append(dict(id="S16_addendum", profile="C", ifaces=ALL4, title="addendum: corrected rows of run 1", steps=[
    st("set_material", {"name": "Ti6Al4V"}),
    st("set_target", tgt(density_max=0.2, E100_min={"value": 0.5, "unit": "E_s"})),
    st("evaluate", {"designs": [{"kind": "cube_bars", "params": {"c": 0.35, "w": 0.33}}]},
       cap="invalid: family validity rule (inside the box)", check="validity_rule_r2",
       expect=[("ok", False), ("has", "error", "validity rule")]),
    st("check_bounds", {}, label="cb1", cap="bound and atlas records of an infeasible spec", check="cb_records_r2",
       expect=[("ok", True), ("eq", "result.verdict", "PROVEN_INFEASIBLE"),
               ("eq", "result.atlas.verdict", "NOT_FOUND_IN_FAMILIES")]),
    st("submit", {"decision": "refuse", "verdict": "UNDETERMINED"},
       cap="refusal with the wrong verdict for the evidence held", check="wrong_verdict_r2",
       expect=[("ok", False), ("has", "error", "refusal needs evidence")], ifaces=LMG),
    st("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE", "evidence": [9999]},
       cap="refusal citing an unknown record", check="unknown_evidence_seq_r2",
       expect=[("ok", False), ("has", "error", "not an evidence record")], ifaces=LMG),
    st("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE", "evidence": ["$cb1.seq"]},
       cap="outcome: proven_infeasible (cites the bound record)", check="proven_infeasible_r2",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "proven_infeasible"),
               ("eq", "result.outcome_card.evidence[0].seq", "$cb1.seq"),
               ("eq", "result.outcome_card.evidence[0].kind", "bound_violation")], ifaces=LMG),
]))
S.append(dict(id="S17_addendum_not_found", profile="C", ifaces=ALL4, title="addendum: not found in families", steps=[
    st("set_material", {"name": "316L"}),
    st("set_target", tgt(gap={"f_lo": 2.5, "f_hi": 3.0, "unit": "f*"})),
    st("set_constraints", {"families": ["tpms", "struts"]}),
    st("check_bounds", {}, label="cb", cap="atlas NOT_FOUND evidence (tpms + struts)", check="nf_bounds_r2",
       expect=[("ok", True), ("eq", "result.verdict", "NOT_FOUND_IN_FAMILIES"), ("len", "result.violated", 0)]),
    st("set_constraints", {"families": ["tpms", "struts", "resonator"]}, ifaces=LMG),
    st("submit", {"decision": "refuse", "verdict": "NOT_FOUND_IN_FAMILIES"},
       cap="stale evidence: atlas record after widening the families", check="stale_family_record_r2",
       expect=[("ok", False), ("has", "error", "refusal needs evidence")], ifaces=LMG),
    st("set_constraints", {"families": ["tpms", "struts"]}, ifaces=LMG),
    st("get_session", {}, cap="evidence check: record holds again for the original families", check="nf_holds_r2",
       expect=[("ok", True), ("eq", "result.evidence[0].holds_for_current_spec", True),
               ("eq", "result.evidence[0].kind", "atlas_not_found")], ifaces=LMG),
    st("submit", {"decision": "refuse", "verdict": "NOT_FOUND_IN_FAMILIES"}, cap="outcome: not_found_in_families",
       check="not_found_in_families_r2",
       expect=[("ok", True), ("eq", "result.outcome_card.outcome", "not_found_in_families"),
               ("eq", "result.outcome_card.evidence[0].seq", "$cb.seq")], ifaces=LMG),
]))
ADDENDUM = ("S16_addendum", "S17_addendum_not_found")

SCENARIOS = {s["id"]: s for s in S}


def rows_expected():
    """Every (scenario, check, interface) row with its expectation, for the protocol."""
    out = []
    for s in S:
        for stp in s["steps"]:
            if not stp.get("check"):
                continue
            for i in (stp["ifaces"] or s["ifaces"]):
                if i not in s["ifaces"] and stp["tool"] != "__cli__":
                    continue
                if i == "cli" and stp["tool"] not in CLI_TOOLS and stp["tool"] != "__cli__":
                    continue
                out.append(dict(scenario=s["id"], check=stp["check"], capability=stp["cap"], interface=i,
                                profile=s["profile"], tool=stp["tool"] if stp["tool"] != "__cli__" else "amm " + stp["argv"][0],
                                expected=describe(stp["expect"]), note=stp.get("note", "")))
    return out


# tools the CLI exposes (spec tools are passed through its spec options)
CLI_TOOLS = ("set_material", "set_constraints", "set_target", "check_bounds", "atlas_suggest", "evaluate", "certify",
             "export")


def describe(expect) -> str:
    parts = []
    for e in expect:
        k = e[0]
        if k == "ok":
            parts.append("accepted" if e[1] else "refused")
        elif k == "exit":
            parts.append(f"exit {e[1]}")
        elif k == "refused_or":
            parts.append(f"refused, or verdict PROVEN_INFEASIBLE by {e[1]}")
        elif k == "report":
            parts.append(f"report.json {e[1]} = {e[2]!r}")
        elif len(e) == 2:
            parts.append(f"{e[1]} {k}")
        elif k == "approx":
            parts.append(f"{e[1]} ~= {e[2]:.6g} (rtol {e[3]:g})")
        else:
            parts.append(f"{e[1]} {k} {e[2]!r}")
    return "; ".join(parts)
