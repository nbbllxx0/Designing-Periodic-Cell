"""B9 fixes (results/software/NOTES_B9.md): transactional calls and cancel rollback (G2), the progress / cancel hook
(G3), read-only calls during a solve (G4), evaluate bands and schema amm-tools/3 (G5), PARDISO free in a finally
(G6), replay of export records with the default root (G1), the data location through amm.data (B6-1) and the
messages for missing data (B6-2, B6-3)."""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

import numpy as np
import pytest

import amm  # noqa: F401  (amm before torch)
from amm import atlas, bloch, certify, data, fem, progress, tools

ROOT = Path(__file__).resolve().parents[1]
SC = {"kind": "sc", "params": {"r": 0.12, "R": 0.0}}
SMALL_EXPORT = {"design": SC, "tiles": 1, "resolution": 24, "tile_resolution": 16}


def _spec_session(root=None, schema=tools.SCHEMA_VERSION):
    s = tools.Session(root, schema=schema)
    assert s.call("set_material", {"name": "PA12"})["ok"]
    assert s.call("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"})["ok"]
    assert s.call("set_target", {"E100_min": {"value": 25, "unit": "MPa"}, "density_max": 0.25})["ok"]
    return s


def _calls(path):
    return [r for r in tools.read_log(path) if r.get("type") == "call"]


# ---- G2: transactional calls --------------------------------------------------------------------------------------
def test_cancel_rolls_the_call_back_and_writes_nothing(tmp_path):
    s = _spec_session(tmp_path / "s")
    before = (s.seq, dict(s.used), s.state_hash(), len(s.evidence), len(_calls(s.log_path)))
    ev = threading.Event()
    ev.set()
    with pytest.raises(progress.Cancelled):  # the certificate stops at its first checkpoint
        s.call("certify", {"design": SC}, cancel=ev)
    assert (s.seq, dict(s.used), s.state_hash(), len(s.evidence), len(_calls(s.log_path))) == before
    assert s._inflight is None and not s.certs


def test_keyboard_interrupt_inside_a_tool_is_rolled_back(tmp_path, monkeypatch):
    s = _spec_session(tmp_path / "s")
    seq, used, n = s.seq, dict(s.used), len(_calls(s.log_path))

    def interrupted(self, designs, bands=False):
        self._spend("designs", len(designs))  # budget spent, then interrupted
        raise KeyboardInterrupt

    monkeypatch.setitem(tools.TOOLS["evaluate"], "fn", interrupted)
    with pytest.raises(KeyboardInterrupt):
        s.call("evaluate", {"designs": [SC]})
    assert s.seq == seq and s.used == used and len(_calls(s.log_path)) == n
    monkeypatch.undo()
    assert s.call("get_session")["seq"] == seq + 1  # the number is reused: no gap, no duplicate
    assert tools.replay(s.log_path)["exact"]


# ---- G3: progress and cancel hook ---------------------------------------------------------------------------------
CERT_KW = dict(res_bloch=(8, 10), static_ladder=((8, 10, 12),), as_built=False, nu=0.3)


def _strip(c):
    return tools.strip_volatile(json.loads(tools.canon(c)))


def test_progress_hook_reports_and_never_changes_the_certificate():
    spec = dict(family="struts", kind="sc", params=dict(r=0.12, R=0.0))
    t = dict(E100_min=0.01, density_max=0.2)
    assert not progress.active()
    plain = certify.certify(spec, t, **CERT_KW)
    seen = []
    with progress.hooks(progress=seen.append):
        hooked = certify.certify(spec, t, **CERT_KW)

    def broken(info):  # a broken progress display: swallowed, the verdict is not touched
        raise RuntimeError("display bug")

    with progress.hooks(progress=broken):
        hooked2 = certify.certify(spec, t, **CERT_KW)
    assert _strip(plain) == _strip(hooked) == _strip(hooked2)
    stages = [x["stage"] for x in seen]
    assert stages.count("certificate: static solve") == 15  # 3 resolutions x 5 grid phases
    assert stages[0] == "certificate: static rung" and seen[1]["n"] == 8


def test_cancel_inside_the_fail_closed_bloch_block_is_not_a_verdict():
    """bloch_block turns any Exception into an undetermined verdict; a cancel must not become one."""
    spec = dict(family="struts", kind="sc", params=dict(r=0.12, R=0.0))
    n = dict(seen=0)
    ev = threading.Event()

    def cb(info):
        if info["stage"] == "certificate: Bloch inertia counts":
            n["seen"] += 1
            ev.set()  # cancel at the next checkpoint (the next k-point)

    with progress.hooks(progress=cb, cancel=ev), pytest.raises(progress.Cancelled):
        certify.bloch_block(spec, dict(f_lo=0.3, f_hi=0.33), 0.3, (8,), n_path=2, n_interior=2, edge_res=(),
                            bloch_phases=(), adversarial_n=6)
    assert n["seen"] == 1


def test_search_checks_cancel_between_batches(monkeypatch):
    pytest.importorskip("botorch")
    from amm import search as srch
    rows = []

    def fake_eval(specs):  # no solve: a slack from the parameters
        out = [dict(spec=s, density=0.2, E100=0.01 * (1 + sum(v for v in s["params"].values()
                                                                 if isinstance(v, float))), G=0.01,
                    bulk=0.01, nu100=0.3, valid=True, bloch_valid=False) for s in specs]
        rows.extend(out)
        return out

    ev = threading.Event()
    batches = []

    def cb(info):
        if info["stage"] == "search: batch":
            batches.append(info)
            if len(batches) == 2:
                ev.set()

    with progress.hooks(progress=cb, cancel=ev), pytest.raises(progress.Cancelled):
        srch.search(dict(E100_min=0.5), families=["struts"], budget=40, q=8, evaluator=fake_eval, err={},
                    domain={})
    assert len(batches) == 2 and batches[0]["budget"] == 40 and 0 < len(rows) < 40


# ---- G6: PARDISO factorization freed on any exception -------------------------------------------------------------
def test_certify_gap_frees_the_factorization_on_an_exception(monkeypatch):
    freed = []
    orig_free = bloch.InertiaCounter.free
    monkeypatch.setattr(bloch.InertiaCounter, "free", lambda self: (freed.append(1), orig_free(self)))
    calls = dict(n=0)
    orig = bloch.InertiaCounter.counts

    def failing(self, k, f):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("solver failure between counts")
        return orig(self, k, f)

    monkeypatch.setattr(bloch.InertiaCounter, "counts", failing)
    m = np.zeros((6, 6, 6), bool)
    m[:, 2:4, 2:4] = m[2:4, :, 2:4] = m[2:4, 2:4, :] = True
    with pytest.raises(RuntimeError):
        bloch.certify_gap({6: fem.build_mesh(m.astype(float))}, 0.3, 0.33, n_path=2, n_interior=1)
    assert freed == [1]


# ---- G1: replay of export records with the default root -----------------------------------------------------------
def test_replay_of_exports_with_the_default_root(tmp_path):
    s = _spec_session(tmp_path / "s")
    out = s.call("export", SMALL_EXPORT)
    assert out["ok"], out
    rep = tools.replay(s.log_path)  # root=None
    assert rep["exact"], rep["mismatches"]
    assert rep["root"] == "temporary directory (removed)" and rep["n_compared"] == 4
    # the export result carries the sha256 of every file: a changed file is still a mismatch
    recs = tools.read_log(s.log_path)
    recs[-1]["result"]["files"]["cell"]["sha256"] = "0" * 64
    recs[-1].pop("result_hash")
    bad = tools.replay(recs)
    assert not bad["exact"] and bad["mismatches"][0]["tool"] == "export"


def test_replay_writes_the_logged_identity_into_export_reports(tmp_path):
    """Code identity is not a result: a log written by other code replays with that code's identity in report.json
    (as the checker alias does for certificates), so the report hash compares only content."""
    s = _spec_session(tmp_path / "s")
    assert s.call("export", SMALL_EXPORT)["ok"]
    recs = tools.read_log(s.log_path)
    recs[0] = dict(recs[0], code="00000000deadbeef", checker="11111111cafecafe")
    rep = tools.replay(recs, root=tmp_path / "r")
    assert rep["identity"]["code_aliased"] and rep["identity"]["checker_log_source"] == "header"
    rpt = json.loads(next((tmp_path / "r" / "exports").glob("*/report.json")).read_text(encoding="utf-8"))
    assert rpt["identity"]["code"] == "00000000deadbeef" and rpt["identity"]["checker"] == "11111111cafecafe"
    assert [m["field"] for m in rep["mismatches"]] == ["result"]  # the report bytes differ (other identity)
    # a log without a checker in its header or results: the known identity of its code
    head = dict(recs[0], code="5970bf55108f1584")
    head.pop("checker")
    assert tools.replay([head] + recs[1:4])["identity"]["checker_log"] == "f141e46cb67a78db"


# ---- G4: read-only calls while a solve runs ---------------------------------------------------------------------
def test_read_only_calls_answer_during_a_solve_and_replay_exactly(tmp_path):
    s = _spec_session(tmp_path / "s")
    assert s.call("check_bounds")["ok"]
    g0 = s.call("get_session")["result"]
    started, go = threading.Event(), threading.Event()

    def hold(info):  # the running export waits at its first checkpoint until the reads are done
        started.set()
        assert go.wait(60)

    th = threading.Thread(target=lambda: s.call("export", SMALL_EXPORT, progress=hold))
    th.start()
    assert started.wait(60)
    t0 = time.time()
    g = s.call("get_session")
    cb = s.call("check_bounds")
    assert time.time() - t0 < 10 and g["ok"] and cb["ok"]
    assert g["result"]["budget_used"] == g0["budget_used"] and g["result"]["certificates"] == g0["certificates"]
    # a spec change waits for the running call (log order = execution order)
    done = []
    tw = threading.Thread(target=lambda: done.append(s.call("set_target", {"density_max": 0.3})))
    tw.start()
    time.sleep(0.3)
    assert not done
    go.set()
    th.join(120)
    tw.join(120)
    calls = _calls(s.log_path)
    assert [c["tool"] for c in calls[-4:]] == ["get_session", "check_bounds", "export", "set_target"]
    assert [c["seq"] for c in calls[-4:]] == [7, 8, 6, 9]  # the reads were logged before the export
    rep = tools.replay(s.log_path)
    assert rep["exact"], rep["mismatches"]


# ---- G5: evaluate bands, schema 3, frozen contracts 1 and 2 -------------------------------------------------------
@pytest.mark.repo
def test_contracts_of_schemas_1_and_2_are_unchanged():
    for sch in (tools.SCHEMA_V1, tools.SCHEMA_V2):
        p = ROOT / "results" / "software" / f"contract_{sch.replace('/', '-')}.json"
        assert p.read_text(encoding="utf-8") == json.dumps(tools.contract(sch), indent=1, sort_keys=True) + "\n"
    c = tools.contract()
    assert c["schema_version"] == "amm-tools/3" == tools.SCHEMA_VERSION
    assert c["added_in_schema_3"] == {"evaluate": {"args": ["bands"], "results": ["bands"]}}
    assert "bands" in c["tools"]["evaluate"]["args"]["properties"]
    assert "bands" not in tools.contract(tools.SCHEMA_V2)["tools"]["evaluate"]["args"]["properties"]


def test_schema_2_session_rejects_the_bands_argument():
    s = _spec_session(schema=tools.SCHEMA_V2)
    out = s.call("evaluate", {"designs": [SC], "bands": True})
    assert not out["ok"] and "bands" in out["error"]
    assert s.used["designs"] == 0


def test_evaluate_bands_are_additive():
    s = _spec_session()
    d = {"kind": "cube_bars", "params": {"c": 0.6, "w": 0.2}}  # a known gap former (tests/test_tools.py)
    a = s.call("evaluate", {"designs": [d]})["result"]["results"][0]
    b = s.call("evaluate", {"designs": [d], "bands": True})["result"]["results"][0]
    assert "bands" not in a and {k: v for k, v in b.items() if k != "bands"} == a
    bd = b["bands"]
    f = np.asarray(bd["f_star"])
    assert f.shape == (len(bd["k_over_pi"]), bd["n_bands"]) and bd["k_ticks"][0] == [0, "G"]
    assert a["gaps"]
    g = a["gaps"][0]  # the reported gaps are read from these bands
    assert any(abs(f[:, j].max() - g["f_lo"]) < 1e-12 and abs(f[:, j + 1].min() - g["f_hi"]) < 1e-12
               for j in range(f.shape[1] - 1))
    assert bd["hz_per_f_star"] > 0
    # the export report never carries the bands
    assert "bands" not in s._evaluated[tools.canon([s._design_spec(tools.Design(**d)), s._nu()])]


# ---- B6-1, B6-2, B6-3: data location and messages ----------------------------------------------------------------
def _link(src: Path, dst: Path):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy(src, dst)


@pytest.mark.repo
def test_amm_data_dir_finds_the_atlas_and_error_model(tmp_path, monkeypatch):
    src = ROOT / "results" / "atlas"
    if not (src / "atlas_nu0.39.jsonl").is_file():
        pytest.skip("no results/atlas in this checkout")
    d = tmp_path / "amm-data-1"
    d.mkdir()
    for f in ("atlas_nu0.39.jsonl", "error_model.json"):
        _link(src / f, d / f)
    monkeypatch.setenv("AMM_DATA_DIR", str(d))
    assert tools.atlas_path(0.39) == d / "atlas_nu0.39.jsonl" and Path(atlas.error_model_path()) == d / "error_model.json"
    s = _spec_session()  # PA12: nu = 0.39
    cb = s.call("check_bounds")["result"]
    assert cb["atlas"]["verdict"] == "FEASIBLE" and cb["verdict"] == "FEASIBLE"
    assert s.call("atlas_suggest", {"top": 2})["ok"]
    # the error model is missing: clear messages, no internal error, no budget spent
    (d / "error_model.json").unlink()
    cb = s.call("check_bounds")["result"]
    assert cb["atlas"]["verdict"] == "UNAVAILABLE" and "error_model.json not found" in cb["atlas"]["note"]
    sr = s.call("search", {"budget": 8})
    assert not sr["ok"] and "internal error" not in sr["error"] and "AMM_DATA_DIR" in sr["error"]
    assert "error_model.json not found" in sr["error"] and s.used["designs"] == 0


def test_messages_when_the_atlas_is_missing(tmp_path, monkeypatch):
    empty = tmp_path / "nodata"
    empty.mkdir()
    monkeypatch.setenv("AMM_DATA_DIR", str(empty))
    s = _spec_session()
    note = s.call("check_bounds")["result"]["atlas"]["note"]
    assert "the search atlas for nu_s = 0.39 not found" in note and str(empty / "atlas_nu0.39.jsonl") in note
    assert f"AMM_DATA_DIR = {empty}" in note and "docs/data.md" in note
    err = s.call("atlas_suggest")["error"]
    assert err == note
    monkeypatch.delenv("AMM_DATA_DIR")
    assert "AMM_DATA_DIR is not set" in data.where()
    # a Poisson ratio no atlas exists for keeps the message recorded in earlier logs
    s2 = tools.Session(None)
    s2.call("set_material", {"E_Pa": 2e9, "nu": 0.25, "rho_kg_m3": 1000})
    s2.call("set_target", {"density_max": 0.3})
    assert s2.call("check_bounds")["result"]["atlas"]["note"] == "no atlas at nu_s = 0.25 (atlases: 0.3, 0.342, 0.39)"
