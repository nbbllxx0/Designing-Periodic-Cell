"""GUI server: REST and server-sent events over the amm tool contract (plain Starlette; no FastAPI needed).

Run (mock, the default while E4 runs: no solver, no CUDA, amm is never imported):
    python -m app.server --mock [--port 8766] [--load smoke/codex-C-r1-S01] [--delay 0.02]
Run (live: wraps amm.tools.Session; solves on the one worker thread, each solve holding the shared solver lock
C:/AI/AgenticMetamaterials_workspaces/gpu.lock):
    python -m app.server --live [--port 8767]

Pattern from AgenticTO (agentto.app.server): one session per app, every tool call logged, solves on one worker,
every record broadcast to all clients. New code; the event stream is SSE (no websocket library needed).

REST (JSON):
  GET  /api/health                 mode, versions, code hash
  GET  /api/tools                  tool contract (parsed from amm source), with availability and queueing
  GET  /api/materials | /api/families
  GET  /api/session                state, normalized targets, certificates, submission, log tail, evidence cards
  GET  /api/session/record/{seq}   one full log record
  POST /api/session/new            {profile}
  GET  /api/recorded               recorded development sessions (mock)
  POST /api/recorded/load          {id}  (mock)
  POST /api/tools/{name}           {args, actor, wait}: solving tools return {job}; others the tool output
  GET  /api/jobs | /api/jobs/{id}  POST /api/jobs/{id}/cancel
  POST /api/details                {design}: tensor, E(n) summary, bands, certificate view
  GET  /api/preview                ?kind=&params=<json>&n=: preview surface mesh
  GET  /api/atlas                  ?nu=&limit=: atlas map points (search tier)
  POST /api/export                 mock: preview bundle {design?, tiles, n}; GET /api/files/{name} downloads it
                                   (live: the amm `export` tool, POST /api/tools/export)
  GET  /api/session-files/{path}   a file the amm export tool wrote (exports/<name>/cell.stl, ...)
  GET  /api/export-zip/{name}      one amm export folder plus session.jsonl as a zip
  GET  /api/lock                   the shared solver lock: file, owner, held by this server
  POST /api/shutdown               stop the server cleanly (cancels a running solve, releases the lock)
  GET  /api/events                 SSE: hello, record, session, job, progress, export

Every POST must send Content-Type application/json and every request a localhost Host header (no cross-site form
posts, no DNS rebinding); the server binds to localhost only.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import time
from functools import lru_cache
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__, backend as bk, geom, mockdata, physics, toolspec

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "results" / "gui" / "sessions"
WEB_DIST = ROOT / "web" / "dist"


def _json(x, status=200):
    return JSONResponse(json.loads(bk.canon(x)), status_code=status)


def _err(msg, status=400):
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


async def _body(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        return {}
    try:
        b = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("body must be JSON")
    if not isinstance(b, dict):
        raise ValueError("body must be a JSON object")
    return b


@lru_cache(maxsize=64)
def _preview(kind: str, params_json: str, n: int) -> dict:
    return geom.preview(kind, json.loads(params_json), n)


LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def _host_ok(request: Request) -> bool:
    h = (request.headers.get("host") or "").strip().lower()
    if h.startswith("["):
        name = h.split("]")[0] + "]"
    else:
        name = h.rsplit(":", 1)[0] if ":" in h else h
    return name in LOCAL_HOSTS


def create_app(be: bk.Backend, request_exit=None) -> Starlette:
    clients: set[asyncio.Queue] = set()
    state = dict(loop=None)

    def on_event(ev):
        loop = state["loop"]
        if loop is None:
            return
        for q in list(clients):
            loop.call_soon_threadsafe(q.put_nowait, ev)

    be.bus.listeners.append(on_event)

    def wrap(fn):
        async def handler(request: Request):
            state["loop"] = asyncio.get_running_loop()
            if not _host_ok(request):
                return _err("the GUI server answers localhost requests only", 403)
            if request.method == "POST" and not (request.headers.get("content-type") or "").startswith(
                    "application/json"):
                return _err("POST requests must send Content-Type: application/json", 415)
            try:
                return await fn(request)
            except KeyError as ex:
                return _err(f"not found: {ex}", 404)
            except ValueError as ex:
                return _err(str(ex), 400)
        return handler

    def threaded(fn):
        """Run a blocking backend call off the event loop."""
        return asyncio.get_running_loop().run_in_executor(None, fn)

    # ---- handlers ---------------------------------------------------------------------------------------------
    async def health(request):
        schema, code = bk.SCHEMA_VERSION, mockdata.code_hash()
        if be.mode == "live":  # report the identity of the amm that serves the calls, not the mock mirror's
            import amm.tools as _amm_tools
            schema, code = _amm_tools.SCHEMA_VERSION, _amm_tools.code_hash()
        return _json(dict(ok=True, mode=be.mode, version=__version__, schema=schema,
                          code=code, pid=os.getpid(),
                          worker=dict(alive=be.queue.worker.is_alive(), current=be.queue.current),
                          lock=_lock_info()))

    def _lock_info():
        lk = getattr(be, "lock", None)
        if lk is None:
            return dict(used=False, note="mock mode: no solver runs, the shared solver lock is never taken")
        return dict(used=True, path=str(lk.path), held_by_this_server=lk.held, owner=lk.owner() or None)

    async def lock(request):
        return _json(_lock_info())

    async def shutdown(request):
        if request_exit is None:
            raise ValueError("shutdown is not available (server not started by app.server.main)")
        await threaded(be.shutdown)
        request_exit()
        return _json(dict(ok=True, stopping=True, pid=os.getpid()))

    async def session_file(request):
        p = be.session_file(request.path_params["path"])
        return FileResponse(p, filename=p.name)

    async def export_zip(request):
        data, name = await threaded(lambda: be.export_zip(request.path_params["name"]))
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    async def tools(request):
        return _json(dict(mode=be.mode, tools=be.tool_list()))

    async def materials(request):
        return _json(dict(materials=physics.materials(), units=dict(E="Pa", rho="kg/m^3", min_feature="m",
                                                                    tolerance="m"),
                          source="amm/units.py (typical datasheet values; inputs of a request, not claims)"))

    async def families(request):
        return _json(toolspec.families())

    async def session(request):
        tail = int(request.query_params.get("tail", 200))
        return _json(await threaded(lambda: be.summary(tail)))

    async def record(request):
        seq = int(request.path_params["seq"])
        for r in be.records():
            if r.get("type") == "call" and r.get("seq") == seq:
                return _json(r)
        raise KeyError(f"record {seq}")

    async def new_session(request):
        b = await _body(request)
        prof = b.get("profile", "C")
        if prof not in ("B", "C"):
            raise ValueError("profile must be B or C")
        return _json(await threaded(lambda: be.new_session(prof)))

    async def recorded(request):
        if be.mode != "mock":
            return _json(dict(sessions=[]))
        checks = getattr(be.index, "replay_checks", {})
        return _json(dict(sessions=[dict(m, replay=checks.get(k)) for k, m in mockdata.sessions().items()]))

    async def recorded_load(request):
        if be.mode != "mock":
            raise ValueError("recorded sessions load in mock mode only")
        b = await _body(request)
        return _json(await threaded(lambda: be.load_recorded(str(b.get("id", "")))))

    async def call_tool(request):
        b = await _body(request)
        name = request.path_params["name"]
        actor = b.get("actor", "user")
        if actor not in ("user", "agent", "script"):
            raise ValueError("actor must be user, agent or script")
        wait = bool(b.get("wait", False))
        return _json(await threaded(lambda: be.call(name, b.get("args") or {}, actor, wait=wait,
                                                    timeout=float(b.get("timeout", 3600)))))

    async def jobs(request):
        return _json(dict(jobs=be.queue.list(), current=be.queue.current))

    async def job(request):
        j = be.queue.jobs.get(request.path_params["id"])
        if j is None:
            raise KeyError(request.path_params["id"])
        return _json(be.queue.public(j))

    async def job_cancel(request):
        return _json(dict(cancelled=be.queue.cancel(request.path_params["id"])))

    async def details(request):
        b = await _body(request)
        d = b.get("design")
        if not isinstance(d, dict):
            raise ValueError("body needs {design: {kind, params}}")
        return _json(await threaded(lambda: be.details(d)))

    async def preview(request):
        q = request.query_params
        kind = q.get("kind", "")
        n = int(q.get("n", 32))
        if not 8 <= n <= 64:
            raise ValueError("n must be 8-64")
        params = json.loads(q.get("params", "{}"))
        if kind not in geom.FAMILY_OF:
            raise ValueError(f"unknown kind {kind!r}")
        p = await threaded(lambda: _preview(kind, json.dumps(params, sort_keys=True), n))
        return _json(p)

    async def atlas_map(request):
        nu = float(request.query_params.get("nu", 0.3))
        limit = int(request.query_params.get("limit", 0)) or None
        if not mockdata.atlas_rows_exist(nu):
            return _json(dict(nu=nu, available=False, points=[], atlases=mockdata.atlas_nus()))
        pts = await threaded(lambda: mockdata.atlas_points(nu, limit))
        return _json(dict(nu=nu, available=True, points=pts, tier="search (not certified)"))

    async def export(request):
        b = await _body(request)
        return _json(await threaded(lambda: be.export(b.get("design"), int(b.get("tiles", 3)), int(b.get("n", 40)))))

    async def files(request):
        name = request.path_params["name"]
        d = be.export_dir().resolve()
        p = (d / name).resolve()
        if p.parent != d or not p.is_file():
            raise KeyError(name)
        return FileResponse(p, filename=name)

    async def events(request: Request):
        q: asyncio.Queue = asyncio.Queue()
        clients.add(q)

        async def gen():
            try:
                hello = dict(type="hello", mode=be.mode, version=__version__, t=time.time(), seq=be.session.seq)
                yield f"event: message\ndata: {json.dumps(hello)}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=15)
                        yield f"data: {bk.canon(ev)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                clients.discard(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    routes = [
        Route("/api/health", wrap(health)),
        Route("/api/tools", wrap(tools)),
        Route("/api/materials", wrap(materials)),
        Route("/api/families", wrap(families)),
        Route("/api/session", wrap(session)),
        Route("/api/session/record/{seq:int}", wrap(record)),
        Route("/api/session/new", wrap(new_session), methods=["POST"]),
        Route("/api/recorded", wrap(recorded)),
        Route("/api/recorded/load", wrap(recorded_load), methods=["POST"]),
        Route("/api/tools/{name}", wrap(call_tool), methods=["POST"]),
        Route("/api/jobs", wrap(jobs)),
        Route("/api/jobs/{id}", wrap(job)),
        Route("/api/jobs/{id}/cancel", wrap(job_cancel), methods=["POST"]),
        Route("/api/details", wrap(details), methods=["POST"]),
        Route("/api/preview", wrap(preview)),
        Route("/api/atlas", wrap(atlas_map)),
        Route("/api/export", wrap(export), methods=["POST"]),
        Route("/api/files/{name}", wrap(files)),
        Route("/api/session-files/{path:path}", wrap(session_file)),
        Route("/api/export-zip/{name}", wrap(export_zip)),
        Route("/api/lock", wrap(lock)),
        Route("/api/shutdown", wrap(shutdown), methods=["POST"]),
        Route("/api/events", wrap(events)),
    ]
    if WEB_DIST.is_dir():
        routes.append(Mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web"))
    else:
        async def index(request):
            return Response("amm GUI backend. Front end: cd web && npm run dev (Vite proxies /api).",
                            media_type="text/plain")
        routes.append(Route("/", index))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:  # server stopping: cancel a running solve, release the solver lock
            await asyncio.get_running_loop().run_in_executor(None, be.shutdown)

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.backend = be
    return app


def build_backend(mode: str, root: Path, delay: float = 0.0, load: str | None = None,
                  lock_path: str | None = None) -> bk.Backend:
    root.mkdir(parents=True, exist_ok=True)
    if mode == "mock":
        return bk.MockBackend(root, delay_scale=delay, load=load)
    if mode == "live":
        from . import live  # noqa: PLC0415 -- imports amm (live mode only)
        return live.LiveBackend(root, lock_path=Path(lock_path) if lock_path else None)
    raise ValueError(mode)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mock", action="store_true", help="recorded results only, no solver (default)")
    g.add_argument("--live", action="store_true", help="wrap amm.tools.Session (imports amm; solves)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("AMM_GUI_PORT", 8766)))
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="where session logs and exports are written")
    ap.add_argument("--load", default=None, help="mock: recorded session to open, e.g. pilot/C/G01")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="mock: replay solver jobs at this fraction of their recorded duration (capped at 3 s)")
    ap.add_argument("--lock", default=None, help="live: the shared solver lock file (default "
                    "C:/AI/AgenticMetamaterials_workspaces/gpu.lock, or AMM_GPU_LOCK)")
    a = ap.parse_args(argv)
    mode = "live" if a.live else "mock"
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("the GUI server binds to localhost only")
    be = build_backend(mode, Path(a.root), a.delay, a.load, lock_path=a.lock)
    import uvicorn
    holder = {}
    app = create_app(be, request_exit=lambda: setattr(holder["server"], "should_exit", True))
    server = uvicorn.Server(uvicorn.Config(app, host=a.host, port=a.port, log_level="warning"))
    holder["server"] = server
    print(f"amm GUI backend ({mode}) on http://{a.host}:{a.port}  pid {os.getpid()}", flush=True)
    try:
        server.run()
    finally:
        be.shutdown()  # also on Ctrl+C: never leave the solver lock behind


if __name__ == "__main__":
    main()
