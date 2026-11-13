# amm GUI backend (`app/`) and front end (`web/`)

Plan items B4 (backend) and B5 (front end, essential panels) of `plan/SOFTWARE_PAPER_PLAN.md`.
The backend lives outside `amm/`, so the frozen E4 code identity is untouched.

## Mock mode (no solver; safe while E4 runs)

Mock mode never imports `amm` (importing it runs a PARDISO solve and loads MKL/torch), never opens a CUDA
context and never calls an LLM. Spec tools run in a mirror of `amm.tools.Session`; solver tools return recorded
results from the development sessions (smoke, pilot, probe). The confirmatory E4 run is not read.

```
cd C:\AI\AgenticMetamaterials
python -B -m app.server --mock --port 8766 --load pilot/C/G01 --delay 0.02
```

Then open http://127.0.0.1:8766/ (the server serves the built front end in `web/dist`).
Options: `--load <id>` opens a recorded session (ids from `GET /api/recorded`, e.g. `pilot/C/G01`,
`smoke/codex-C-r1-S01`); `--delay f` replays each solver job at the fraction `f` of its recorded duration (capped at
3 s) so the queue states are visible; `--root` sets where session logs and exports go (default
`results/gui/sessions/`).

Front end with hot reload (needs the backend above; Vite proxies `/api` to port 8766):

```
node web/node_modules/vite/bin/vite.js web    # http://127.0.0.1:5174
```

Rebuild `web/dist` after front-end changes:
`cd web && node node_modules/vite/bin/vite.js build`
(type check: `node node_modules/typescript/bin/tsc -b --noEmit`).

Both commands are in `.claude/launch.json` (`amm-gui-mock`, `amm-web-dev`).

URL parameters: `?load=<id>` opens a recorded session, `?tiled=1` the tiled view, `?tab=timeline|atlas|agent` the
bottom tab, `?static=1` disables the event stream (needed for headless screenshots).

What mock mode serves:

| Tool | Mock behaviour |
|---|---|
| set_material, set_constraints, set_target, set_source, submit, undo, get_session, list_families | mirror of `amm.tools.Session` (same results, state hashes and certificate keys; checked against the 18 current-code smoke sessions in `tests/test_app.py`) |
| check_bounds, atlas_suggest, search, certify | the recorded result for the same arguments, normalized targets, Poisson ratio and families; otherwise a clear "no recorded result" error |
| evaluate | recorded result, else the nearest search-atlas row of the same kind (labelled, with the parameter distance) |
| ask_clarification | not available (no user and no agent in mock mode) |

## Live mode

```
python -B -m app.server --live --port 8767      # http://127.0.0.1:8767/
```

(`.claude/launch.json`: `amm-gui-live`.) The backend wraps `amm.tools.Session` (schema amm-tools/3 since B9, 2026-11-08; `app/live.py`,
imported only here). Every user action is a logged tool call (actor "user"), so a GUI session replays exactly with
`amm.tools.replay(<session>/session.jsonl, root=<dir>)` (checked for the e2e sessions, section below).

| Tool | Live behaviour |
|---|---|
| set_material, set_constraints, set_target, set_source, submit, undo, get_session, list_families, check_bounds, atlas_suggest | run at once (CPU, fast); while a solve runs they answer "session busy" instead of blocking |
| evaluate, search, certify, as_built | queued on the one worker; each job takes the shared solver lock (below) |
| export, screen_manufacturing | queued on the worker, CPU only, no lock |

- **Shared solver lock.** `C:/AI/AgenticMetamaterials_workspaces/gpu.lock`, same file protocol as
  `scripts/ops/gpulock_run.py` (exclusive create of `{pid, who, t}`, a lock of a dead process is removed). Taken per
  job and released when the job ends (also on cancel, on `POST /api/shutdown` and on Ctrl+C); while another runner
  holds it the job shows "waiting for the shared solver lock (held by ...)". `--lock PATH` or `AMM_GPU_LOCK` override
  the file. `GET /api/lock` shows the state.
- **Progress and cancel.** Running jobs stream `progress` events on the SSE stream (stage, solve counts, elapsed) and
  appear in the jobs bar under the header with a Cancel button. amm has no progress callback, so `app/live.py` wraps
  homogenize, the inertia counter, the GPU band solver and the certificate blocks at run time (pass-through: same
  arguments, same results; no amm file is edited). A cancelled solve stops at the next checkpoint (seconds) and is
  rolled back: no log record, seq number and budget returned.
- **Bands.** `evaluate` returns gaps but not the band arrays; a tap on `amm.evaluate.evaluate_batch` keeps the bands
  of the logged call for the band diagram (no extra solve). Before a design is evaluated the panels show the nearest
  atlas cell, labelled as such.
- **Full C\*.** The stiffness panel shows the 6x6 tensor of the session's `evaluate` (normalized or MPa) with the
  derived quantities, and E(n) from the full tensor; a certificate adds its cubic constants and guarded bounds.
- **Outcome (B1).** The evidence panel shows the `amm-outcome/1` view: every evidence record with the outcome it
  supports and whether it holds for the current spec, the outcome card of the submission with the records it cites,
  and the last submit the refusal-evidence rule rejected (with amm's message). The Submit box offers release /
  refuse (verdict) / need_info and says which records each verdict could cite now.
- **Export (B2).** "Screen manufacturing" and "Export STL + report" call the amm tools; the files they write under
  `<session>/exports/<name>/` are downloadable (`/api/session-files/...`, zip with `session.jsonl` at
  `/api/export-zip/<name>`). The screening-only disclaimer is always shown.
- **Agent.** The agent panel is a stub: the agent reaches the same tool contract through the MCP server
  (`python -m amm.mcp_server --session DIR --profile C`); the GUI makes no LLM calls.

Front end with hot reload against the live server: `set AMM_GUI_PORT=8767` before starting Vite.

### Live end-to-end check

```
python -B -m app.e2e_live --start-server     # about 2 min, ~1 GPU-minute
```

Starts the live server (port 8767) and headless Microsoft Edge with a temporary profile (DevTools protocol on
127.0.0.1, own minimal websocket client, no Playwright), clicks through two scenarios and stops both: (1) 316L,
a = 5 mm, struts, density <= 0.3, E100 >= 5 GPa -> Check bounds -> Atlas suggest -> Evaluate -> Certify, cancelled
while running -> Certify (static-only certificate, ~45 s) -> release -> Screen manufacturing -> Export, with the
downloads checked; (2) density <= 0.2, E100 >= 0.5 E_s -> refuse without evidence (rejected) -> Check bounds ->
refuse PROVEN_INFEASIBLE (accepted, cites the bound record). Screenshots `paper/figures/gui_live_*.png`; a JSON record
(steps, timings, checks) in `results/gui/sessions/e2e_live_<stamp>.json`.

## API

REST (JSON) and server-sent events; see the docstring of `app/server.py`. Main routes: `GET /api/tools`,
`POST /api/tools/{name}` `{args, actor, wait}` (solving tools return a job), `GET /api/session`, `GET /api/jobs`,
`POST /api/jobs/{id}/cancel`, `POST /api/details` (tensor, bands, certificate view of a design), `GET /api/preview`,
`GET /api/atlas`, `POST /api/export` + `GET /api/files/{name}` (mock preview bundle), `GET /api/session-files/{path}`
and `GET /api/export-zip/{name}` (files of the amm export tool), `GET /api/lock`, `POST /api/shutdown`,
`GET /api/events` (SSE: hello, record, session, job, progress, export). POSTs must be `application/json` and the Host
header a localhost name.

Mock preview bundle (zip, header Export in mock mode): `cell.stl`, `tiled_NxNxN.stl` (preview geometry: binary mask
at voxel centres, scaled to mm when the cell size is set), `report.json` (spec, design, evidence cards, certificate
summary, disclaimers), `session.jsonl`, and the full certificate when one is held. In live mode the header Export
calls the amm `export` tool (certified geometry model, amm-export/1 report, screening).

## Files

| File | Content |
|---|---|
| `server.py` | Starlette app, routes, SSE, request guards (localhost Host, JSON POSTs), CLI (`--mock` / `--live`) |
| `backend.py` | `MockSession` (mirror), `RecordedIndex`, `JobQueue` (one worker, progress, cancel), `MockBackend`, export |
| `live.py` | `LiveBackend` (amm.tools.Session), `GpuLock`, run-time progress/cancel hooks, band tap |
| `e2e_live.py` | live end-to-end check (headless Edge + CDP, localhost only) |
| `mockdata.py` | recorded development sessions, certificates, atlas rows; amm code hash from source bytes |
| `outcomes.py` | five-outcome evidence cards, the amm-outcome/1 view (`b1_view`) and the certificate view |
| `physics.py` | mirror of `amm.units.normalize`, design validation, cubic E(n), band gaps |
| `geom.py` | preview level sets (same formulas as `amm/geometry.py`), boundary mesh, STL |
| `toolspec.py` | tool contract, materials and family boxes parsed from the amm source with `ast` |

Tests: `python -B -m pytest -q tests/test_app.py` (mock mode, never imports amm) and `tests/test_app_live.py`
(lock protocol and hooks on the CPU; one end-to-end live test, skipped without a GPU or while another runner holds the
solver lock).

## Still stub or second tier

- Agent panel (Propose / Act, chips): stub; the agent is reached through the MCP server.
- Atlas map: plot only (no click-to-load); timeline: list with undo (no branches).
- `as_built` has no button of its own (the certificate runs the same check); `search` has a button but was not part of
  the e2e check (1-15 min of GPU).
- Mock mode serves export and screening only from recordings (none exist for the development sessions).
