"""B3 (2026-11-07): no solve at import, MKL initialized before torch, explicit grid phase, checker identity, data
manifest and optional extras. Ordering checks run in fresh interpreters (other tests may have loaded torch)."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300, cwd=str(ROOT))


# ---- MKL before torch ------------------------------------------------------------------------------------------
def test_import_amm_solves_nothing_and_torch_import_initializes_mkl_first():
    out = _run("import sys, os, amm\n"
               "st = dict(amm._runtime.STATE)\n"
               "assert not st['initialized'], st\n"
               "assert 'pypardiso' not in sys.modules\n"
               "assert os.environ['MKL_CBWR'] == 'AUTO,STRICT' and os.environ['MKL_NUM_THREADS']\n"
               "import torch\n"
               "st = amm._runtime.STATE\n"
               "assert st['initialized'] and st['trigger'] == 'import torch' and st['torch_loaded_before'] is False, st\n"
               "assert amm.MKL_CBWR_STATUS == 0x10002\n"
               "print('OK')")
    assert out.returncode == 0 and "OK" in out.stdout, out.stderr[-2000:]


def test_botorch_import_also_goes_through_the_guard():
    out = _run("import amm, botorch\nst = amm._runtime.STATE\n"
               "assert st['initialized'] and st['trigger'].startswith('import torch') and not st['torch_loaded_before']\n"
               "print('OK')")
    assert out.returncode == 0 and "OK" in out.stdout, out.stderr[-2000:]


def test_first_pardiso_use_initializes_mkl_without_torch():
    out = _run("import sys, amm\nfrom amm import fem, geometry, homog\n"
               "cov, sub, info = geometry.design_cell(dict(family='struts', kind='sc', params=dict(r=0.15, R=0.0)), 8)\n"
               "r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=0.3))\n"
               "st = amm._runtime.STATE\n"
               "assert st['initialized'] and st['trigger'] == 'first PARDISO solver' and 'torch' not in sys.modules, st\n"
               "assert st['cbwr_status'] == 0x10002\nprint('OK')")
    assert out.returncode == 0 and "OK" in out.stdout, out.stderr[-2000:]


def test_torch_first_gives_a_clear_error_instead_of_an_abort():
    out = _run("import torch, amm\n"
               "try:\n    amm.MKL_CBWR_STATUS\nexcept RuntimeError as e:\n    print('ERR', e)\n")
    assert out.returncode == 0, out.stderr[-2000:]
    assert "ERR amm: torch was imported before MKL" in out.stdout


# ---- geometry: explicit phase ------------------------------------------------------------------------------------
def test_grid_phase_is_an_argument_and_threads_do_not_interfere():
    from amm import geometry as G
    assert not hasattr(G, "_SHIFT")
    spec = dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.2))
    serial = {ph: G.design_cell(spec, 12, phase=ph)[0] for ph in (0.0, 0.25, 0.5)}
    got, errs = {}, []

    def work(ph):
        try:
            for _ in range(3):
                c = G.design_cell(spec, 12, phase=ph)[0]
                if not np.array_equal(c, serial[ph]):
                    errs.append(ph)
            got[ph] = c
        except Exception as e:  # noqa: BLE001
            errs.append(e)

    th = [threading.Thread(target=work, args=(ph,)) for ph in (0.0, 0.25, 0.5) for _ in range(2)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert not errs
    # same arithmetic as the removed module global: ((i + 1/2)/n + phase/n) mod 1
    g = G.grid(5, 0.25 / 5)[0][:, 0, 0]
    assert np.array_equal(g, ((np.arange(5) + 0.5) / 5 + 0.25 / 5) % 1.0)


# ---- checker identity ------------------------------------------------------------------------------------------
def test_checker_files_cover_every_imported_amm_module():
    from amm import certify
    out = _run("import sys, amm.certify\nprint(sorted(m.split('.')[1] + '.py' for m in sys.modules "
               "if m.startswith('amm.')))")
    loaded = set(ast.literal_eval(out.stdout.strip().splitlines()[-1]))
    files = set(certify.checker_files())
    assert loaded <= files, loaded - files
    assert {"certify.py", "bloch.py", "fem.py", "homog.py", "geometry.py", "pardiso.py", "units.py",
            "__init__.py", "_runtime.py"} <= files
    assert certify.CHECKER_FILES == certify.checker_files()


def test_a_new_module_imported_by_the_checker_joins_the_identity(tmp_path):
    from amm import certify
    src = Path(certify.__file__).parent
    for f in src.glob("*.py"):
        (tmp_path / f.name).write_bytes(f.read_bytes())
    base = certify.checker_files(tmp_path)
    (tmp_path / "newcheck.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "bloch.py").write_text((src / "bloch.py").read_text(encoding="utf-8")
                                       + "\n\ndef _late():\n    from . import newcheck\n    return newcheck.X\n",
                                       encoding="utf-8")
    assert "newcheck.py" not in base and "newcheck.py" in certify.checker_files(tmp_path)


# ---- data manifest and packaging -------------------------------------------------------------------------------
def test_data_manifest_matches_the_files_and_the_e4_identity():
    from amm import data
    v = data.verify()
    assert v["ok"], v
    m = data.manifest()
    assert m["version"] == "amm-data/1" and all(len(f["sha256"]) == 64 for f in m["files"])
    meta = json.loads((ROOT / "results" / "bench" / "e4" / "jobs.json").read_text(encoding="utf-8"))["meta"]
    assert m["identity"]["e4_data_hash"] == meta["data"]


def test_optional_extras_are_not_core_dependencies():
    import re
    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")  # Python 3.10: no tomllib
    core = re.search(r"^dependencies = \[(.*?)\]", txt, re.M | re.S).group(1)
    for opt in ("botorch", "gpytorch", "mcp", "cupy", "starlette", "uvicorn", "scikit-image"):
        assert opt not in core
    extras = txt.split("[project.optional-dependencies]", 1)[1].split("\n[", 1)[0]
    ex = dict(re.findall(r"^(\w+) = \[(.*?)\]", extras, re.M))
    assert {"search", "mcp", "gui", "export", "gpu"} <= set(ex)
    assert "botorch" in ex["search"] and "mcp" in ex["mcp"] and "starlette" in ex["gui"]


_BLOCK = ("import sys, importlib.abc\n"
          "class B(importlib.abc.MetaPathFinder):\n"
          "    def find_spec(self, name, path=None, target=None):\n"
          "        if name.split('.')[0] in {MODS}:\n"
          "            raise ImportError('blocked ' + name)\n"
          "sys.meta_path.insert(0, B())\n")


def test_missing_botorch_gives_a_clear_error():
    code = _BLOCK.replace("{MODS}", "('botorch', 'gpytorch')") + (
        "from amm import tools\n"
        "s = tools.Session(profile='C')\n"
        "s.call('set_material', {'name': '316L'}); s.call('set_target', {'density_max': 0.3})\n"
        "out = s.call('search', {'budget': 8})\n"
        "print('ERR', out['error'])\n"
        "print('OK', s.call('check_bounds')['ok'])\n")
    out = _run(code)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "ERR amm.search (the `search` tool) needs BoTorch" in out.stdout and "pip install amm[search]" in out.stdout
    assert "OK True" in out.stdout


def test_missing_mcp_gives_a_clear_error():
    code = _BLOCK.replace("{MODS}", "('mcp',)") + (
        "from amm import tools, mcp_server\n"
        "try:\n    mcp_server.build_server(tools.Session(profile='B'))\n"
        "except ImportError as e:\n    print('ERR', e)\n")
    out = _run(code)
    assert out.returncode == 0 and "pip install amm[mcp]" in out.stdout, out.stderr[-2000:]


def test_cuda_falls_back_to_cpu(monkeypatch):
    import torch
    from amm import atlas, bloch, evaluate
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert bloch.resolve_device("cuda") == "cpu" and bloch.resolve_device("cpu") == "cpu"
    row = evaluate.evaluate_batch([atlas.make_spec("cube_bars", {"c": 0.6, "w": 0.2})], nu=0.3, n_static=10,
                                  n_bloch=6, n_fine=30, npts=2, nev=8, workers=1)[0]
    assert row["bloch_device"] == "cpu" and row["bloch_valid"] and row["E100"] > 0
