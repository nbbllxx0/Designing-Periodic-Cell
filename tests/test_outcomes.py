"""B1 (2026-11-07): refusal evidence, the five-outcome schema, schema versions, schema-1 projection and replay of
version-1 logs, and the full tensor C* in evaluate."""
from __future__ import annotations

import json

import numpy as np
import pytest

from amm import outcomes, tensor, tools

INFEASIBLE = [("set_material", {"name": "316L"}),
              ("set_target", {"density_max": 0.16, "E100_min": {"value": 38.6, "unit": "GPa"}})]  # Voigt V1 violated


def _s(tmp=None, profile="C", calls=INFEASIBLE, schema=tools.SCHEMA_VERSION):
    s = tools.Session(tmp, profile=profile, schema=schema)
    for n, a in calls:
        assert s.call(n, a)["ok"]
    return s


def test_refusal_without_evidence_is_rejected_with_a_clear_message():
    s = _s()
    out = s.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"})
    assert not out["ok"] and out["error"].startswith(outcomes.REFUSAL_ERROR)
    assert "check_bounds" in out["error"] and "No evidence record" in out["error"]
    assert s.submission is None


def test_bound_and_atlas_records_support_their_verdicts_only():
    s = _s()
    cb = s.call("check_bounds")
    assert cb["ok"] and cb["result"]["verdict"] == "PROVEN_INFEASIBLE"
    kinds = {e["kind"]: e["seq"] for e in s.evidence}
    assert kinds == {"bound_violation": 3, "atlas_not_found": 3}
    bad = s.call("submit", {"decision": "refuse", "verdict": "UNDETERMINED"})
    assert not bad["ok"] and "Records held for the current spec: seq 3 bound_violation" in bad["error"]
    bad = s.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE", "evidence": [99]})
    assert not bad["ok"] and "seq 99 is not an evidence record" in bad["error"]
    gs = s.call("get_session")["result"]
    assert gs["schema_version"] == tools.SCHEMA_VERSION and {e["kind"] for e in gs["evidence"]} == set(kinds)
    ok = s.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE", "evidence": [3]})
    assert ok["ok"]
    card = ok["result"]["outcome_card"]
    assert card["schema_version"] == outcomes.OUTCOME_SCHEMA and card["outcome"] == "proven_infeasible"
    assert card["evidence_checked"] and card["evidence"][0]["kind"] == "bound_violation"
    assert "V1" in card["evidence"][0]["summary"]
    assert ok["result"]["submitted"]["outcome"] == "proven_infeasible"


def test_stale_evidence_does_not_count():
    s = _s()
    assert s.call("check_bounds")["ok"]
    assert s.call("set_target", {"density_max": 0.17})["ok"]  # the spec changed after check_bounds
    out = s.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"})
    assert not out["ok"] and "No evidence record is held for the current spec" in out["error"]
    out = s.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE", "evidence": [3]})
    assert not out["ok"] and "computed for another spec" in out["error"]
    assert s.call("undo")["ok"]  # back to the checked spec: the record holds again
    assert s.call("submit", {"decision": "refuse", "verdict": "NOT_FOUND_IN_FAMILIES"})["result"][
        "outcome_card"]["outcome"] == "not_found_in_families"


def test_search_records_must_cover_the_declared_families():
    s = _s()
    e = dict(kind="search_not_found", seq=7, tool="search", summary="x", ctx=s._evidence_ctx("search", {}))
    assert s._holds(e)
    e2 = dict(e, ctx=s._evidence_ctx("search", {"families": ["struts"]}))
    assert not s._holds(e2)  # searched struts only, three families declared
    assert s.call("set_constraints", {"families": ["struts"]})["ok"]
    assert s._holds(e2)


def test_w1_rejection_on_input_is_a_bound_record():
    s = _s(calls=[("set_material", {"name": "Ti6Al4V"}), ("set_constraints", {"cell_size": 6})])
    assert not s.call("set_target", {"gap": {"f_lo": 0, "f_hi": 279, "unit": "kHz"}})["ok"]
    out = s.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"})
    assert out["ok"] and out["result"]["outcome_card"]["evidence"][0]["tool"] == "set_target"


def test_profile_b_records_the_claim_without_checking():
    s = _s(profile="B")
    out = s.call("submit", {"decision": "refuse", "verdict": "UNDETERMINED"})
    assert out["ok"]
    card = out["result"]["outcome_card"]
    assert card["outcome"] == "numerically_undetermined" and card["evidence_checked"] is False
    rel = _s(profile="B").call("submit", {"decision": "release",
                                          "design": {"kind": "sc", "params": {"r": 0.1, "R": 0.0}}})
    assert rel["result"]["outcome_card"]["outcome"] == "uncertified_release"


def test_need_info_outcome_and_evidence_only_for_refusals():
    s = _s()
    assert not s.call("submit", {"decision": "need_info", "evidence": [1]})["ok"]
    out = s.call("submit", {"decision": "need_info", "note": "material?"})
    assert out["result"]["outcome_card"]["outcome"] == "need_info"


def test_five_outcomes_and_schema_versions():
    assert list(outcomes.OUTCOMES) == ["certified_candidate", "refuted_candidate", "proven_infeasible",
                                       "not_found_in_families", "numerically_undetermined", "need_info"]
    c = tools.contract()
    assert c["schema_version"] == "amm-tools/3" and c["outcome_schema"] == "amm-outcome/1"  # B9: schema 3
    assert {"as_built", "screen_manufacturing", "export"} <= set(c["tools"])
    assert c["tools"]["as_built"]["since"] == "amm-tools/2" and c["tools"]["certify"]["since"] == "amm-tools/1"
    c1 = tools.contract(tools.SCHEMA_V1)
    assert set(c1["tools"]) == set(c["tools"]) - {"as_built", "screen_manufacturing", "export"}
    json.dumps(c)


def test_schema_1_session_is_the_projection_of_schema_2():
    v1 = _s(schema=tools.SCHEMA_V1)
    v2 = _s()
    assert v1.tools() == ["set_material", "set_constraints", "set_target", "set_source", "check_bounds",
                          "ask_clarification", "list_families", "atlas_suggest", "evaluate", "search", "certify",
                          "submit", "undo", "get_session"]
    assert not v1.call("export", {"design": {"kind": "sc", "params": {"r": 0.1, "R": 0.0}}})["ok"]
    for s in (v1, v2):
        assert s.call("check_bounds")["ok"]
    o1 = v1.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"})
    o2 = v2.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"})
    assert o1["ok"] and o2["ok"] and "outcome_card" not in o1["result"]
    assert tools.project("submit", o2["result"], tools.SCHEMA_V1) == o1["result"]
    assert set(o2["result"]["submitted"]) - set(o1["result"]["submitted"]) == {"outcome", "evidence"}
    g1, g2 = v1.call("get_session")["result"], v2.call("get_session")["result"]
    assert dict(tools.project("get_session", g2, tools.SCHEMA_V1), tools=g1["tools"]) == g1
    assert "evidence" not in g1 and g1["budget"] == dict(designs=tools.MAX_SESSION_DESIGNS,
                                                         certify=tools.MAX_SESSION_CERTIFY)


def _v1_log(tmp_path, drop_check_bounds: bool):
    s = _s(tmp_path / "s", schema=tools.SCHEMA_V1)
    assert s.call("check_bounds")["ok"]
    assert s.call("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE"})["ok"]
    recs = tools.read_log(tmp_path / "s" / "session.jsonl")
    assert recs[0]["schema"] == tools.SCHEMA_V1
    if drop_check_bounds:  # a version-1 log of a refusal with no evidence (allowed before B1)
        recs = [r for r in recs if r.get("tool") != "check_bounds"]
    return recs


def test_replay_of_a_version_1_log_is_exact_when_behaviour_is_unchanged(tmp_path):
    rep = tools.replay(_v1_log(tmp_path, False))
    assert rep["exact"] and rep["schema"] == tools.SCHEMA_V1 and not rep["decision_changes"], rep


def test_replay_reports_a_refusal_the_new_rule_rejects(tmp_path):
    rep = tools.replay(_v1_log(tmp_path, True))
    assert not rep["exact"]
    assert len(rep["decision_changes"]) == 1 and rep["decision_changes"][0]["now"] == "rejected"
    m = [x for x in rep["mismatches"] if x["tool"] == "submit"][0]
    assert m["field"] == "ok" and "refusal-evidence rule" in m["reason"]


def test_logged_checker_is_found_for_the_identity_alias():
    calls = [dict(ok=True, result=dict(submitted=dict(certificate=dict(verdict="certified", checker="abc"))))]
    assert tools._logged_checker(calls) == "abc"
    assert tools._logged_checker([dict(ok=True, result=dict(x=1))]) is None


def test_static_audit_of_logs():
    recs = [dict(type="session", profile="C", schema="amm-tools/1"),
            dict(type="call", seq=1, tool="set_target", ok=True, args={}, result=dict(targets={"E100_min": 0.5},
                                                                                     normalized={"E100_min": 0.5})),
            dict(type="call", seq=2, tool="search", ok=True, args={}, result=dict(found=False, best=[], objective="pess",
                                                                                 normalized_targets={"E100_min": 0.5})),
            dict(type="call", seq=3, tool="submit", ok=True, args=dict(decision="refuse", verdict="UNDETERMINED"),
                 result=dict(submitted=dict(spec=dict(targets={"E100_min": 0.5}))))]
    a = outcomes.audit_log(recs)
    assert a["rule_applies"] and not a["accepted"] and a["held"][0]["kind"] == "search_not_found"
    recs[3]["args"]["verdict"] = "NOT_FOUND_IN_FAMILIES"
    assert outcomes.audit_log(recs)["accepted"]


# ---- full tensor ---------------------------------------------------------------------------------------------------
def test_tensor_summary_of_isotropic_and_cubic_tensors():
    from amm import homog
    E, nu = 1.0, 0.3
    lam, mu = E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))
    C = np.zeros((6, 6))
    C[:3, :3] = lam
    C[np.arange(3), np.arange(3)] = lam + 2 * mu
    C[3:, 3:] = np.eye(3) * mu
    t = tensor.summary(C)
    assert t["E100"] == pytest.approx(1.0) and t["E111"] == pytest.approx(1.0) and t["E110"] == pytest.approx(1.0)
    assert t["nu12"] == pytest.approx(0.3) and t["bulk_voigt"] == pytest.approx(t["bulk_reuss"])
    C[3:, 3:] = np.eye(3) * 0.2 * mu  # strongly anisotropic cubic: E111 < E100
    t, cc = tensor.summary(C), homog.cubic_constants(C)
    assert t["E100"] == pytest.approx(cc["E100"]) and t["E111"] < t["E100"]


def test_evaluate_exposes_the_full_tensor(tmp_path):
    s = _s(calls=[("set_material", {"name": "PA12"}), ("set_constraints", {"cell_size": 10})])
    out = s.call("evaluate", {"designs": [{"kind": "cube_bars", "params": {"c": 0.6, "w": 0.2}}]})
    assert out["ok"]
    r = out["result"]["results"][0]
    C = np.array(r["C"])
    assert C.shape == (6, 6) and np.allclose(C, C.T)
    assert r["derived"]["E100"] == pytest.approx(r["E100"], rel=1e-12)
    assert r["derived"]["C44"] == pytest.approx(r["G"], rel=1e-12) and min(r["derived"]["eigenvalues"]) > 0
    assert np.allclose(np.array(r["C_MPa"]), C * 1.70e9 / 1e6)
    p = tools.project("evaluate", out["result"], tools.SCHEMA_V1)["results"][0]
    assert not set(tools.V2_EVALUATE_KEYS) & set(p) and p["E100"] == r["E100"]
