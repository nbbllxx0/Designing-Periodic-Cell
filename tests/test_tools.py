"""Tool contract: validation, logging, undo, release gating and exact LLM-free replay (amm.tools)."""
import json

from amm import outcomes, tools


def answer_pa12(question, options):
    for i, o in enumerate(options):
        if o["set"].get("material") == "PA12":
            return dict(choice=i, label=o["label"], comment="")
    return dict(choice=None, label=None, comment="The part is SLS-printed PA12.")


def run_session(root, profile="C"):
    s = tools.Session(root, profile=profile, answerer=answer_pa12)
    c = s.call
    assert not c("set_target", {"E100_min": {"value": 5, "unit": "MPa"}, "bogus": 1})["ok"]       # extra key
    assert c("set_target", {"E100_min": {"value": 5, "unit": "MPa"}, "density_max": 0.3})["ok"]
    r = c("ask_clarification", {"question": "Which material?", "options": [
        {"label": "PA12 (SLS)", "set": {"material": "PA12"}}, {"label": "Ti-6Al-4V", "set": {"material": "Ti6Al4V"}}]})
    assert r["ok"] and r["result"]["answer"]["choice"] == 0
    assert c("set_material", {"name": "PA12"})["ok"]
    assert c("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"})["ok"]
    assert c("set_source", {"key": "material", "source": "answered"})["ok"]
    assert not c("evaluate", {"designs": [{"kind": "sc", "params": {"r": 0.5, "R": 0}}]})["ok"]      # outside box
    e = c("evaluate", {"designs": [{"kind": "cube_bars", "params": {"c": 0.6, "w": 0.2}},
                                   {"kind": "gyroid", "params": {"density": 0.2, "mode": "sheet"}}]})
    assert e["ok"] and len(e["result"]["results"]) == 2 and "E100_MPa" in e["result"]["results"][0]
    assert e["result"]["results"][0]["gaps"] and e["result"]["results"][0]["gaps_Hz"]  # known gap former
    assert c("set_target", {"density_max": 0.25})["ok"]
    assert c("undo")["ok"]
    assert s.state["targets"]["density_max"] == 0.3
    rel = c("submit", {"decision": "release", "design": {"kind": "sc", "params": {"r": 0.1, "R": 0.2}}})
    assert rel["ok"] is (profile == "B")         # C refuses an uncertified release
    if profile == "C":
        assert "certify first" in rel["error"]
        # B1: a refusal must cite evidence held in the session; none is held yet
        bad = c("submit", {"decision": "refuse", "verdict": "OTHER", "note": "test"})
        assert not bad["ok"] and bad["error"].startswith(outcomes.REFUSAL_ERROR)
        # a gap containing f = 0 is rejected on input (bound W1): that rejection is a bound record
        assert not c("set_target", {"gap": {"f_lo": 0, "f_hi": 2, "unit": "kHz"}})["ok"]
        ok = c("submit", {"decision": "refuse", "verdict": "OTHER", "note": "test"})
        assert ok["ok"] and ok["result"]["outcome_card"]["outcome"] == "proven_infeasible"
        assert ok["result"]["submitted"]["evidence"] == [dict(seq=13, tool="set_target", kind="bound_violation")]
    return s


def test_contract_and_exact_replay(tmp_path):
    run_session(tmp_path / "c")
    log = tools.read_log(tmp_path / "c" / "session.jsonl")
    assert log[0]["type"] == "session" and sum(r["type"] == "call" for r in log) == 14
    assert log[0]["schema_version"] == tools.SCHEMA_VERSION and all(r["schema_version"] == tools.SCHEMA_VERSION
                                                                    for r in log[1:])
    rep = tools.replay(tmp_path / "c" / "session.jsonl", root=tmp_path / "replay")
    assert rep["exact"], rep["mismatches"]
    assert rep["n_compared"] == 14 and rep["schema"] == tools.SCHEMA_VERSION and not rep["decision_changes"]


def test_profile_b_has_no_certificates(tmp_path):
    s = run_session(tmp_path / "b", profile="B")
    assert "certify" not in s.tools() and "check_bounds" not in s.tools()
    assert not s.call("certify", {"design": {"kind": "sc", "params": {"r": 0.1, "R": 0.2}}})["ok"]
    assert tools.replay(tmp_path / "b" / "session.jsonl")["exact"]


def test_replay_detects_a_changed_result(tmp_path):
    run_session(tmp_path / "c")
    p = tmp_path / "c" / "session.jsonl"
    recs = tools.read_log(p)
    for r in recs:
        if r.get("tool") == "evaluate" and r["ok"]:
            r["result"]["results"][0]["E100"] *= 1.01
            del r["result_hash"]
            break
    rep = tools.replay(recs)
    assert not rep["exact"] and rep["mismatches"][0]["field"] == "result"
    assert "E100" in rep["mismatches"][0]["diff"]["path"]


def test_tool_schemas_are_json_serializable():
    for name, t in tools.TOOLS.items():
        json.dumps(t["model"].model_json_schema())


def test_mcp_server_exposes_the_profile_tools(tmp_path):
    from amm import mcp_server
    for prof in ("B", "C"):
        s = tools.Session(tmp_path / prof, profile=prof)
        srv = mcp_server.build_server(s)
        names = {t.name for t in srv._tool_manager.list_tools()}
        assert names == set(s.tools())
        assert ("certify" in names) is (prof == "C")


def test_oracle_answers_from_the_intended_spec():
    from amm import bench
    o = bench.Oracle(dict(intended=dict(material="316L", cell_size=[10, "mm"],
                                        targets=dict(gap={"f_lo": [100, "kHz"], "f_hi": [195, "kHz"]})),
                          oracle=dict(facts="316L steel.")))
    assert o("Material?", [dict(label="Ti", set=dict(material="Ti6Al4V")),
                           dict(label="316L", set=dict(material="316-L"))])["choice"] == 1
    assert o("Cell?", [dict(label="1 cm", set=dict(cell_size=[1, "cm"]))])["choice"] == 0
    a = o("Gap?", [dict(label="2-3 kHz", set=dict(gap={"f_lo": 2, "f_hi": 3, "unit": "kHz"}))])
    # after a matching answer the missing item is settled: the oracle no longer restates it (pilot A04)
    assert a["choice"] is None and a["comment"] == bench.NEUTRAL
    fresh = bench.Oracle(dict(intended=o.intended, oracle=dict(facts="316L steel.")))
    assert fresh("Gap?", [dict(label="2-3 kHz", set=dict(gap={"f_lo": 2, "f_hi": 3, "unit": "kHz"}))])["comment"] == "316L steel."
