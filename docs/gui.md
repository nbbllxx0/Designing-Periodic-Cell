# Browser GUI

The GUI is a Starlette backend (`app/`) and a built web front end (`web/dist`). Both live in the source tree,
outside the `amm` package, so **the GUI runs from a source checkout only**. The `gui` extra
(`pip install "amm[gui]"`: starlette, uvicorn) installs its Python dependencies, but the wheel contains neither
`app/` nor `web/`. The GUI is still being completed (plan items B4 and B5). `app/README.md` is the authoritative,
up-to-date description. This page covers launching it.

## Launch (mock mode: no solver, no GPU)

From the root of the checkout:

```
python -B -m app.server --mock --port 8766 --load pilot/C/G01
```

Then open <http://127.0.0.1:8766/>. Mock mode never imports `amm` and never opens a CUDA context. Specification
tools run in a mirror of `amm.tools.Session`. Solver tools (`check_bounds`, `atlas_suggest`, `evaluate`,
`search`, `certify`) return recorded results from the development sessions, or a clear "no recorded result" error.
It needs the recorded sessions under `results/` and the built front end in `web/dist`.

Checked for this page (2026-11-08, port 8799, `--root` in a temporary directory): the server was ready in 1.0 s,
`GET /api/tools` returned the tool list in mode `mock`, `GET /` served the front end ("amm - metamaterial cell
design"), and `GET /api/session` returned the session state.

Options (`python -m app.server --help`):

| Option | Meaning |
|---|---|
| `--mock` / `--live` | recorded results only (default), or wrap a real `amm.tools.Session` |
| `--host`, `--port` | default 127.0.0.1:8766 (`AMM_GUI_PORT`) |
| `--root` | where session logs and exports go (default `results/gui/sessions/`) |
| `--load ID` | mock: open a recorded session, for example `pilot/C/G01` (ids from `GET /api/recorded`) |
| `--delay F` | mock: replay solver jobs at fraction F of their recorded duration (capped at 3 s) |
| `--lock PATH` | live: the shared solver lock file (`AMM_GPU_LOCK`) |

## Live mode

```
python -B -m app.server --live --port 8766
```

Live mode imports amm and runs `evaluate`, `search` and `certify` on one worker thread, in order. Specification
tools run at once. It solves on this machine and takes the shared solver lock. Live mode was not exercised for
this page, because it is the GUI work in progress.

## Front-end development

The front end is TypeScript and Vite in `web/`. `app/README.md` gives the commands for the hot-reload dev server
and for rebuilding `web/dist`. Node.js is needed only to change the front end, not to run the GUI.

## REST API

Main routes: `GET /api/tools`, `POST /api/tools/{name}` (`{args, actor, wait}`; solving tools return a job),
`GET /api/session`, `GET /api/jobs`, `POST /api/jobs/{id}/cancel`, `POST /api/details`, `GET /api/preview`,
`GET /api/atlas`, `POST /api/export` and `GET /api/files/{name}`, and `GET /api/events` (server-sent events). The
docstring of `app/server.py` documents them.
