"""V2 (2026-11-08): the command line amm.cli, a thin wrapper over Session.call with JSON output. It must add no logic:
its tool calls and their results are exactly those of the library for the same arguments."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from amm import cli, tools

ROOT = Path(__file__).resolve().parents[1]
INFEASIBLE = ["--material", "316L", "--target", '{"density_max": 0.16, "E100_min": {"value": 38.6, "unit": "GPa"}}']


def _run(capsys, argv):
    code = cli.main(argv)
    out = json.loads(capsys.readouterr().out)
    return code, out


def test_check_bounds_is_the_library_call(capsys, tmp_path):
    code, out = _run(capsys, ["check-bounds", "--session", str(tmp_path / "s")] + INFEASIBLE)
    assert code == 0 and out["ok"] and out["cli"] == cli.CLI_SCHEMA
    assert [c["tool"] for c in out["calls"]] == ["set_material", "set_target", "check_bounds"]
    assert out["result"]["verdict"] == "PROVEN_INFEASIBLE" and out["result"]["violated"][0]["bound"] == "V1"
    # the same calls through the library give the same results (no logic in the CLI)
    s = tools.Session(None)
    for c in out["calls"]:
        r = s.call(c["tool"], c["args"])
        assert r["ok"] and tools.result_hash(r["result"]) == tools.result_hash(c["result"])
    recs = tools.read_log(tmp_path / "s" / "session.jsonl")
    assert [r.get("actor") for r in recs if r["type"] == "call"] == ["cli"] * 3


def test_spec_file_and_flags(capsys, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(dict(material={"name": "PA12"}, constraints={"cell_size": 10, "cell_size_unit": "mm"},
                                    targets={"density_max": 0.25})), encoding="utf-8")
    code, out = _run(capsys, ["check-bounds", "--spec", str(spec), "--target", '{"E100_min": {"value": 25, "unit": "MPa"}}'])
    assert code == 0, out
    tgt = next(c for c in out["calls"] if c["tool"] == "set_target")
    assert tgt["args"] == {"density_max": 0.25, "E100_min": {"value": 25, "unit": "MPa"}}
    assert tgt["result"]["normalized"]["E100_min"] == pytest.approx(25e6 / 1.7e9, rel=1e-15)
    code, out = _run(capsys, ["check-bounds", "--spec", str(spec), "--material", "316L"])
    assert out["calls"][0]["args"] == {"name": "316L"}


def test_refusals_are_amms_and_stop_the_calls(capsys):
    code, out = _run(capsys, ["check-bounds", "--material", "316L", "--target", '{"porosity_max": 0.5}'])
    assert code == 1 and not out["ok"] and out["error"]["tool"] == "set_target"
    assert "porosity_max" in out["error"]["error"] and [c["tool"] for c in out["calls"]] == ["set_material", "set_target"]
    code, out = _run(capsys, ["check-bounds", "--profile", "B", "--material", "316L", "--target", '{"density_max": 0.3}'])
    assert code == 1 and "unknown tool 'check_bounds'" in out["error"]["error"]
    code, out = _run(capsys, ["export", "--material", "PA12", "--design", '{"kind": "bcc", "params": {"r": 0.08, "R": 0}}'])
    assert code == 1 and "needs a session directory" in out["error"]["error"]


def test_usage_errors_exit_2(capsys, tmp_path):
    assert cli.main(["evaluate", "--design", "{bad json"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert "not valid JSON" in out["usage_error"]
    assert cli.main(["certify", "--design", "{}", "--design", "{}"]) == 2
    capsys.readouterr()
    (tmp_path / "used").mkdir()
    (tmp_path / "used" / "session.jsonl").write_text("{}\n", encoding="utf-8")
    assert cli.main(["check-bounds", "--session", str(tmp_path / "used"), "--material", "PA12"]) == 2
    assert "already holds a session log" in json.loads(capsys.readouterr().out)["usage_error"]
    with pytest.raises(SystemExit) as ex:
        cli.main(["frobnicate"])
    assert ex.value.code == 2


def test_replay_of_a_cli_session_is_exact(capsys, tmp_path):
    code, _ = _run(capsys, ["check-bounds", "--session", str(tmp_path / "s")] + INFEASIBLE)
    assert code == 0
    code, out = _run(capsys, ["replay", str(tmp_path / "s" / "session.jsonl")])
    assert code == 0 and out["result"]["exact"] and out["result"]["n_compared"] == 3


def test_cli_is_not_part_of_the_code_identity():
    assert "cli.py" in tools.NOT_HASHED


def test_console_script_entry_and_module_run():
    import re  # tomllib needs Python 3.11; amm supports 3.10
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    assert re.search(r'^amm = "amm\.cli:main"$', block, re.M), block
    import importlib
    mod, fn = "amm.cli:main".split(":")
    assert getattr(importlib.import_module(mod), fn) is cli.main
    p = subprocess.run([sys.executable, "-B", "-m", "amm.cli", "--version"], capture_output=True, text=True,
                       cwd=str(ROOT), timeout=120)
    assert p.returncode == 0 and p.stdout.strip().startswith("amm ")
