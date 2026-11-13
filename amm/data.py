"""Location and integrity of the packaged data: the search atlas and the search-tier error model (plan B3).

The data are not inside the wheel (about 47 MB). They form a versioned data set, `amm-data/1`, described by
`amm/data_manifest.json` (shipped with the package; written by scripts/software/make_data_manifest.py): file names,
roles (runtime, provenance, documentation), sizes, sha256 hashes, generating scripts, and the identity the E4 runs
recorded (scripts/bench/e4.py data_hash). At release (plan B7) the same files go to a Zenodo record whose DOI is
added to the manifest; a user downloads them into a folder and points AMM_DATA_DIR at it.

`data_dir()`: $AMM_DATA_DIR if set, else results/atlas of the repository checkout (the path every result so far
used). `verify()` checks the runtime files against the manifest. Nothing here changes what the tools compute: with
AMM_DATA_DIR unset the files read are the same as before 2026-11-07.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

MANIFEST_PATH = Path(__file__).with_name("data_manifest.json")
REPO_DATA = Path(__file__).resolve().parents[1] / "results" / "atlas"


def data_dir() -> Path:
    """$AMM_DATA_DIR if set, else results/atlas of the source checkout. Read at each call: amm.tools (atlas) and
    amm.atlas (error model) resolve their files through it when they need them (B9, 2026-11-08)."""
    env = os.environ.get("AMM_DATA_DIR")
    return Path(env) if env else REPO_DATA


def atlas_path(nu: float) -> Path:
    """The search-atlas file for a solid Poisson ratio nu (it exists only for the ratios of ATLAS_NUS)."""
    return data_dir() / f"atlas_nu{nu:g}.jsonl"


def error_model_path() -> Path:
    return data_dir() / "error_model.json"


ATLAS_NUS = (0.3, 0.342, 0.39)  # the atlases of amm-data/1 (the Poisson ratios of the four named materials)


def where() -> str:
    """Where amm looks for the data, in words (for error messages)."""
    env = os.environ.get("AMM_DATA_DIR")
    if env:
        return f"AMM_DATA_DIR = {env}"
    return (f"AMM_DATA_DIR is not set, so amm looked in the source checkout's results/atlas ({REPO_DATA}); "
            "an installed package has no data there")


def missing_message(what: str, path: Path, looked: str | None = None) -> str:
    """A clear message for a runtime data file that is not there: what, where amm looked, and how to fix it."""
    return (f"{what} not found: {path} does not exist ({looked or where()}). The runtime data set amm-data/1 (search atlases "
            "atlas_nu0.3.jsonl, atlas_nu0.342.jsonl, atlas_nu0.39.jsonl and error_model.json) is not part of the "
            "wheel: download it and set the environment variable AMM_DATA_DIR to its folder, or run from a source "
            "checkout with results/atlas (docs/data.md; amm.data.verify() checks the files)")


def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def verify(directory: str | Path | None = None, roles=("runtime",)) -> dict:
    """{ok, version, dir, files: {name: "ok" | "missing" | "hash mismatch"}} for the files of the given roles."""
    d = Path(directory) if directory is not None else data_dir()
    m = manifest()
    out = {}
    for f in m["files"]:
        if f["role"] not in roles:
            continue
        p = d / f["name"]
        out[f["name"]] = "missing" if not p.exists() else ("ok" if _sha256(p) == f["sha256"] else "hash mismatch")
    return dict(ok=all(v == "ok" for v in out.values()), version=m["version"], dir=str(d), files=out)
