"""Write the versioned data manifest of the search atlas and the error model (plan B3).

    python scripts/software/make_data_manifest.py

Output: amm/data_manifest.json (shipped inside the package, so an installed amm can verify a downloaded data
set) with, per file: name, role, bytes, sha256, the script that generated it, and whether amm reads it at run time.
`identity.e4_data_hash` repeats scripts/bench/e4.py data_hash() over the same files (the identity recorded with
every E4 job), so a downloaded copy can be matched to the E4 runs. The data set is distributed as the asset
amm-data-1.zip of GitHub release v0.2.0 (release/RELEASE_PLAN.md) under CC-BY-4.0.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ATLAS = ROOT / "results" / "atlas"
OUT = ROOT / "amm" / "data_manifest.json"
VERSION = "amm-data/1"

FILES = [
    ("atlas_nu0.3.jsonl", "runtime", "search atlas, 2,722 cells, solid Poisson ratio 0.3 (search tier, not certified)",
     "scripts/atlas/run_atlas.py"),
    ("atlas_nu0.342.jsonl", "runtime", "search atlas, 2,722 cells, solid Poisson ratio 0.342", "scripts/atlas/run_atlas.py"),
    ("atlas_nu0.39.jsonl", "runtime", "search atlas, 2,722 cells, solid Poisson ratio 0.39", "scripts/atlas/run_atlas.py"),
    ("error_model.json", "runtime", "calibrated one-sided search-tier error model and its calibrated domain",
     "scripts/atlas/calibrate.py"),
    ("calibration.json", "provenance", "converged reference values behind the error model", "scripts/atlas/calibrate.py"),
    ("calibration_extra.json", "provenance", "extra calibration references (held-out bins)",
     "scripts/atlas/extend_calibration.py"),
    ("NOTES.md", "documentation", "how the atlas and the error model were built and checked", None),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def e4_data_hash() -> str:
    """Same bytes and order as scripts/bench/e4.py data_hash()."""
    h = hashlib.sha256()
    for f in sorted(ATLAS.glob("atlas_nu*.jsonl")) + [ATLAS / "error_model.json"]:
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def main():
    files = []
    for name, role, desc, gen in FILES:
        p = ATLAS / name
        gen_path = gen if gen and (ROOT / gen).exists() else None
        files.append(dict(name=name, role=role, description=desc, bytes=p.stat().st_size, sha256=sha256(p),
                          generator=gen_path or gen, generator_present=bool(gen_path)))
    man = dict(
        schema="amm-data-manifest/1", version=VERSION, title="amm search atlas and search-tier error model",
        license="CC-BY-4.0",  # confirmed by the authors 2026-11-08
        location=dict(default="results/atlas (repository checkout)", env="AMM_DATA_DIR",
                      note="an installed amm reads the data from $AMM_DATA_DIR (a folder holding the runtime files); "
                           "amm.data.verify() checks the files against this manifest"),
        distribution=dict(release="https://github.com/nbbllxx0/Designing-Periodic-Cell/releases/tag/v0.2.0",
                          asset="amm-data-1.zip"),
        contents=("atlas rows (spec, search-tier C* summary, gaps, bands) per solid Poisson ratio and the error "
                  "model used by check_bounds, atlas_suggest and search; values are search-tier estimates, NOT "
                  "certificates"),
        identity=dict(e4_data_hash=e4_data_hash(), note="scripts/bench/e4.py data_hash() of the runtime files"),
        files=files)
    OUT.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    print("wrote", OUT, "e4_data_hash", man["identity"]["e4_data_hash"])


if __name__ == "__main__":
    main()
