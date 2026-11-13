"""E4 harness (audit 2026-11-06, F03): arm D logging, arm O on the oracle spec, run records, partition. No LLM."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "bench"))
import scoring  # noqa: E402
from amm import bench, tools  # noqa: E402


def brief(bid):
    return json.loads((ROOT / "bench" / "v1" / "briefs" / f"{bid}.json").read_text(encoding="utf-8"))


def test_intended_tool_args_reproduce_the_intended_request(tmp_path):
    for bid in ("G01", "M01", "S01", "X01", "A05"):
        b = brief(bid)
        a = bench.intended_tool_args(b["intended"])
        s = tools.Session(None, profile="C")
        assert s.call("set_material", {"name": a["material"]})["ok"]
        if a["constraints"]:
            assert s.call("set_constraints", a["constraints"])["ok"]
        assert s.call("set_target", a["targets"])["ok"]
        norm, _ = s.normalized()
        assert scoring._close(norm, scoring.intended_normalized(b), 1e-9), bid


def test_direct_answer_is_logged_through_the_tool_contract(tmp_path):
    b = brief("S01")
    a = bench.intended_tool_args(b["intended"])
    ans = dict(decision="release", material=a["material"], cell_size=None, targets=a["targets"],
               design=dict(kind="gyroid", params=dict(density=0.3, mode="sheet")), note="from memory")
    txt = "Here is my answer:\n" + json.dumps(ans)
    s = tools.Session(tmp_path / "session", profile="B")
    bench._log_direct_answer(s, bench._last_json(txt))
    r = scoring.score_session(b, tmp_path, certify_releases=False)
    assert r["decision"] == "release" and r["spec_ok"] and r["outcome"] == "pending"


def test_run_brief_always_writes_a_record(tmp_path):
    p = tmp_path / "request.json"
    p.write_text(json.dumps(bench.load_brief(ROOT / "bench" / "v1" / "briefs" / "S01.json")), encoding="utf-8")
    rec = bench.run_brief(p, tmp_path / "job", profile="Z")
    assert rec["status"] == "error" and "unknown arm" in rec["error"]
    assert (tmp_path / "job" / "run.json").exists()


def test_baseline_refuses_a_proven_infeasible_brief_without_a_solve(tmp_path):
    b = brief("X01")
    p = tmp_path / "request.json"
    p.write_text(json.dumps(dict(text=b["text"], intended=b["intended"], oracle=b["oracle"])), encoding="utf-8")
    rec = bench.run_brief(p, tmp_path / "job", profile="O")
    assert rec["status"] == "done", rec
    r = scoring.score_session(b, tmp_path / "job", certify_releases=False)
    assert r["outcome"] == "correct_refusal" and r["verdict_match"] == "exact" and r["correct"]


def test_partition_matches_the_audit_counts():
    import e4
    b = e4.load_briefs()
    part = e4.partition(b)
    conf = [i for i in b if part[i] == "confirmatory"]
    assert len(conf) == 78 and len({scoring.spec_key(b[i]) for i in conf}) == 61
    assert all(part[i] == "development" for i in ("S01", "R01", "A04"))


def test_deidentified_request_has_no_label():
    import e4
    d = e4.deidentified(brief("X01"))
    assert set(d) == {"text", "intended", "oracle"} and "X01" not in json.dumps(d)


def test_gpu_busy_ignores_own_process(monkeypatch):
    """Arm O runs the solver in the runner: its own CUDA context must not block the next job (smoke 2026-11-06)."""
    import os
    import subprocess
    import sys as _s
    from pathlib import Path as _P
    _s.path.insert(0, str(_P(__file__).resolve().parents[1] / "scripts" / "bench"))
    import e4

    class R:
        returncode = 0
        stdout = f"{os.getpid()}, C:\envs\amm\python.exe\n123, C:\Windows\explorer.exe\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert e4.gpu_busy() == []
    R.stdout += "999999, C:\other\python.exe\n"
    assert e4.gpu_busy() == ["999999, C:\other\python.exe"]


def _e4(monkeypatch, tmp_path):
    import sys as _s
    from pathlib import Path as _P
    _s.path.insert(0, str(_P(__file__).resolve().parents[1] / "scripts" / "bench"))
    import e4
    monkeypatch.setattr(e4, "WS_ROOT", tmp_path / "ws")
    return e4


def test_second_runner_refused(monkeypatch, tmp_path):
    e4 = _e4(monkeypatch, tmp_path)
    import pytest
    with e4.GpuLock("first", name="e4_runner.lock", wait=False):
        with pytest.raises(SystemExit):
            with e4.GpuLock("second", name="e4_runner.lock", wait=False):
                pass
    with e4.GpuLock("third", name="e4_runner.lock", wait=False):  # released: a new runner may start
        pass


def test_finished_workspace_without_job_fields_is_recovered_not_rerun(monkeypatch, tmp_path):
    """run_brief writes run.json at the end; an interruption before E4 adds the job fields must not cause a rerun."""
    import json as _j
    e4 = _e4(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    (root / "results" / "bench" / "t").mkdir(parents=True)
    job = dict(job="codex-B-r1-S01", provider="codex", arm="B", rep=1, brief="S01", partition="development",
               order=0, workspace="abc123")
    monkeypatch.setattr(e4, "ROOT", root)
    monkeypatch.setattr(e4, "load_jobs", lambda tag: [job])
    monkeypatch.setattr(e4, "select", lambda jobs: jobs)
    monkeypatch.setattr(e4, "check_frozen", lambda tag, log: dict(code="x"))
    monkeypatch.setattr(e4, "load_briefs", lambda: {})
    called = []
    monkeypatch.setattr(e4.bench, "run_brief", lambda *a, **k: called.append(1) or {})
    ws = e4.WS_ROOT / "t" / "abc123"
    ws.mkdir(parents=True)
    (ws / "run.json").write_text(_j.dumps(dict(status="done", wall_s=12.0)), encoding="utf-8")
    e4._run("t")
    rec = _j.loads((root / "results" / "bench" / "t" / "jobs" / "codex-B-r1-S01" / "run.json").read_text())
    assert not called and rec["recovered"] and rec["job"] == "codex-B-r1-S01" and rec["status"] == "done"


def test_plan_writes_manifest_with_full_identity(monkeypatch, tmp_path):
    """plan() must run (a duplicate keyword once broke it) and freeze every identity field checked by run."""
    import json as _j
    import shutil as _sh
    import sys as _s
    from pathlib import Path as _P
    _s.path.insert(0, str(_P(__file__).resolve().parents[1] / "scripts" / "bench"))
    import e4
    monkeypatch.setattr(e4, "snapshot", lambda d: None)
    monkeypatch.setattr(_s, "argv", ["e4.py", "plan", "--tag", "_pytest_plan"])
    out = e4.ROOT / "results" / "bench" / "_pytest_plan"
    try:
        e4.plan()
        meta = _j.loads((out / "jobs.json").read_text(encoding="utf-8"))["meta"]
        assert set(e4.identity()) <= set(meta) and meta["n_jobs"] == 1379
        assert {k: meta[k] for k in e4.identity()} == e4.identity()
    finally:
        _sh.rmtree(out, ignore_errors=True)


# ---- amendment A1 (2026-11-07) -----------------------------------------------------------------------------------
def test_a1_changes_only_the_harness_file_against_the_plan_time_source():
    """The real tree: after A1 only scripts/bench/e4.py of scripts/bench may differ from the E4 source zip. amm/
    may differ only once E4 has been scored (plan section 8: V5c, then B1-B3 edit amm/; 2026-11-07)."""
    import sys as _s
    from pathlib import Path as _P
    _s.path.insert(0, str(_P(__file__).resolve().parents[1] / "scripts" / "bench"))
    import e4
    changed = e4.changed_source_files("e4")
    assert [f for f in changed if not f.startswith("amm/")] == ["scripts/bench/e4.py"]
    if any(f.startswith("amm/") for f in changed):
        assert (e4.ROOT / "results" / "bench" / "e4" / "RESULT_A2.md").is_file()  # E4 scored before amm changed


def test_a1_override_is_narrow(monkeypatch, tmp_path):
    import pytest
    e4 = _e4(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    (root / "results" / "bench" / "t").mkdir(parents=True)
    monkeypatch.setattr(e4, "ROOT", root)
    monkeypatch.setattr(e4, "harness_hash", lambda: "h")
    meta, now, log = dict(code="c", checker="k"), dict(code="c", checker="k", full_source="f2", prereg="p2"), print
    monkeypatch.setattr(e4, "changed_source_files", lambda tag: ["scripts/bench/e4.py"])
    rec = e4.check_amendment("t", "A1", meta, now, {"full_source": 1, "prereg": 1}, log)
    assert rec["changed_files"] == ["scripts/bench/e4.py"]
    assert (root / "results" / "bench" / "t" / "amendments" / "A1.json").exists()
    monkeypatch.setattr(e4, "changed_source_files", lambda tag: ["amm/tools.py", "scripts/bench/e4.py"])
    with pytest.raises(SystemExit):
        e4.check_amendment("t", "A1", meta, now, {"full_source": 1}, log)
    monkeypatch.setattr(e4, "changed_source_files", lambda tag: [])
    with pytest.raises(SystemExit):
        e4.check_amendment("t", "A1", meta, now, {"checker": 1}, log)


def test_quota_event_only_for_abnormal_ends_with_a_limit_message(monkeypatch, tmp_path):
    e4 = _e4(monkeypatch, tmp_path)
    ws = tmp_path / "w"
    (ws / "codex").mkdir(parents=True)
    (ws / "codex" / "stderr.txt").write_text("stream error: 429 Too Many Requests, retrying", encoding="utf-8")
    ok = dict(status="done", returncode=0, final='{"decision": "release"}')
    assert e4.quota_event(ws, ok) is None  # transient retry inside a finished session
    assert e4.quota_event(ws, dict(status="done", returncode=1, final="")) is not None
    (ws / "codex" / "stderr.txt").write_text("", encoding="utf-8")
    assert e4.quota_event(ws, dict(status="timeout", returncode=-9, final="")) is None  # plain timeout stays final
    (ws / "codex" / "events.jsonl").write_text('{"type":"error","message":"You\'ve hit your usage limit."}\n'
                                               '{"type":"item.completed","text":"quota of 429 designs"}\n',
                                               encoding="utf-8")
    assert "usage limit" in e4.quota_event(ws, dict(status="done", returncode=1, final=""))
    (ws / "codex" / "events.jsonl").write_text('{"type":"item.completed","text":"rate limit 429"}\n', encoding="utf-8")
    assert e4.quota_event(ws, dict(status="done", returncode=1, final="")) is None  # agent text is not a channel


def test_quota_interruption_is_kept_not_scored_and_stops(monkeypatch, tmp_path):
    import json as _j
    import pytest
    e4 = _e4(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    (root / "results" / "bench" / "t").mkdir(parents=True)
    job = dict(job="codex-B-r1-S01", provider="codex", arm="B", rep=1, brief="S01", partition="confirmatory",
               order=0, workspace="abc123")
    monkeypatch.setattr(e4, "ROOT", root)
    monkeypatch.setattr(e4, "load_jobs", lambda tag: [job])
    monkeypatch.setattr(e4, "select", lambda jobs: jobs)
    monkeypatch.setattr(e4, "check_frozen", lambda tag, log: dict(code="x"))
    monkeypatch.setattr(e4, "load_briefs", lambda: {"S01": dict(text="t", intended={}, oracle={})})
    monkeypatch.setattr(e4, "wait_gpu", lambda log: 0.0)

    def fake_run(req, ws, **k):
        (ws / "codex").mkdir(parents=True)
        (ws / "codex" / "stderr.txt").write_text("ERROR: You've hit your usage limit. Try again later.")
        (ws / "run.json").write_text("{}")
        return dict(status="done", returncode=1, final="", wall_s=3.0)
    monkeypatch.setattr(e4.bench, "run_brief", fake_run)
    with pytest.raises(SystemExit) as ex:
        e4._run("t")
    assert ex.value.code == 3
    out = root / "results" / "bench" / "t"
    assert not (out / "jobs" / "codex-B-r1-S01").exists()  # not a scored answer; rerun after the reset
    att = list((out / "attempts").iterdir())
    assert len(att) == 1 and "_infra_" in att[0].name and not (att[0] / "run.json").exists()
    assert _j.loads((att[0] / "infra.json").read_text())["status"] == "infra_interruption"


def test_cut_phase_refused_under_a1(monkeypatch, tmp_path):
    import pytest
    import sys as _s
    e4 = _e4(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    (root / "results" / "bench" / "t").mkdir(parents=True)
    monkeypatch.setattr(e4, "ROOT", root)
    monkeypatch.setattr(e4, "load_jobs", lambda tag: [])
    monkeypatch.setattr(e4, "check_frozen", lambda tag, log: dict(code="x"))
    monkeypatch.setattr(e4, "load_briefs", lambda: {})
    monkeypatch.setattr(_s, "argv", ["e4.py", "run", "--tag", "t", "--phase", "2", "--amendment", "A1"])
    with pytest.raises(SystemExit, match="cut by amendment"):
        e4._run("t")
