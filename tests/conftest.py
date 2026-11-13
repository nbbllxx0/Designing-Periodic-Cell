"""Test requirements (plan B6, 2026-11-08): markers and automatic skips, so the same suite runs in a full checkout,
in CPU-only CI and against an installed wheel. No assertion is changed here: a test whose requirement is absent is
skipped with the reason (or, for a module that cannot even be imported without it, not collected, and the header
says so); with every requirement present the suite runs exactly as before.

Markers (registered in pyproject.toml):
  gpu   needs a CUDA device
  data  needs the runtime data files (search atlas, error model) where amm reads them: amm.data.data_dir()
        (AMM_DATA_DIR, else results/atlas of the checkout; see docs/data.md)
  repo  needs source-checkout files outside the amm package (listed per test below)
  slow  takes more than about 10 s on a desktop CPU without CUDA
CI runs `pytest -m "not gpu"`; locally `pytest -m "not slow"` is the quick subset.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# modules whose top-level imports need source-checkout files ("data": the runtime data files): not collected
# when those are absent (scripts/bench/build.py loads the error model at import)
# (keys are file names or glob patterns: test_app*.py covers every GUI test module)
MODULE_NEEDS = {
    "test_app*.py": ("app/backend.py", "app/server.py"),
    "test_app.py": ("results/bench",),
    "test_bench.py": ("scripts/bench/build.py", "scripts/bench/render.py", "scripts/bench/scoring.py", "data"),
    "test_harness.py": ("scripts/bench/scoring.py", "scripts/bench/e4.py", "bench/v1/briefs"),
}

# per test (node id without parameters, or a module name for every test in it): requirements.
# "data", "gpu", "slow" are markers; "repo:<path>" needs that path under the checkout root.
NEEDS = {
    "test_app.py": ("repo:app", "repo:results/bench", "data"),  # the mock GUI serves atlas rows and mirrors
    "test_bench.py": ("repo:scripts/bench", "repo:bench/v1", "data"),
    "test_harness.py": ("repo:scripts/bench", "repo:bench/v1"),
    "test_harness.py::test_plan_writes_manifest_with_full_identity": ("data",),  # e4.data_hash reads the files
    "test_core.py::test_gpu_bands_match_cpu_dense": ("gpu",),
    "test_runtime.py::test_data_manifest_matches_the_files_and_the_e4_identity": (
        "data", "repo:results/bench/e4/jobs.json"),
    "test_runtime.py::test_optional_extras_are_not_core_dependencies": ("repo:pyproject.toml",),
    "test_cli.py::test_console_script_entry_and_module_run": ("repo:pyproject.toml",),  # V2
    # B7 (2026-11-08): reads the frozen contracts of schemas 1 and 2 from results/software (absent next to an
    # installed wheel; found by the B7 clean installs)
    "test_b9.py::test_contracts_of_schemas_1_and_2_are_unchanged": (
        "repo:results/software/contract_amm-tools-1.json", "repo:results/software/contract_amm-tools-2.json"),
    "test_outcomes.py::test_bound_and_atlas_records_support_their_verdicts_only": ("data",),
    "test_outcomes.py::test_stale_evidence_does_not_count": ("data",),
    "test_bounds.py::test_bounds_never_refute_an_achieved_design": ("slow",),
    "test_verdict.py::test_static_block_without_static_targets_stops_at_the_first_rung": ("slow",),
    "test_mutations.py::test_overstated_stiffness_is_refused_and_honest_claim_passes": ("slow",),
    "test_mutations.py::test_density_claim_violation_is_refused": ("slow",),
    "test_mutations.py::test_interior_k_gap_closure_is_caught_by_the_adversarial_k_search": ("slow",),
    "test_mutations.py::test_floating_core_is_refused_by_static_and_bloch_blocks": ("slow",),
    # about 3 s with CUDA, about 30 s when the band solver runs on the CPU
    "test_tools.py::test_contract_and_exact_replay": ("slow",),
    "test_tools.py::test_profile_b_has_no_certificates": ("slow",),
    "test_tools.py::test_replay_detects_a_changed_result": ("slow",),
    # B9 (tests/test_b9.py): search-tier bands and the adversarial k search run on the CPU without CUDA
    "test_b9.py::test_evaluate_bands_are_additive": ("slow",),
    "test_b9.py::test_cancel_inside_the_fail_closed_bloch_block_is_not_a_verdict": ("slow",),
}

_cache: dict = {}


def _cuda() -> bool:
    if "cuda" not in _cache:
        try:
            import amm  # noqa: F401  (amm before torch: MKL's OpenMP runtime first)
            import torch
            _cache["cuda"] = bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001
            _cache["cuda"] = False
    return _cache["cuda"]


def _data_missing() -> list[str]:
    """The runtime data files that are absent where amm reads them (amm.data: AMM_DATA_DIR, or results/atlas of
    the checkout; B6-1 fixed in B9)."""
    if "data" not in _cache:
        from amm import atlas, tools
        need = [tools.atlas_path(nu) for nu in (0.3, 0.342, 0.39)]
        need.append(Path(atlas.error_model_path()))
        _cache["data"] = [str(p) for p in need if not p.is_file()]
    return _cache["data"]


def _module_missing(paths) -> list[str]:
    out = []
    for p in paths:
        if p == "data":
            out += [f"data file {m}" for m in _data_missing()[:1]]
        elif not (ROOT / p).exists():
            out.append(p)
    return out


def _missing_modules() -> dict:
    out = {}
    for f in sorted(Path(__file__).parent.glob("test_*.py")):
        miss = []
        for pat, paths in MODULE_NEEDS.items():
            if fnmatch.fnmatch(f.name, pat):
                miss += [m for m in _module_missing(paths) if m not in miss]
        if miss:
            out[f.name] = miss
    return out


_MISSING_MODULES = _missing_modules()
collect_ignore = sorted(_MISSING_MODULES)


def pytest_report_header(config):
    lines = []
    for m, miss in _MISSING_MODULES.items():
        lines.append(f"amm: {m} not collected (source-checkout files absent: {', '.join(miss)})")
    return lines


def _needs(item) -> tuple:
    mod = Path(str(item.fspath)).name
    base = f"{mod}::{item.originalname if hasattr(item, 'originalname') else item.name}"
    return tuple(NEEDS.get(mod, ())) + tuple(NEEDS.get(base, ()))


def pytest_collection_modifyitems(config, items):
    for item in items:
        for req in _needs(item):
            if req.startswith("repo:"):
                item.add_marker(pytest.mark.repo)
                p = req[5:]
                if not (ROOT / p).exists():
                    item.add_marker(pytest.mark.skip(reason=f"source-checkout file absent: {p}"))
            elif req == "gpu":
                item.add_marker(pytest.mark.gpu)
                if not _cuda():
                    item.add_marker(pytest.mark.skip(reason="no CUDA device"))
            elif req == "data":
                item.add_marker(pytest.mark.data)
                miss = _data_missing()
                if miss:
                    item.add_marker(pytest.mark.skip(reason=f"runtime data files absent ({len(miss)}), e.g. {miss[0]}"))
            elif req == "slow":
                item.add_marker(pytest.mark.slow)
