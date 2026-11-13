# GUI backend + front end (plan B4/B5), status notes

Started 2026-11-07 while E4 runs. Constraints: no edits in amm/, scripts/bench/, bench/, results/atlas/,
results/bench/, plan/E4_PREREG.md, plan/SOFTWARE_PAPER_PLAN.md; no solver/CUDA/LLM calls; mock mode only.

## Log
- 2026-11-07: kept app/geom.py (preview level sets, same formulas as amm/geometry.py, voxel-centre mask,
  boundary mesh, binary STL) and app/toolspec.py (tool contract + materials parsed from amm source by `ast`, so mock
  mode never imports amm; `import amm` runs a 1x1 PARDISO solve at import). Both reviewed: sound.
- Environment: amm env has starlette 1.7 + uvicorn 0.54, no fastapi, no httpx, no websockets/wsproto
  -> backend is plain Starlette; event stream is SSE (no websocket library installed; no download).
- Mock data: development sessions only (results/bench/smoke/jobs, results/bench/pilot/{B,C}, results/probe/C).
  results/bench/e4 (confirmatory, running) is deliberately NOT read.
- Backend written: app/{physics,mockdata,backend,outcomes,server}.py; toolspec gained families() (BOX/FAMILIES
  parsed from amm/atlas.py, amm/geometry.py).
  * Mock mirror of amm.tools.Session spec tools replays all 18 current-code smoke sessions with identical results
    AND state hashes; certificate keys reproduce the recorded file names. Older pilot/probe sessions (earlier
    code: cert key without material, submit without spec, get_session without budget) differ as expected and are
    flagged `same_code: false`; their certificates are matched by content.
  * Recorded index: 105 solver calls (check_bounds, atlas_suggest, evaluate, search, certify) keyed by args +
    normalized targets + nu + families. evaluate falls back to the nearest search-atlas row (labelled).
  * One-worker JobQueue for evaluate/search/certify; SSE /api/events; export zip (preview STL cell + tiled,
    report.json with evidence cards, session.jsonl, certificate).
- tests/test_app.py: 14 passed (mock only; includes a fresh-interpreter check that amm/cupy/torch/pypardiso are
  never imported).
- Front end: copied C:\AI\AgenticTO_100M\web (config only), then its node_modules (robocopy, 205 MB; no npm
  install, no download). AgenticTO-specific sources removed from the copy; new src/: store (zustand), api (REST +
  EventSource), physics (units, cubic E(n), validity), components SpecPanel, DesignPanel, CellView (R3F voxel
  surface, cell / 3x3x3 tiled), BandDiagram (SVG, target gap, certified safe interval and margins, search-tier
  gaps, Hz axis), StiffnessPanel (C* table search vs certificate + guarded bounds vs targets, E(n) surface),
  EvidencePanel (five outcome cards), Secondary (timeline with undo, atlas map, agent stub). tsc clean; vite build
  -> web/dist (served by the backend).
- .claude/launch.json: amm-gui-mock (backend + built front end, port 8766, loads pilot/C/G01) and amm-web-dev
  (Vite HMR, port 5174, proxies /api to 8766). Both started and checked once, then stopped (own PIDs only).
- Screenshots (headless Microsoft Edge, --screenshot, SwiftShader WebGL, localhost, scratch profile; no Chrome;
  no Playwright/puppeteer in node_modules): paper/figures/gui_mock_{certified_gap, tiled_atlas, undetermined,
  proven_infeasible, not_found, certified_stiffness}.png.
- CDP check (headless Edge driven from the agentto env's `websockets`): event stream connects, Evaluate runs on
  the worker queue and appears in the timeline, Certify of an unrecorded design fails with the mock-mode message.
  Found and fixed: job status could step back when the POST reply arrived after the stream's "done" event.
- Not done / needs live solver after E4: live mode end to end; live band/tensor details; B1 outcome schema;
  B2 certified-geometry export; second-tier panels beyond stubs. No refuted certificate exists in the development
  data, so the "refuted" card is only shown empty.

## 2026-11-08: live mode, B1/B2 wiring, full C*, live e2e check

Constraints kept: edits only in app/, web/, tests/test_app.py, tests/test_app_live.py (new), .claude/launch.json and
this file; amm/, scripts/bench/, results/bench/, results/verification/, plan/ untouched; no npm install, no download, no
LLM call; every GPU use under the shared solver lock; only own PIDs stopped.

- **Live backend** (`app/live.py`, `LiveBackend` moved out of backend.py): wraps `amm.tools.Session` (amm-tools/2).
  Spec tools, check_bounds, atlas_suggest run at once (CPU); while a solve holds the session they answer "session
  busy" instead of blocking the HTTP thread. evaluate, search, certify, as_built go to the one worker and each job
  takes `C:/AI/AgenticMetamaterials_workspaces/gpu.lock` (`GpuLock`: protocol of scripts/ops/gpulock_run.py; wait is
  cancellable and reported; release only removes our own file; released per job, on cancel, on POST /api/shutdown,
  on server exit). export / screen_manufacturing are queued, CPU, no lock.
- **Progress and cancel**: amm has no callbacks, so live.py wraps homogenize, InertiaCounter.counts/edge,
  GPUBands.__call__, adversarial_ks, certify._static_row / static_block / bloch_block / as_built_block and
  evaluate_batch at run time (pass-through; checked equal in tests; no amm source edited, code and checker hashes
  unchanged). Progress events go out on the SSE stream ("progress"); the jobs bar shows stage, counts, elapsed and
  Cancel. Cancel raises `JobCancelled` (BaseException, so amm's fail-closed `except Exception` cannot turn it into a
  verdict) at the next checkpoint (seconds) and the call is rolled back (seq and budget restored, nothing logged).
  The JobQueue gained progress/cancel_event and running-job cancel; mock mode cancels its replay delay the same way.
- **Bands**: a tap on evaluate_batch keeps the band arrays of the session's own evaluate call (Session.evaluate
  returns only the gaps), so the band diagram shows the logged call without an extra solve. The earlier unlogged
  "details" solve of live mode is gone; before Evaluate the panels show the nearest atlas cell, labelled.
- **B1**: `outcomes.b1_view` (both modes): every evidence record with the outcome it supports and `holds` for the
  current spec, `can_cite` per refusal verdict, the submission's amm-outcome/1 card, and the last submit the
  refusal-evidence rule rejected. Evidence panel rebuilt: outcome card with cited records, rejection box with amm's
  message, six tiles (five outcomes + information needed), Submit box (release / refuse + verdict / need_info).
- **B2**: Export panel calls `screen_manufacturing` and `export`; screening table (min solid feature and narrowest
  channel vs printer limit, tiled connectivity, watertight), the screening-only disclaimer always visible, download
  links for cell.stl, tiled STL, report.json and a zip with session.jsonl (`/api/session-files/...`,
  `/api/export-zip/<name>`; paths confined to `<session>/exports`). Header Export = amm export tool in live mode,
  preview bundle in mock mode.
- **Full C\***: stiffness panel shows the 6x6 tensor of evaluate (normalized or MPa) with derived quantities
  (E100/E110/E111 from the full tensor, Zener, cubic deviation, nu12, Voigt/Reuss, eigenvalues) and E(n) from the
  full compliance; mock mode shows the cubic reconstruction from the atlas row, labelled. `physics.tensor_summary`
  mirrors amm.tensor.summary (numpy only).
- **Server**: request guards (POST must be application/json -> 415; Host must be a localhost name -> 403; against
  cross-site posts and DNS rebinding), `GET /api/lock`, `POST /api/shutdown`, lifespan shutdown, `--lock PATH`.
  launch.json: `amm-gui-live` (port 8767).
- **Live e2e** (`python -B -m app.e2e_live --start-server`; headless Edge with a temporary profile, CDP over an own
  stdlib websocket client, localhost only; record `results/gui/sessions/e2e_live_20261108-060513.json`), 96 s, ok:
  1. 316L, a = 5 mm, struts, density <= 0.3, E100 >= 5 GPa: check_bounds FEASIBLE -> atlas_suggest -> sc R=0.211
     r=0.131 -> evaluate 2.6 s (full C*) -> certify cancelled after 8 s (status cancelled, seq 9 -> 9, certify budget
     0) -> certify 43.8 s: **certified**, robust, rung (32, 48, 64) -> release (card certified_candidate citing #10)
     -> screen 7.4 s "screen passed" -> export 7.4 s (outcome certified_candidate, mm): cell.stl 1.08 MB, tiled 3^3
     6.77 MB, report.json (amm-export/1), zip, all downloaded and checked.
  2. Ti6Al4V, density <= 0.2, E100 >= 0.5 E_s: refuse PROVEN_INFEASIBLE first -> rejected by the refusal rule ("No
     evidence record is held for the current spec") and shown -> check_bounds (V1 violated) -> refuse accepted,
     card proven_infeasible citing #5 bound_violation.
  UI spec steps 0.24-0.7 s each (click to logged call; not a V7 measurement).
  Both GUI session logs replay exactly with amm.tools.replay (13 and 6 calls, incl. the certificate and the export
  hashes; the cancelled call left no trace).
- Screenshots (UI, not diagram figures): paper/figures/gui_live_{evaluate_full_tensor, certify_progress, certified,
  export_screening, refusal_rejected, proven_infeasible}.png. The gui_mock_* set is unchanged.
- Mock mode re-checked in headless Edge (pilot/C/G01, X07: no page errors).
- Tests: tests/test_app.py 18 (4 new: B1 view and refusal rule, full-tensor view, running-job cancel, request
  guards); tests/test_app_live.py 3 (lock protocol, hooks pass-through and cancel, live end to end on the GPU:
  evaluate, certify cancel/rollback, screen, export, downloads, exact replay; skipped without CUDA or while another
  runner holds the lock; under gpulock_run it uses a private lock file).
- GPU time (lock held): about 3 min in total (dev checks 0.5, e2e 0.9, replays of the two GUI sessions 1.0, live
  test 0.2, plus the GPU tests of the full suite run under gpulock_run).

### amm issues found (not fixed here: amm/ is frozen for this task; worked around in app/)
1. No progress or cancel hook in certify / search / evaluate. Session._call catches Exception only, so a cancel
   (BaseException) leaves seq and the budget advanced with no record; app/live.py restores both. Suggest: optional
   `progress` and `cancel` callbacks in amm, and a rollback in `_call`.
2. Session.evaluate computes the band arrays (keep_bands=True) but returns only the gaps; the GUI taps
   evaluate_batch. Suggest: optional bands in the evaluate result (a schema addition).
3. `amm.tools.replay(log)` with the default `root=None` fails at every `export` record ("export writes files: it
   needs a session directory") and reports a mismatch; pass `root=`. Suggest: replay into a temporary directory when
   the log holds export calls.
4. The Session lock is held for the whole solve (certify 1-15 min), so every other call blocks (MCP clients too). The
   GUI answers "session busy"; amm could release it around the solve or document it.
5. bloch.certify_gap frees the InertiaCounter outside a `finally`: an exception (or a cancel) between counts leaves a
   PARDISO factorization until garbage collection. Minor.

### Still mock or stub
Agent panel (stub, points to the MCP server); atlas map without click-to-load; timeline without branches; no
as_built button (the certificate runs it); search wired (button, budget) but not in the e2e check (1-15 GPU-min);
mock mode serves export/screen only from recordings (none exist).
- Full suite (under scripts/ops/gpulock_run.py, 2026-11-08 06:10-06:17, after waiting for another runner's lock):
  **151 passed**, 0 skipped, 287 s (was 144; +4 in test_app.py, +3 in test_app_live.py). Lock file absent afterwards;
  no server or Edge process of this work left running.
