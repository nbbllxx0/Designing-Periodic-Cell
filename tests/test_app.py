"""GUI backend (app/) in MOCK mode only: no solver, no CUDA, amm is never imported.

Run: python -m pytest -q tests/test_app.py
"""
from __future__ import annotations

import io
import json
import socket
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import backend as bk, geom, mockdata, outcomes, physics, toolspec  # noqa: E402


@pytest.fixture(scope="module")
def index():
    return bk.RecordedIndex.build()


# ---- contract and mirrors ------------------------------------------------------------------------------------
def test_toolspec_parsed_from_source():
    names = [t["name"] for t in toolspec.tool_specs()]
    assert names[:4] == ["set_material", "set_constraints", "set_target", "set_source"]
    assert {"check_bounds", "evaluate", "search", "certify", "submit", "undo", "get_session"} <= set(names)
    prof = {t["name"]: t["profiles"] for t in toolspec.tool_specs()}
    assert prof["certify"] == ["C"] and prof["check_bounds"] == ["C"] and prof["evaluate"] == ["B", "C"]
    assert set(toolspec.materials()) == {"PA12", "Ti6Al4V", "316L", "AlSi10Mg"}
    fam = toolspec.families()["families"]
    assert sum(len(k) for k in fam.values()) == 9
    assert fam["resonator"]["cube_bars"]["params"] == {"c": [0.30, 0.86], "w": [0.06, 0.36]}
    assert fam["tpms"]["gyroid"]["modes"] == ["network", "sheet"]


def test_mirror_replays_current_code_sessions_exactly(index):
    """Every recorded session written by the current amm tool contract replays through the mock mirror with
    identical results and state hashes (spec tools, certificate keys, submit, undo, budgets). Since B1
    (2026-11-07) that is the current code or the pre-B1 code (schema amm-tools/1 logs, replayed through the
    schema-1 projection with the refusal-evidence rule applied), mockdata.V1_CONTRACT_CODES."""
    same = {k: v for k, v in index.replay_checks.items() if v["replay_compatible"]}
    assert len(same) >= 10
    bad = {k: v for k, v in same.items() if v["n_mismatch"]}
    assert not bad, bad


def test_certificate_keys_match_recorded_files(index):
    """The mirror's cert_key reproduces the file names amm wrote (<spec_hash>_<cert_key>.json)."""
    n = 0
    for sid, meta in mockdata.sessions().items():
        if not meta["replay_compatible"] or not meta["n_certificates"]:
            continue
        s = bk.MockSession(None, profile=meta["profile"])
        files = {p.stem.split("_", 1)[1] for p in (mockdata.session_path(sid).parent / "certificates").glob("*.json")}
        keys = set()
        for rec in mockdata.read_log(mockdata.session_path(sid)):
            if rec.get("type") != "call":
                continue
            if rec["tool"] == "certify" and rec["ok"]:
                keys.add(s.lookup_key("certify", rec["args"]).split(":", 1)[1])
            s.apply_recorded(rec)
        assert keys == files, sid
        n += 1
    assert n >= 3


def test_normalize_mirror():
    t, missing, _ = physics.normalize(dict(material="316L", cell_size=[6, "mm"], E100_min=[31, "GPa"],
                                           gap={"f_lo": [144, "kHz"], "f_hi": [304, "kHz"]}))
    assert not missing
    assert t["E100_min"] == pytest.approx(31e9 / 193e9)
    m = toolspec.materials()["316L"]
    assert t["gap"]["f_lo"] == pytest.approx(144e3 * 6e-3 / physics.c_t(m))
    t, missing, _ = physics.normalize(dict(E100_min=[1, "GPa"]))
    assert "E100_min" not in t and missing


def test_cubic_helpers():
    # isotropic: C44 = (C11 - C12) / 2 -> E(n) constant = E
    E, nu = 1.0, 0.3
    lam, mu = E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))
    s = physics.cubic_summary(lam + 2 * mu, lam, mu)
    assert s["E100"] == pytest.approx(1.0) and s["E111"] == pytest.approx(1.0) and s["zener"] == pytest.approx(1.0)
    assert s["nu100"] == pytest.approx(0.3)
    n = np.random.default_rng(0).normal(size=(50, 3))
    assert np.allclose(physics.young_directional(lam + 2 * mu, lam, mu, n), 1.0)


def test_gap_mirror_against_atlas_rows():
    rows = [r for r in mockdata.atlas(0.3) if r.get("bloch_valid") and r.get("gaps")][:40]
    assert rows
    for r in rows:
        mine = physics.complete_gaps(r["bands"])
        assert [round(g["f_lo"], 6) for g in mine[:len(r["gaps"])]] == [round(g["f_lo"], 6) for g in r["gaps"]]
    assert physics.kpath_ticks(len(rows[0]["bands"]))[-1] == (20, "X")


def test_preview_geometry_and_stl():
    m = geom.mask("gyroid", dict(density=0.3, mode="network"), 32)
    assert abs(m.mean() - 0.3) < 0.01
    v, f = geom.boundary_mesh(m)
    data = geom.stl_bytes(v, f, scale=6.0, tiles=2)
    assert len(data) == 84 + 50 * len(f) * 8
    p = geom.preview("cube_bars", dict(c=0.5, w=0.2), 24)
    assert len(p["faces"]) % 3 == 0 and p["vertices"]


def test_outcome_cards_cover_five_outcomes(index):
    seen = set()
    for sid in ("pilot/C/G01", "pilot/C/X07", "pilot/C/N02", "pilot/C/M01", "pilot/C/A04"):
        s = bk.MockSession(None, profile="C")
        for rec in mockdata.read_log(mockdata.session_path(sid)):
            if rec.get("type") == "call":
                s.apply_recorded(rec)
        calls = [r for r in s.records if r.get("type") == "call"]
        c = outcomes.cards(calls, s.submission, s.normalized(strict=False)[0])
        assert [x["id"] for x in c["cards"]] == [o[0] for o in outcomes.OUTCOMES]
        if c["submitted_outcome"]:
            seen.add(c["submitted_outcome"])
        if sid.endswith("A04"):
            assert c["need_info"]
    assert {"certified", "proven_infeasible", "not_found", "undetermined"} <= seen


def test_mock_unrecorded_solver_call_fails_cleanly(tmp_path, index):
    s = bk.MockSession(tmp_path, index=index)
    assert s.call("set_material", dict(name="316L"))["ok"]
    assert s.call("set_target", dict(E100_min=dict(value=0.01234, unit="E_s")))["ok"]
    out = s.call("certify", dict(design=dict(kind="sc", params=dict(r=0.1, R=0.0))))
    assert not out["ok"] and "mock mode" in out["error"]
    out = s.call("evaluate", dict(designs=[dict(kind="sc", params=dict(r=0.1, R=0.0))]))
    assert out["ok"] and out["mock_source"]["kind"] == "atlas"
    assert s.call("undo")["ok"] and s.state["targets"] == {}
    assert (tmp_path / "session.jsonl").is_file()


# ---- server (mock) over HTTP -----------------------------------------------------------------------------------
def _free_port():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn

    from app import server as srv
    be = srv.build_backend("mock", tmp_path_factory.mktemp("gui"))
    port = _free_port()
    cfg = uvicorn.Config(srv.create_app(be), host="127.0.0.1", port=port, log_level="error")
    us = uvicorn.Server(cfg)
    th = threading.Thread(target=us.run, daemon=True)
    th.start()
    for _ in range(100):
        if us.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", be
    us.should_exit = True
    th.join(5)


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read())


def _post(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as ex:
        return ex.code, json.loads(ex.read())


def test_server_rest_flow(server):
    base, be = server
    h = _get(base, "/api/health")
    assert h["ok"] and h["mode"] == "mock" and h["worker"]["alive"]
    assert len(_get(base, "/api/tools")["tools"]) == len(toolspec.tool_specs())
    rec = _get(base, "/api/recorded")["sessions"]
    assert any(s["id"] == "pilot/C/G01" for s in rec)
    st, summ = _post(base, "/api/recorded/load", dict(id="pilot/C/G01"))
    assert st == 200 and summ["submission"]["decision"] == "release"
    assert summ["evidence"]["submitted_outcome"] == "certified"
    d = summ["focus"]
    st, det = _post(base, "/api/details", dict(design=d))
    assert st == 200 and det["certificate"]["verdict"] == "certified"
    assert det["certificate"]["bloch"]["margins"]["lower"] > 0
    assert det["search"]["cubic"]["E100"] > 0 and det["search"]["ticks"]
    # new session: spec tools at once, solver tools via the queue
    _post(base, "/api/session/new", dict(profile="C"))
    st, out = _post(base, "/api/tools/set_material", dict(args=dict(name="Ti6Al4V")))
    assert st == 200 and out["ok"] and out["result"]["nu"] == 0.342
    st, out = _post(base, "/api/tools/set_target", dict(args=dict(density_max=0.3, G_min=dict(value=6, unit="GPa"))))
    assert out["ok"] and out["result"]["normalized"]["G_min"] == pytest.approx(6e9 / 113.8e9)
    st, out = _post(base, "/api/tools/evaluate", dict(args=dict(designs=[d]), wait=True))
    assert out["job"]["status"] == "done" and out["job"]["output"]["ok"]
    st, out = _post(base, "/api/tools/certify", dict(args=dict(design=d), wait=True))
    assert out["job"]["status"] == "failed" and "mock mode" in out["job"]["output"]["error"]
    st, out = _post(base, "/api/tools/set_target", dict(args=dict(bogus=1)))
    assert not out["ok"] and "bogus" in out["error"]
    s = _get(base, "/api/session")
    assert s["seq"] == 5 and [r["tool"] for r in s["log"] if r["type"] == "call"][-1] == "set_target"
    assert _get(base, "/api/jobs")["jobs"]
    pv = _get(base, "/api/preview?kind=gyroid&params=%7B%22density%22%3A0.3%2C%22mode%22%3A%22sheet%22%7D&n=16")
    assert pv["faces"]
    at = _get(base, "/api/atlas?nu=0.342&limit=50")
    assert at["available"] and len(at["points"]) == 50


def test_server_export_and_download(server):
    base, be = server
    _post(base, "/api/recorded/load", dict(id="smoke/codex-C-r1-S01"))
    st, ex = _post(base, "/api/export", dict(tiles=2, n=24))
    assert st == 200 and ex["name"].endswith(".zip")
    with urllib.request.urlopen(base + ex["url"], timeout=30) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    names = set(z.namelist())
    assert {"cell.stl", "tiled_2x2x2.stl", "report.json", "session.jsonl"} <= names
    assert any(n.startswith("certificate_") for n in names)
    rep = json.loads(z.read("report.json"))
    assert rep["mode"] == "mock" and rep["evidence"]["submitted_outcome"] == "certified"
    assert rep["geometry"]["unit"] in ("mm", "cell units (a = 1)")
    st, _ = _post(base, "/api/export", dict(design=dict(kind="sc", params=dict(r=0.5, R=0))))
    assert st == 400
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(base + "/api/files/..%2Fsession.jsonl", timeout=10)


def test_server_event_stream_and_queue(server):
    base, be = server
    got = []

    def listen():
        with urllib.request.urlopen(base + "/api/events", timeout=20) as r:
            for line in r:
                line = line.decode().strip()
                if line.startswith("data: "):
                    got.append(json.loads(line[6:]))
                    if sum(1 for e in got if e.get("type") == "job" and e["job"]["status"] == "done") >= 1:
                        return

    th = threading.Thread(target=listen, daemon=True)
    th.start()
    time.sleep(0.5)
    _post(base, "/api/session/new", dict(profile="C"))
    _post(base, "/api/tools/set_material", dict(args=dict(name="316L")))
    st, out = _post(base, "/api/tools/evaluate", dict(args=dict(designs=[dict(kind="octet", params=dict(r=0.08, R=0))])))
    assert out["job"]["status"] in ("queued", "running", "done")
    th.join(20)
    types = [e["type"] for e in got]
    assert types[0] == "hello" and "record" in types and "job" in types
    states = [e["job"]["status"] for e in got if e["type"] == "job"]
    assert states[0] == "queued" and states[-1] == "done"


def test_one_worker_runs_jobs_in_order(tmp_path):
    be = bk.MockBackend(tmp_path, delay_scale=0.0)
    be.call("set_material", dict(name="316L"))
    jobs = [be.call("evaluate", dict(designs=[dict(kind="sc", params=dict(r=0.05 + 0.01 * i, R=0.0))]))["job"]
            for i in range(4)]
    done = [be.queue.wait(j["id"], 30) for j in jobs]
    assert [d["status"] for d in done] == ["done"] * 4
    starts = [d["t_start"] for d in done]
    ends = [d["t_end"] for d in done]
    assert all(ends[i] <= starts[i + 1] for i in range(3))  # never two at once
    assert be.queue.worker.is_alive()


def test_mock_mode_never_imports_amm_or_gpu(tmp_path):
    """In a fresh interpreter (other test files may import amm): build the mock backend and app, load a recorded
    session, evaluate and export; amm, cupy and torch must stay unimported."""
    import subprocess
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from app import server as srv\n"
        "be = srv.build_backend('mock', __import__('pathlib').Path(%r))\n"
        "srv.create_app(be)\n"
        "be.load_recorded('pilot/C/G01')\n"
        "be.call('evaluate', {'designs': [be.summary()['focus']]}, wait=True)\n"
        "be.details(be.summary()['focus']); be.export(n=16, tiles=1)\n"
        "bad = [m for m in sys.modules if m == 'amm' or m.startswith('amm.') or m in ('cupy', 'torch', 'pypardiso')]\n"
        "print('BAD', bad)\n" % (str(ROOT), str(tmp_path)))
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "BAD []" in out.stdout, out.stdout


# ---- live-mode plumbing that mock mode shares (2026-11-08): B1 view, full C*, progress/cancel, request guards ----
def test_b1_view_of_a_mock_session(tmp_path, index):
    """The amm-outcome/1 view: evidence records with the outcome they support and whether they hold for the current
    spec; the refusal rule (taken from amm/outcomes.py) rejects a refusal without evidence and the rejection is
    reported; a refusal citing a held bound record gets the proven_infeasible card."""
    be = bk.MockBackend(tmp_path)
    be.call("set_material", dict(name="Ti6Al4V"))
    be.call("set_target", dict(density_max=0.2, E100_min=dict(value=0.5, unit="E_s")))
    out = be.call("submit", dict(decision="refuse", verdict="PROVEN_INFEASIBLE"))
    assert not out["ok"] and out["error"].startswith("refusal needs evidence: ")
    v = be.summary()["outcome"]
    assert v["schema"] == "amm-outcome/1" and v["evidence_checked"] and v["card"] is None
    assert [g["id"] for g in v["groups"]] == list(outcomes.OUTCOME_ORDER)
    assert v["last_rejected_submit"]["refusal_rule"] and v["can_cite"]["PROVEN_INFEASIBLE"] == []
    # a W1 rejection (gap containing f = 0) is itself a bound record (B1): held while no gap target is set
    be.call("set_target", dict(gap=dict(f_lo=0.0, f_hi=0.2, unit="f*")))
    v = be.summary()["outcome"]
    w1 = [r for r in v["records"] if r["kind"] == "bound_violation"]
    assert w1 and w1[0]["holds"] and v["can_cite"]["PROVEN_INFEASIBLE"] == [w1[0]["seq"]]
    out = be.call("submit", dict(decision="refuse", verdict="PROVEN_INFEASIBLE"))
    assert out["ok"], out
    v = be.summary()["outcome"]
    assert v["card"]["outcome"] == "proven_infeasible" and v["card"]["evidence"][0]["seq"] == w1[0]["seq"]
    assert v["last_rejected_submit"] is None and v["submit_seq"] == out["seq"]


def test_full_tensor_view_and_mirror_of_amm_tensor_summary(tmp_path, index):
    be = bk.MockBackend(tmp_path)
    be.call("set_material", dict(name="316L"))
    det = be.details(dict(kind="octet", params=dict(r=0.08, R=0.0)))
    t = det["search"]["tensor"]
    assert t["kind"] == "cubic" and np.asarray(t["C"]).shape == (6, 6)
    cub = det["search"]["cubic"]
    for k in ("E100", "E110", "E111"):
        assert t["derived"][k] == pytest.approx(cub[k], rel=1e-10)
    s = physics.tensor_summary(physics.voigt_cubic(1.0, 0.4, 0.3))
    assert s["bulk_voigt"] == pytest.approx(s["bulk_reuss"]) == pytest.approx(0.6)
    assert s["eigenvalues"][-1] == pytest.approx(1.8)


def test_running_job_progress_and_cancel_mock(tmp_path):
    """A running job is cancelled cooperatively; nothing is logged for it (mock: the replay delay is waited before
    the call)."""
    be = bk.MockBackend(tmp_path, delay_scale=1.0, delay_cap=20.0)
    be.load_recorded("pilot/C/G01")  # its certify call took minutes: replayed with a 20 s delay
    seq, used = be.session.seq, dict(be.session.used)
    ev = []
    be.bus.listeners.append(ev.append)
    d = be.summary()["focus"]
    j = be.call("certify", dict(design=d))["job"]
    for _ in range(250):
        if be.queue.jobs[j["id"]].get("progress"):
            break
        time.sleep(0.02)
    assert be.queue.jobs[j["id"]]["status"] == "running"
    assert be.queue.cancel(j["id"])
    done = be.queue.wait(j["id"], 30)
    assert done["status"] == "cancelled" and "rolled back" in done["output"]["error"]
    assert done["t_end"] - done["t_start"] < 10
    assert be.session.seq == seq and be.session.used == used
    assert any(e["type"] == "progress" for e in ev)
    assert not be.queue.cancel(j["id"])  # finished jobs cannot be cancelled


def test_server_request_guards(server):
    base, be = server
    req = urllib.request.Request(base + "/api/tools/get_session", data=b"args=", method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(req, timeout=10)
    assert ei.value.code == 415
    req = urllib.request.Request(base + "/api/health", headers={"Host": "evil.example:80"})
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(req, timeout=10)
    assert ei.value.code == 403
    h = _get(base, "/api/health")
    assert h["lock"]["used"] is False
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(base + "/api/session-files/..%2F..%2Fsession.jsonl", timeout=10)
    s = _get(base, "/api/session")
    assert s["exports"] == [] and s["outcome"]["schema"] == "amm-outcome/1"
