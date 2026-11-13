"""Live end-to-end check of the GUI: headless Microsoft Edge driven over the Chrome DevTools Protocol (CDP), against a
live-mode server on localhost only (real amm.tools.Session, real solvers under the shared solver lock).

    python -B -m app.e2e_live --start-server [--port 8767] [--shots paper/figures] [--edge PATH]

Scenarios (each in a new session, every step through the browser UI, as a user would click):
  1. certified: spec (316L, a = 5 mm, struts only, density <= 0.3, E100 >= 5 GPa) -> Check bounds -> Atlas suggest ->
     load the best suggestion -> Evaluate (search tier, full C*) -> Certify, cancelled after the first solves (the
     call is rolled back) -> Certify again (static-only certificate, about 1 min) -> Submit release ->
     Screen manufacturing -> Export STL + report -> the download links are fetched and checked.
  2. refusal: spec with density <= 0.2 and E100 >= 0.5 E_s (violates the Voigt bound) -> Submit refuse before any
     evidence (rejected by the refusal-evidence rule; the rejection is shown) -> Check bounds -> Submit refuse
     PROVEN_INFEASIBLE (accepted; the outcome card cites the bound record).
Screenshots: <shots>/gui_live_*.png. A JSON record of the run (steps, timings, checks) goes to the server's session
root. Nothing here talks to any host but 127.0.0.1. No third-party packages: the CDP websocket client is below.

Edge is started with its own temporary profile (never the user's browser profile) and closed at the end; with
--start-server the server is started as a child process and stopped through POST /api/shutdown (which releases
the solver lock).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


# ================================================================================================================
# minimal websocket client (RFC 6455, client side, text frames) for CDP
# ================================================================================================================
class WebSocket:
    def __init__(self, url: str, timeout: float = 60):
        assert url.startswith("ws://127.0.0.1:") or url.startswith("ws://localhost:"), url
        hostport, path = url[5:].split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket handshake failed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError(head[:200])
        self.buf = head.split(b"\r\n\r\n", 1)[1]

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text: str, opcode: int = 1):
        data = text.encode() if isinstance(text, str) else text
        n = len(data)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 1 << 16:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self) -> str:
        parts = []
        while True:
            b0, b1 = self._read(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 9:  # ping
                self.send(data, opcode=10)
                continue
            if op == 8:
                raise ConnectionError("websocket closed by peer")
            parts.append(data)
            if b0 & 0x80:
                return b"".join(parts).decode()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class CDP:
    def __init__(self, ws_url: str):
        self.ws = WebSocket(ws_url)
        self.n = 0
        self.events: list[dict] = []

    def __call__(self, method: str, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps(dict(id=mid, method=method, params=params)))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            self.events.append(m)
            del self.events[:-200]

    def js(self, expr: str, timeout: float = 30):
        r = self("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True, timeout=int(timeout * 1000))
        if r.get("exceptionDetails"):
            raise RuntimeError(f"js error: {r['exceptionDetails'].get('exception', {}).get('description', r)}")
        return r.get("result", {}).get("value")


# helpers injected into the page: find panels, rows and buttons by their visible text, set React-controlled inputs
HELPERS = r"""
window.__amm = {
  panel(t) { return [...document.querySelectorAll('section.panel')].find(s => (s.querySelector('h2')?.textContent || '').trim().startsWith(t)); },
  scope(s) { return typeof s === 'string' ? (this.panel(s) || (()=>{throw new Error('no panel ' + s)})()) : (s || document); },
  btn(s, t) { const bs = [...this.scope(s).querySelectorAll('button')];
    return bs.find(b => b.textContent.trim() === t) || bs.find(b => b.textContent.trim().startsWith(t)); },
  click(s, t) { const b = this.btn(s, t); if (!b) throw new Error('no button ' + t); if (b.disabled) throw new Error('disabled: ' + t); b.click(); return true; },
  set(el, v) { const p = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(p, 'value').set.call(el, v);
    el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); return true; },
  row(s, label) { return [...this.scope(s).querySelectorAll('.row')].find(r => (r.querySelector('label')?.textContent || '').trim() === label); },
  selectWith(s, optionText) { return [...this.scope(s).querySelectorAll('select')].find(x => [...x.options].some(o => o.textContent === optionText || o.value === optionText)); },
  has(t) { return document.body.innerText.includes(t); },
};
true
"""


# ================================================================================================================
# the run
# ================================================================================================================
class Run:
    def __init__(self, base: str, cdp: CDP, shots: Path, width: int = 1680, height: int = 1250):
        self.base, self.c, self.shots, self.w, self.h = base, cdp, shots, width, height
        self.steps: list[dict] = []
        self.t0 = time.time()
        self.screens: list[str] = []

    # ---- http (status checks only; every action goes through the UI) ----
    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=60) as r:
            return json.loads(r.read())

    def fetch(self, path) -> bytes:
        with urllib.request.urlopen(self.base + path, timeout=120) as r:
            return r.read()

    # ---- ui ----
    def step(self, name, fn, *a, **k):
        t = time.time()
        out = fn(*a, **k)
        self.steps.append(dict(step=name, seconds=round(time.time() - t, 2), t=round(t - self.t0, 1)))
        print(f"  [{time.time() - self.t0:7.1f} s] {name} ({time.time() - t:.2f} s)", flush=True)
        return out

    def js(self, expr, timeout=30):
        return self.c.js(expr, timeout)

    def ui(self, expr):
        self.js(HELPERS)
        return self.js(expr)

    def wait(self, expr, timeout=60, what=""):
        t = time.time()
        while time.time() - t < timeout:
            try:
                self.js(HELPERS)
                if self.js(expr):
                    return round(time.time() - t, 2)
            except RuntimeError:
                pass
            time.sleep(0.25)
        try:
            page = self.js("location.href + ' | ' + document.body.innerText.slice(0, 400)")
        except RuntimeError as ex:
            page = str(ex)
        errs = [e["params"]["exceptionDetails"].get("exception", {}).get("description", "")[:300]
                for e in self.c.events if e.get("method") == "Runtime.exceptionThrown"]
        raise TimeoutError(f"timeout waiting for {what or expr}; page: {page}; page errors: {errs[-3:]}")

    def wait_job(self, tool, n_before, timeout=1800, on_running=None):
        """Wait for the next `tool` job (after n_before jobs of that tool) to finish; returns it."""
        t = time.time()
        seen_running = False
        while time.time() - t < timeout:
            jobs = [j for j in self.get("/api/jobs")["jobs"] if j["tool"] == tool]
            if len(jobs) > n_before:
                j = jobs[n_before]
                if j["status"] == "running" and not seen_running and on_running:
                    seen_running = True
                    on_running(j)
                if j["status"] in ("done", "failed", "cancelled"):
                    return j
            time.sleep(0.5)
        raise TimeoutError(f"{tool} job did not finish in {timeout} s")

    def n_jobs(self, tool):
        return sum(1 for j in self.get("/api/jobs")["jobs"] if j["tool"] == tool)

    def shot(self, name, settle=1.5, toast=False):
        time.sleep(settle)
        if not toast:  # let a notification fade (it covers the lower right corner)
            t = time.time()
            while time.time() - t < 10 and self.js("document.querySelector('.toast') !== null"):
                time.sleep(0.3)
        hgt = max(self.h, int(self.js("Math.ceil(document.documentElement.scrollHeight)")))
        self.c("Emulation.setDeviceMetricsOverride", width=self.w, height=hgt, deviceScaleFactor=1, mobile=False)
        time.sleep(0.8)
        data = self.c("Page.captureScreenshot", format="png", captureBeyondViewport=True)["data"]
        self.c("Emulation.setDeviceMetricsOverride", width=self.w, height=self.h, deviceScaleFactor=1, mobile=False)
        p = self.shots / f"gui_live_{name}.png"
        p.write_bytes(base64.b64decode(data))
        self.screens.append(str(p.relative_to(ROOT)).replace("\\", "/") if p.is_relative_to(ROOT) else str(p))
        print(f"    screenshot {p.name} ({p.stat().st_size // 1024} kB, height {hgt})", flush=True)

    def open(self):
        self.c("Emulation.setDeviceMetricsOverride", width=self.w, height=self.h, deviceScaleFactor=1, mobile=False)
        self.c("Page.navigate", url=self.base + "/")
        self.wait("!!window.__amm && !!window.__amm.panel('Specification') && document.body.innerText.includes('LIVE')",
                  60, "GUI loaded")
        self.wait("document.querySelector('.conn.on') !== null", 30, "event stream connected")

    def new_session(self):
        root = self.summary().get("root")
        self.ui("__amm.click(document.querySelector('header.top'), 'New session')")
        t = time.time()
        while self.summary().get("root") == root:
            if time.time() - t > 30:
                raise TimeoutError("new session")
            time.sleep(0.2)
        self.wait("__amm.has('no targets yet')", 30, "new session")

    def click_logged(self, scope_js, text, n_new=1):
        """Click a button whose tool call runs at once, and wait until the call is logged."""
        n = len([x for x in self.summary()["log"] if x.get("type") == "call"])
        self.ui(f"__amm.click({scope_js}, '{text}')")
        self.wait_seq(n + n_new)

    def set_material(self, name):
        self.ui(f"__amm.set(__amm.selectWith('Specification', '{name}'), '{name}')")
        self.wait(f"__amm.has('nu_s') && __amm.selectWith('Specification', '{name}').value === '{name}'", 30)

    def set_cell(self, mm):
        self.ui(f"__amm.set(__amm.row('Specification', 'Cell size a').querySelector('input'), '{mm}')")
        self.ui("__amm.click(__amm.row('Specification', 'Cell size a'), 'Set')")
        self.wait(f"__amm.row('Specification', 'Cell size a').querySelector('.val').textContent.startsWith('{mm} mm')", 30)

    def families(self, keep):
        for f in ("tpms", "struts", "resonator"):
            js_box = (f"[...__amm.row('Specification', 'Families').querySelectorAll('label.check')]"
                      f".find(l => l.textContent.trim() === '{f}').querySelector('input')")
            want = f in keep
            if bool(self.ui(f"{js_box}.checked")) != want:
                self.ui(f"{js_box}.click()")
                self.wait(f"{js_box}.checked === {str(want).lower()}", 30)

    def add_target(self, key, value, unit=None):
        box = "__amm.panel('Specification').querySelector('.add-target')"
        self.ui(f"__amm.set({box}.querySelector('select'), '{key}')")
        self.ui(f"__amm.set({box}.querySelector('input[aria-label=value]'), '{value}')")
        if unit:
            self.ui(f"__amm.set({box}.querySelectorAll('select')[1], '{unit}')")
        n = len([r for r in self.get("/api/session")["log"] if r.get("type") == "call"])
        self.ui(f"__amm.click({box}, 'Set')")
        self.wait_seq(n + 1)

    def wait_seq(self, n_calls, timeout=30):
        t = time.time()
        while time.time() - t < timeout:
            if len([r for r in self.get("/api/session")["log"] if r.get("type") == "call"]) >= n_calls:
                time.sleep(0.4)
                return
            time.sleep(0.2)
        raise TimeoutError("call not logged")

    def summary(self):
        return self.get("/api/session")


def scenario_certified(r: Run, checks: dict):
    print("scenario 1: spec -> atlas suggestion -> evaluate -> certify (cancel once) -> release -> screen -> export")
    r.step("new session", r.new_session)
    r.step("material 316L", r.set_material, "316L")
    r.step("cell size 5 mm", r.set_cell, 5)
    r.step("families: struts only", r.families, ["struts"])
    r.step("target density <= 0.3", r.add_target, "density_max", 0.3)
    r.step("target E100 >= 5 GPa", r.add_target, "E100_min", 5, "GPa")
    r.step("check bounds", r.click_logged, "'Specification'", "Check bounds")
    cb = [x for x in r.summary()["log"] if x.get("tool") == "check_bounds"][-1]
    checks["check_bounds_verdict"] = cb["result"]["verdict"]
    r.step("atlas suggest", r.click_logged, "'Cell design'", "Atlas suggest")
    r.wait("document.querySelector('.suggest li button') !== null", 30, "suggestions")
    best = r.ui("document.querySelector('.suggest li button').textContent")
    checks["suggestion"] = best
    r.step("load suggestion 1", lambda: (r.ui("document.querySelector('.suggest li button').click()"),
                                         r.wait("document.querySelector('.suggest li.on') !== null", 10)))
    n = r.n_jobs("evaluate")
    r.ui("__amm.click('Cell design', 'Evaluate (search tier)')")
    j = r.step("evaluate (search tier, GPU)", r.wait_job, "evaluate", n, 600)
    checks["evaluate"] = dict(status=j["status"], seconds=round(j["t_end"] - j["t_start"], 2),
                              queue_wait_s=round(j["t_start"] - j["t_queued"], 2))
    res = j["output"]["result"]["results"][0]
    checks["evaluate"].update(E100=res["E100"], density=res["density"], full_tensor="C" in res and len(res["C"]) == 6)
    r.step("full C* shown", r.wait, "!!document.querySelector('table.c6') && __amm.has('full tensor')", 30, "full tensor table")
    r.wait("document.querySelector('.bands svg polyline') !== null", 30, "bands")
    r.shot("evaluate_full_tensor")

    # cancel a running certificate: it stops at the next solver checkpoint and is rolled back
    seq0 = r.summary()["seq"]
    n = r.n_jobs("certify")
    r.ui("__amm.click('Cell design', 'Certify')")
    t_click = time.time()

    def on_running(job):
        r.wait("!!document.querySelector('.jobsbar .stage') && document.querySelector('.jobsbar .stage').textContent.includes('static')",
               120, "progress in the jobs bar")
        time.sleep(4)
        r.shot("certify_progress", settle=0.3, toast=True)
        r.ui("__amm.click(document.querySelector('.jobsbar'), 'Cancel')")
    jc = r.step("certify, cancelled while running", r.wait_job, "certify", n, 900, on_running)
    checks["cancel"] = dict(status=jc["status"], error=jc["output"]["error"], seconds=round(jc["t_end"] - t_click, 1),
                            seq_before=seq0, seq_after=r.summary()["seq"],
                            budget_certify_after=r.summary()["budget_used"]["certify"])
    assert jc["status"] == "cancelled" and checks["cancel"]["seq_after"] == seq0, checks["cancel"]

    n = r.n_jobs("certify")
    r.ui("__amm.click('Cell design', 'Certify')")
    jc = r.step("certify (static-only certificate)", r.wait_job, "certify", n, 1800)
    out = jc["output"]
    checks["certify"] = dict(status=jc["status"], seconds=round(jc["t_end"] - jc["t_start"], 1),
                             verdict=(out.get("result") or {}).get("verdict"), outcome=(out.get("result") or {}).get("outcome"),
                             robust=(out.get("result") or {}).get("robust"), error=out.get("error"),
                             rung=((out.get("result") or {}).get("static") or {}).get("rung"))
    print("   certificate:", checks["certify"], flush=True)
    r.wait("__amm.has('certified safe') || __amm.has('guarded bound')", 30, "certificate in the stiffness panel")
    certified = checks["certify"]["verdict"] == "certified"
    if certified:
        r.ui("__amm.set(document.querySelector('.submitbox select[aria-label=decision]'), 'release')")
        r.ui("__amm.click(document.querySelector('.submitbox'), 'Submit')")
        r.step("submit release", r.wait, "!!document.querySelector('.outcomecard.oc-certified_candidate')", 30, "outcome card")
    r.shot("certified" if certified else f"certify_{checks['certify']['verdict']}")

    n = r.n_jobs("screen_manufacturing")
    r.ui("__amm.click('Export and manufacturing screening', 'Screen manufacturing')")
    js = r.step("screen manufacturing", r.wait_job, "screen_manufacturing", n, 600)
    checks["screen"] = dict(status=js["status"], seconds=round(js["t_end"] - js["t_start"], 1),
                            verdict=(js["output"].get("result") or {}).get("verdict"))
    n = r.n_jobs("export")
    r.ui("__amm.click('Export and manufacturing screening', 'Export STL + report')")
    je = r.step("export STL + report", r.wait_job, "export", n, 600)
    res = je["output"]["result"]
    checks["export"] = dict(status=je["status"], seconds=round(je["t_end"] - je["t_start"], 1), name=res["name"],
                            outcome=res["outcome"], screening=res["screening"]["verdict"], unit=res["unit"])
    r.wait("document.querySelectorAll('.exportfiles a').length >= 3", 30, "download links")
    links = r.ui("[...document.querySelectorAll('.exportfiles a')].map(a => a.getAttribute('href'))")
    got = {}
    for href in links:
        b = r.fetch(href)
        kind = "zip" if href.startswith("/api/export-zip") else href.rsplit("/", 1)[-1]
        ok = (b[:2] == b"PK") if kind == "zip" else (json.loads(b)["schema_version"] == "amm-export/1"
                                                       if kind.endswith(".json") else
                                                       len(b) == 84 + 50 * struct.unpack("<I", b[80:84])[0])
        got[kind] = dict(bytes=len(b), valid=bool(ok))
    checks["downloads"] = got
    assert all(v["valid"] for v in got.values()), got
    r.ui("document.querySelector('section.export').scrollIntoView()")
    r.shot("export_screening")
    return certified


def scenario_refusal(r: Run, checks: dict):
    print("scenario 2: infeasible spec -> refusal rejected without evidence -> check bounds -> proven infeasible")
    r.step("new session", r.new_session)
    r.step("material Ti6Al4V", r.set_material, "Ti6Al4V")
    r.step("target density <= 0.2", r.add_target, "density_max", 0.2)
    r.step("target E100 >= 0.5 E_s", r.add_target, "E100_min", 0.5, "E_s")
    r.ui("__amm.set(document.querySelector('.submitbox select[aria-label=decision]'), 'refuse')")
    r.ui("__amm.set(document.querySelector('.submitbox select[aria-label=verdict]'), 'PROVEN_INFEASIBLE')")
    r.ui("__amm.click(document.querySelector('.submitbox'), 'Submit')")
    r.step("refusal rejected (no evidence held)", r.wait, "!!document.querySelector('.reject')", 30, "rejection shown")
    checks["rejected"] = r.ui("document.querySelector('.reject').textContent")
    r.shot("refusal_rejected", toast=True)
    r.step("check bounds", r.click_logged, "'Specification'", "Check bounds")
    r.wait("[...document.querySelectorAll('.b1rec .ref')].some(x => x.textContent.includes('bound_violation'))", 30,
           "bound record")
    r.ui("__amm.set(document.querySelector('.submitbox select[aria-label=verdict]'), 'PROVEN_INFEASIBLE')")
    r.ui("__amm.click(document.querySelector('.submitbox'), 'Submit')")
    r.step("refuse PROVEN_INFEASIBLE accepted", r.wait, "!!document.querySelector('.outcomecard.oc-proven_infeasible')", 30)
    s = r.summary()
    card = s["outcome"]["card"]
    subs = [(x["seq"], x["ok"], (x.get("error") or "")[:60]) for x in s["log"] if x.get("tool") == "submit"]
    checks["refusal"] = dict(outcome=card["outcome"], cites=[(e["seq"], e["kind"]) for e in card["evidence"]],
                             submits=subs)
    assert card["outcome"] == "proven_infeasible" and subs[0][1] is False and subs[-1][1] is True, subs
    r.shot("proven_infeasible")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--start-server", action="store_true", help="start the live server as a child and stop it after")
    ap.add_argument("--root", default=str(ROOT / "results" / "gui" / "sessions"))
    ap.add_argument("--shots", default=str(ROOT / "paper" / "figures"))
    ap.add_argument("--edge", default=EDGE)
    ap.add_argument("--cdp-port", type=int, default=9331)
    ap.add_argument("--only", choices=("certified", "refusal"), default=None)
    a = ap.parse_args(argv)
    base = f"http://127.0.0.1:{a.port}"
    shots = Path(a.shots)
    shots.mkdir(parents=True, exist_ok=True)
    srv = edge = cdp = profile = None
    record = dict(started=time.strftime("%Y-%m-%d %H:%M:%S"), base=base, checks={})
    t_all = time.time()
    try:
        if a.start_server:
            srv = subprocess.Popen([sys.executable, "-B", "-m", "app.server", "--live", "--port", str(a.port),
                                    "--root", a.root], cwd=str(ROOT))
            record["server_pid"] = srv.pid
            for _ in range(240):
                try:
                    with urllib.request.urlopen(base + "/api/health", timeout=2) as resp:
                        h = json.loads(resp.read())
                    break
                except OSError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("live server did not start")
        with urllib.request.urlopen(base + "/api/health", timeout=10) as resp:
            h = json.loads(resp.read())
        assert h["mode"] == "live", h
        record["health"] = h
        profile = tempfile.mkdtemp(prefix="amm-e2e-edge-")
        edge = subprocess.Popen([a.edge, "--headless=new", f"--remote-debugging-port={a.cdp_port}",
                                 "--remote-debugging-address=127.0.0.1", f"--user-data-dir={profile}",
                                 "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                                 "--disable-sync", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                 "--window-size=1680,1250", "about:blank"])
        record["edge_pid"] = edge.pid
        for _ in range(120):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{a.cdp_port}/json/list", timeout=2) as resp:
                    pages = [p for p in json.loads(resp.read()) if p.get("type") == "page"]
                if pages:
                    break
            except OSError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Edge DevTools endpoint did not come up")
        cdp = CDP(pages[0]["webSocketDebuggerUrl"])
        cdp("Page.enable")
        cdp("Runtime.enable")
        r = Run(base, cdp, shots)
        r.step("open GUI", r.open)
        if a.only in (None, "certified"):
            record["certified"] = scenario_certified(r, record["checks"])
        if a.only in (None, "refusal"):
            scenario_refusal(r, record["checks"])
        record.update(steps=r.steps, screenshots=r.screens, ok=True)
    except BaseException as ex:  # noqa: BLE001 -- record the failure, then clean up
        record.update(ok=False, error=f"{type(ex).__name__}: {ex}")
        raise
    finally:
        record["seconds"] = round(time.time() - t_all, 1)
        if cdp is not None:
            try:
                cdp("Browser.close")
            except Exception:  # noqa: BLE001
                pass
        if edge is not None:
            try:
                edge.wait(15)
            except subprocess.TimeoutExpired:
                pass
            # Edge re-launches itself: stop every process of OUR temporary profile (never any other Edge)
            time.sleep(1)
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine "
                            f"-like '*{Path(profile).name}*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force "
                            "-ErrorAction SilentlyContinue }"], capture_output=True, timeout=60)
        if srv is not None:
            try:
                req = urllib.request.Request(base + "/api/shutdown", data=b"{}", method="POST",
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=60).read()
                srv.wait(60)
            except Exception:  # noqa: BLE001
                srv.terminate()
                srv.wait(30)
            record["server_exit"] = srv.returncode
        out = Path(a.root) / f"e2e_live_{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
        print("record:", out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
