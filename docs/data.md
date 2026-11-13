# Data: the search atlas and the error model

Some tools need a versioned data set, `amm-data/1`, of about 47 MB: the search atlas and the search-tier error
model. These files are **not inside the wheel**. The data set is described by `amm/data_manifest.json`, which is
shipped with the package.

| File | Role | Size | Used by |
|---|---|---|---|
| `atlas_nu0.3.jsonl` | runtime | 15.8 MB | `check_bounds` (atlas verdict), `atlas_suggest`, `search` seeding, at solid Poisson ratio 0.3 (316L) |
| `atlas_nu0.342.jsonl` | runtime | 15.8 MB | the same at 0.342 (Ti6Al4V) |
| `atlas_nu0.39.jsonl` | runtime | 15.8 MB | the same at 0.39 (PA12) |
| `error_model.json` | runtime | 5 kB | `check_bounds` atlas verdict, `atlas_suggest` ranking, `search` (required) |
| `calibration.json`, `calibration_extra.json` | provenance | 36 kB, 54 kB | converged reference values behind the error model |
| `NOTES.md` | documentation | 11 kB | how the atlas and the error model were built and checked |

Each atlas has 2,722 cells, one search-tier `evaluate` row each (static n = 20, bands n = 10 with the band diagram
kept). They are estimates, not certificates. The manifest lists the sha256, size, role and generating script
(`scripts/atlas/run_atlas.py`, `scripts/atlas/calibrate.py`, `scripts/atlas/extend_calibration.py`) of every file.

## What works without the data

Everything except the atlas-dependent parts works:

- `set_*`, `evaluate`, `certify`, `as_built`, `screen_manufacturing`, `export`, `submit` and replay;
- the bounds part of `check_bounds`. Its atlas part reports `UNAVAILABLE`, and so does its overall verdict when no
  bound is violated.

`atlas_suggest` returns an error, and the atlas part of `check_bounds` says why in its `note`: "the search atlas
for nu_s = 0.39 not found: <path> does not exist (AMM_DATA_DIR = ... / AMM_DATA_DIR is not set, so amm looked in
the source checkout's results/atlas ...)", followed by how to get the data set and set `AMM_DATA_DIR`. A Poisson
ratio that no atlas exists for (a custom material) keeps the message "no atlas at nu_s = 0.25 (atlases: 0.3, 0.342,
0.39)". `search` needs `error_model.json` (it ranks designs by the error-corrected slack); without it, it returns
the error "search cannot run: the search-tier error model error_model.json not found: ..." with the same
explanation, spends no budget, and does not run uncorrected. `check_bounds` then reports its atlas part as
`UNAVAILABLE` with that note. (Before amm B9, 2026-11-08, the messages were "no atlas at nu_s = ..." and
"internal error: FileNotFoundError", bugs B6-2 and B6-3 of `results/software/NOTES_B6.md`.)

## Where amm looks

- **Source checkout:** `results/atlas/` of the checkout. This is the default, and every result of the project
  used it.
- **Installed package:** `$AMM_DATA_DIR`, a folder that holds the runtime files. `amm.data.data_dir()` returns
  it, and `amm.data.verify()` checks the files against the manifest:

```python
import os
os.environ["AMM_DATA_DIR"] = r"D:\amm-data-1"      # set before importing amm
import amm
from amm import data
print(data.verify())   # {'ok': True, 'version': 'amm-data/1', 'dir': ..., 'files': {name: 'ok' | 'missing' | 'hash mismatch'}}
```

Both the atlas (`amm.tools.atlas_dir()`) and the error model (`amm.atlas.error_model_path()`) are resolved through
`amm.data.data_dir()` when they are needed, so `AMM_DATA_DIR` may also be set after importing amm. Setting
`amm.tools.ATLAS_DIR` to a folder overrides the atlas location only. (Bug B6-1 of amm before B9, 2026-11-08: the
tools read the atlas from `<package>/../results/atlas` and ignored `AMM_DATA_DIR`, and the error-model path was
fixed at import; checked fixed in a clean wheel install, `results/software/NOTES_B9.md`.)

## Getting the data

The data set is distributed as `amm-data-1.zip`, an asset of GitHub release v0.2.0
(https://github.com/nbbllxx0/Designing-Periodic-Cell/releases/tag/v0.2.0), under CC BY 4.0; the manifest's
`distribution` field names it. Unzip it into a folder and set `AMM_DATA_DIR` to that folder; in a source checkout the
same files are in `results/atlas/`. `amm.data.verify(folder)` confirms the hashes.

## The manifest

`amm/data_manifest.json` (schema `amm-data-manifest/1`) records the data-set version, the file list (name, role,
bytes, sha256, generator), and the identity that the benchmark runs recorded (`identity.e4_data_hash`). It is
written by `scripts/software/make_data_manifest.py`. A rebuilt atlas or error model is a new data version.
