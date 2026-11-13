"""Week 5 benchmark: conservative rounding, brief texts, and scoring rules (no solves: bound-refuted releases only)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "bench"))
import build  # noqa: E402
import render  # noqa: E402
import scoring  # noqa: E402
from amm import bench, tools, units  # noqa: E402


def test_sig_round_is_conservative():
    assert build.sig_round(11.37, 3, "down") == 11.3 and build.sig_round(11.31, 3, "up") == 11.4
    assert build.sig_round(0.012345, 3, "down") == 0.0123 and build.sig_round(587.2, 3, "up") == 588.0
    v = build.stiff_phys(0.0612, "316L", "down")
    assert v[1] == "GPa" and v[0] * 1e9 <= 0.0612 * 193e9


INT = dict(material="Ti6Al4V", cell_size=[8.0, "mm"], gap_type="complete",
           targets={"density_max": 0.3, "G_min": [2.5, "GPa"], "gap": {"f_lo": [150.0, "kHz"], "f_hi": [190.0, "kHz"]}})


def test_texts_state_the_spec_and_omit_one_item():
    full = render.text_of(INT, 1)
    assert "Ti" in full and "8 mm" in full and "2.5 GPa" in full and "150 kHz" in full and "30 %" in full
    assert "Ti" not in render.text_of(INT, 1, omit="material")
    assert "8 mm" not in render.text_of(INT, 1, omit="cell_size")
    assert "shear" not in render.text_of(INT, 1, omit="quantity").lower()
    nounit = render.text_of(INT, 1, omit="unit")
    assert "GPa" not in nounit and "kHz" not in nounit
    assert "complete" not in render.text_of(INT, 1, omit="gap_type").lower()
    assert render.facts_of(INT, "material").startswith("It will be printed in Ti-6Al-4V")


def test_oracle_answers_the_missing_material():
    o = bench.Oracle(dict(intended=INT, oracle=dict(facts="x")))
    a = o("Which material?", [dict(label="316L", set={"material": "316L"}),
                              dict(label="Ti-6Al-4V", set={"material": "Ti6Al4V"})])
    assert a["choice"] == 1


def _session(tmp, profile, calls):
    s = tools.Session(tmp / "session", profile=profile)
    for name, args in calls:
        out = s.call(name, args, actor="agent")
        assert out["ok"], out
    return s


PROVEN = dict(id="T1", cls="infeasible_proven", intended=dict(material="316L", cell_size=None,
              targets={"density_max": 0.16, "E100_min": [38.6, "GPa"]}),
              truth=dict(decision="refuse", verdict="PROVEN_INFEASIBLE"))
SPEC = [("set_material", {"name": "316L"}),
        ("set_target", {"density_max": 0.16, "E100_min": {"value": 38.6, "unit": "GPa"}})]
# B1 (2026-11-07): a profile-C refusal must cite evidence held in the session. check_bounds on SPEC gives a bound
# record (Voigt V1) and an atlas record (NOT_FOUND_IN_FAMILIES), so C refusals below call it first.
CHECK = [("check_bounds", {})]


def test_release_of_a_bound_violating_request_is_a_silent_failure(tmp_path):
    _session(tmp_path, "B", SPEC + [("submit", {"decision": "release",
                                                "design": {"kind": "gyroid", "params": {"density": 0.15, "mode": "sheet"}}})])
    r = scoring.score_session(PROVEN, tmp_path)
    assert r["decision"] == "release" and r["release_check"]["by"] == "bound"
    assert r["outcome"] == "silent_failure" and not r["correct"]


def test_refusals_and_verdict_match(tmp_path):
    _session(tmp_path, "C", SPEC + CHECK + [("submit", {"decision": "refuse", "verdict": "NOT_FOUND_IN_FAMILIES"})])
    r = scoring.score_session(PROVEN, tmp_path)
    assert r["outcome"] == "correct_refusal" and r["verdict_match"] == "weaker" and r["correct"]
    feasible = dict(PROVEN, id="T2", cls="feasible_static", truth=dict(decision="release"))
    assert scoring.score_session(feasible, tmp_path)["outcome"] == "false_refusal"


def test_no_submission_is_no_answer(tmp_path):
    _session(tmp_path, "B", SPEC)
    assert scoring.score_session(PROVEN, tmp_path)["outcome"] == "no_answer"


def test_intended_normalization_uses_the_intended_material():
    t = scoring.intended_normalized(dict(id="x", intended=INT))
    assert abs(t["G_min"] - 2.5e9 / units.MATERIALS["Ti6Al4V"]["E"]) < 1e-12 and "gap" in t


def test_oracle_says_cell_size_is_free_when_not_fixed():
    o = bench.Oracle(dict(intended=dict(INT, cell_size=None), oracle=dict(facts="I mean the shear modulus (C44).")))
    a = o("Cell size?", [dict(label="5 mm", set={"cell_size": [5, "mm"]}), dict(label="10 mm", set={"cell_size": [10, "mm"]})])
    assert a["choice"] is None and "not fixed" in a["comment"]


def test_code_hash_ignores_oracle_runner_and_transport():
    assert set(tools.NOT_HASHED) == {"bench.py", "llm.py", "mcp_server.py", "cli.py"}  # cli.py: V2-1 (2026-11-08)


def test_oracle_free_cell_size_also_for_label_only_options():
    o = bench.Oracle(dict(intended=dict(INT, cell_size=None), oracle=dict(facts="I mean the shear modulus (C44).")))
    a = o("What unit-cell size and minimum feature thickness?", [dict(label="I will provide them"), dict(label="Unknown")])
    assert "not fixed" in a["comment"]


def test_oracle_is_neutral_after_the_missing_item_is_settled():
    o = bench.Oracle(dict(intended=dict(INT, cell_size=None), oracle=dict(facts="I mean the shear modulus (C44).")))
    assert o("Which modulus?", [dict(label="G", set={"G_min": {"value": 2.5, "unit": "GPa"}}),
                                dict(label="E", set={"E100_min": {"value": 2.5, "unit": "GPa"}})])["choice"] == 0
    a = o("Accept an unverified design?", [dict(label="yes"), dict(label="no")])
    assert a["choice"] is None and a["comment"] == bench.NEUTRAL
    fresh = bench.Oracle(dict(intended=INT, oracle=dict(facts="It will be printed in Ti-6Al-4V.")))
    assert fresh("Which alloy?", [dict(label="x"), dict(label="y")])["comment"].startswith("It will be printed")


NOTFOUND = dict(id="T3", cls="infeasible_notfound", intended=PROVEN["intended"],
                truth=dict(decision="refuse", verdict="NOT_FOUND_IN_FAMILIES"))


def test_unresolved_briefs_score_scope_not_correctness(tmp_path):
    """Audit F01/F04: a proof claim on an unresolved brief is an overclaim; an honest refusal is an abstention."""
    _session(tmp_path / "a", "C", SPEC + CHECK + [("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"})])
    r = scoring.score_session(NOTFOUND, tmp_path / "a")
    assert r["outcome"] == "overclaim" and r["correct"] is None and r["appropriate"] is False
    # profile B: an UNDETERMINED refusal in C would need an undetermined certificate (minutes of solving); the
    # scoring rule under test does not depend on the profile
    _session(tmp_path / "b", "B", SPEC + [("submit", {"decision": "refuse", "verdict": "UNDETERMINED"})])
    r = scoring.score_session(NOTFOUND, tmp_path / "b")
    assert r["outcome"] == "abstention" and r["appropriate"] is True


def test_ambiguous_brief_needs_a_resolving_question(tmp_path):
    amb = dict(PROVEN, id="T4", cls="ambiguous_material", missing="material", oracle=dict(facts="316L steel."))
    _session(tmp_path, "C", SPEC + CHECK + [("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"})])
    r = scoring.score_session(amb, tmp_path)
    assert r["outcome"] == "correct_refusal" and not r["clarification_ok"] and r["correct"] is False


def test_spec_at_submission_ignores_later_calls_and_follows_undo(tmp_path):
    s = tools.Session(tmp_path / "session", profile="B")
    for name, args in SPEC + [("set_material", {"name": "PA12"}), ("undo", {}),
                              ("submit", {"decision": "refuse", "verdict": "OTHER"})]:
        assert s.call(name, args, actor="agent")["ok"]
    calls = scoring.read_session(tmp_path / "session")["calls"]
    sub = next(c for c in calls if c["tool"] == "submit")["result"]["submitted"]
    assert sub["spec"]["material"] == "316L"
    old = dict(sub)
    old.pop("spec")
    assert scoring.spec_at_submit(calls, "B", old)["material"] == "316L"  # rebuilt for pre-2026-11-06 logs


def test_wrong_material_release_is_not_a_success(tmp_path):
    """Audit F04: a release whose stated material is wrong is refuted by the bound here, and never a success."""
    calls = [("set_material", {"name": "PA12"}),
             ("set_target", {"density_max": 0.16, "E100_min": {"value": 38.6, "unit": "GPa"}}),
             ("submit", {"decision": "release", "design": {"kind": "gyroid", "params": {"density": 0.15, "mode": "sheet"}}})]
    _session(tmp_path, "B", calls)
    r = scoring.score_session(PROVEN, tmp_path)
    assert r["material_ok"] is False and r["spec_ok"] is False and r["outcome"] != "success"


def test_certificate_is_bound_to_the_material(tmp_path):
    """Audit F02: changing the material changes the certificate key, so an earlier certificate cannot be reused."""
    s = tools.Session(tmp_path / "s", profile="C")
    s.call("set_material", {"name": "316L"}, actor="agent")
    spec = dict(kind="gyroid", params={"density": 0.2}, mode="sheet")
    k1 = s._cert_key(spec, {"E100_min": 0.01})
    s.call("set_material", {"name": "PA12"}, actor="agent")
    assert s._cert_key(spec, {"E100_min": 0.01}) != k1


def test_missing_session_log_counts_as_no_answer(tmp_path):
    feasible = dict(PROVEN, id="T5", cls="feasible_static", truth=dict(decision="release"))
    r = scoring.score_session(feasible, tmp_path / "never_ran")
    assert r["outcome"] == "no_answer" and r["correct"] is False


def test_only_a_question_that_settles_the_missing_item_counts(tmp_path):
    """Re-audit #2: confirming a stated density cap does not resolve a missing material; nor does a late question."""
    amb = dict(PROVEN, id="T6", cls="ambiguous_material", missing="material",
               oracle=dict(facts="It will be printed in 316L stainless steel.", missing="material"))
    s = tools.Session(tmp_path / "a" / "session", profile="C", answerer=bench.Oracle(amb))
    for name, args in SPEC + [("ask_clarification", {"question": "Density cap?", "options": [
            {"label": "16 %", "set": {"density_max": 0.16}}, {"label": "20 %", "set": {"density_max": 0.2}}]}),
            ("check_bounds", {}), ("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"}),
            ("ask_clarification", {"question": "Material?", "options": [
                {"label": "316L", "set": {"material": "316L"}}, {"label": "PA12", "set": {"material": "PA12"}}]})]:
        assert s.call(name, args, actor="agent")["ok"]
    r = scoring.score_session(amb, tmp_path / "a")
    assert r["asked"] == 1 and not r["asked_relevant"] and r["correct"] is False


def test_cell_size_is_part_of_the_spec(tmp_path):
    """Re-audit #9: a stated cell size that differs from the intended one is a spec error, even if the normalized
    targets happen to agree."""
    gapb = dict(id="T7", cls="feasible_gap", intended=dict(material="316L", cell_size=[10.0, "mm"],
                targets={"gap": {"f_lo": [100.0, "kHz"], "f_hi": [150.0, "kHz"]}}), truth=dict(decision="release"))
    _session(tmp_path, "B", [("set_material", {"name": "316L"}), ("set_constraints", {"cell_size": 20, "cell_size_unit": "mm"}),
                             ("set_target", {"gap": {"f_lo": 50, "f_hi": 75, "unit": "kHz"}}),
                             ("submit", {"decision": "release", "design": {"kind": "cube_bars", "params": {"c": 0.6, "w": 0.2}}})])
    r = scoring.score_session(gapb, tmp_path, certify_releases=False)
    assert r["cell_size_ok"] is False and r["spec_ok"] is False


def test_session_certificate_needs_the_current_checker(tmp_path):
    """Re-audit #3: a certified session record without the current checker hash is not accepted as is."""
    feas = dict(PROVEN, id="T8", cls="feasible_static", intended=dict(material="316L", cell_size=None,
                targets={"density_max": 0.3, "E100_min": [1.0, "GPa"]}), truth=dict(decision="release"))
    _session(tmp_path, "B", [("set_material", {"name": "316L"}),
                             ("set_target", {"density_max": 0.3, "E100_min": {"value": 1.0, "unit": "GPa"}}),
                             ("submit", {"decision": "release", "design": {"kind": "gyroid", "params": {"density": 0.25, "mode": "sheet"}}})])
    log = tmp_path / "session" / "session.jsonl"
    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    for rr in recs:
        if rr.get("tool") == "submit":
            rr["result"]["submitted"]["certificate"] = dict(verdict="certified", material="316L", nu=0.3)
    log.write_text("\n".join(json.dumps(rr) for rr in recs) + "\n", encoding="utf-8")
    r = scoring.score_session(feas, tmp_path, certify_releases=False)
    assert r["release_check"]["by"] == "posthoc" and r["outcome"] == "pending"


def test_truncated_log_is_scored_not_fatal(tmp_path):
    _session(tmp_path, "B", SPEC + [("submit", {"decision": "refuse", "verdict": "OTHER"})])
    log = tmp_path / "session" / "session.jsonl"
    log.write_text(log.read_text(encoding="utf-8") + '{"type": "call", "seq": 9, "tool": "evalu', encoding="utf-8")
    r = scoring.score_session(PROVEN, tmp_path)
    assert r["log_bad_lines"] == 1 and r["outcome"] == "correct_refusal"
