"""V2 GUI phase: start the live GUI server (NOT under gpulock_run: it takes the shared lock per job itself), run the
GUI rows through its HTTP API, the transport rows, then one headless-Edge pass (app/e2e_live.py) against the same
server, and stop the server (POST /api/shutdown; only the PID started here is ever killed).

    python scripts/verify/v2/run_gui_phase.py [--port 8767] [--skip-api] [--skip-edge]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2lib  # noqa: E402

HERE = Path(__file__).resolve().parent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--skip-api", action="store_true")
    ap.add_argument("--skip-edge", action="store_true")
    ap.add_argument("--only", default=None)
    a = ap.parse_args(argv)
    base = f"http://127.0.0.1:{a.port}"
    root = v2lib.SESS / "gui"
    root.mkdir(parents=True, exist_ok=True)
    log = open(v2lib.OUT / f"gui_server_{time.strftime('%Y%m%d-%H%M%S')}.log", "w", encoding="utf-8")
    srv = subprocess.Popen([v2lib.PY, "-B", "-m", "app.server", "--live", "--port", str(a.port), "--root", str(root)],
                           cwd=str(v2lib.ROOT), stdout=log, stderr=subprocess.STDOUT)
    rec = dict(server_pid=srv.pid, started=time.strftime("%Y-%m-%d %H:%M:%S"), steps=[])
    print("GUI server pid", srv.pid, flush=True)
    try:
        for _ in range(240):
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                    rec["health"] = json.loads(r.read())
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("GUI server did not start")
        print("health:", rec["health"], flush=True)
        if not a.skip_api:
            cmd = [v2lib.PY, "-B", str(HERE / "run_v2.py"), "--ifaces", "gui", "--gui", base]
            if a.only:
                cmd += ["--only", a.only]
            t = time.time()
            rec["steps"].append(dict(step="api rows", exit=subprocess.call(cmd, cwd=str(v2lib.ROOT)),
                                     seconds=round(time.time() - t, 1)))
            t = time.time()
            rec["steps"].append(dict(step="transport rows", exit=subprocess.call(
                [v2lib.PY, "-B", str(HERE / "special_v2.py"), "gui", "--gui", base], cwd=str(v2lib.ROOT)),
                seconds=round(time.time() - t, 1)))
        if not a.skip_edge:
            er = v2lib.SESS / "gui_edge"
            shots = v2lib.OUT / "shots"
            t = time.time()
            code = subprocess.call([v2lib.PY, "-B", "-m", "app.e2e_live", "--port", str(a.port), "--root", str(er),
                                    "--shots", str(shots)], cwd=str(v2lib.ROOT))
            rec["steps"].append(dict(step="edge pass", exit=code, seconds=round(time.time() - t, 1)))
            recs = sorted(er.glob("e2e_live_*.json"))
            if recs:
                rec["steps"].append(dict(step="edge rows", exit=subprocess.call(
                    [v2lib.PY, "-B", str(HERE / "special_v2.py"), "edge", "--record", str(recs[-1])], cwd=str(v2lib.ROOT))))
    finally:
        try:
            req = urllib.request.Request(base + "/api/shutdown", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=60).read()
            srv.wait(60)
        except Exception as ex:  # noqa: BLE001
            print("shutdown failed, terminating our server pid", srv.pid, ex, flush=True)
            srv.terminate()
            srv.wait(30)
        rec["server_exit"] = srv.returncode
        rec["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        (v2lib.OUT / "observations" / "main").mkdir(parents=True, exist_ok=True)
        (v2lib.OUT / "observations" / "main" / f"gui_phase_{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(
            json.dumps(rec, indent=1), encoding="utf-8")
        log.close()
        print("GUI phase done:", json.dumps(rec["steps"]), "server exit", srv.returncode, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
