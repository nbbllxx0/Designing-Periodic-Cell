"""Optional V6 GUI walkthrough: Case 1's design steps through the LIVE GUI (headless Edge over CDP, the helpers of
app/e2e_live.py), annotated screenshots to paper/figures/gui_case_mount_*.png. No LLM. The GUI takes the solver lock
per job (do NOT wrap this script in gpulock_run).

    python -B scripts/verify/v6/gui_case_mount.py [--port 8768]

Steps (each through the browser UI): new session -> PA12 -> a = 20 mm -> E100 >= 60 MPa -> complete gap
11.5-14.95 kHz -> Check bounds -> Atlas suggest -> load suggestion 1 -> Evaluate -> Certify -> Submit release ->
Screen manufacturing -> Export. Record: results/verification/v6/case1/gui_walkthrough.json.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from app import e2e_live as E  # noqa: E402

SHOTS = ROOT / "paper" / "figures"
V6 = ROOT / "results" / "verification" / "v6"


class MountRun(E.Run):
    def shot(self, name, settle=1.5, toast=False, caption=""):
        time.sleep(settle)
        if not toast:
            t = time.time()
            while time.time() - t < 10 and self.js("document.querySelector('.toast') !== null"):
                time.sleep(0.3)
        hgt = max(self.h, int(self.js("Math.ceil(document.documentElement.scrollHeight)")))
        self.c("Emulation.setDeviceMetricsOverride", width=self.w, height=hgt, deviceScaleFactor=1, mobile=False)
        time.sleep(0.8)
        data = self.c("Page.captureScreenshot", format="png", captureBeyondViewport=True)["data"]
        self.c("Emulation.setDeviceMetricsOverride", width=self.w, height=self.h, deviceScaleFactor=1, mobile=False)
        p = SHOTS / f"gui_case_mount_{name}.png"
        p.write_bytes(base64.b64decode(data))
        annotate(p, caption or name)
        self.screens.append(str(p.relative_to(ROOT)).replace("\\", "/"))
        print(f"    screenshot {p.name}", flush=True)


def annotate(path: Path, caption: str):
    """Caption band above the screenshot (the step and what it shows)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(path).convert("RGB")
    band = 46
    out = Image.new("RGB", (im.width, im.height + band), (32, 44, 64))
    out.paste(im, (0, band))
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    d.text((14, 11), caption, fill=(255, 255, 255), font=font)
    out.save(path)


def add_gap(r, lo, hi, unit="kHz"):
    box = "__amm.panel('Specification').querySelector('.add-target')"
    r.ui(f"__amm.set({box}.querySelector('select'), 'gap')")
    r.ui(f"__amm.set({box}.querySelector('input[aria-label=value]'), '{lo}')")
    r.ui(f"__amm.set({box}.querySelector('input[aria-label=upper]'), '{hi}')")
    r.ui(f"__amm.set({box}.querySelectorAll('select')[1], '{unit}')")
    n = len([x for x in r.get("/api/session")["log"] if x.get("type") == "call"])
    r.ui(f"__amm.click({box}, 'Set')")
    r.wait_seq(n + 1)


def scenario(r: MountRun, ck: dict):
    r.step("new session", r.new_session)
    r.step("material PA12", r.set_material, "PA12")
    r.step("cell size 20 mm", r.set_cell, 20)
    r.step("target E100 >= 60 MPa", r.add_target, "E100_min", 60, "MPa")
    r.step("target gap 11.5-14.95 kHz", add_gap, r, 11.5, 14.95)
    r.step("check bounds", r.click_logged, "'Specification'", "Check bounds")
    cb = [x for x in r.summary()["log"] if x.get("tool") == "check_bounds"][-1]
    ck["check_bounds"] = cb["result"]["verdict"]
    ck["normalized"] = cb["result"]["normalized_targets"]
    r.shot("1_spec", caption=f"1 Spec: PA12, a = 20 mm, E100 >= 60 MPa, complete gap 11.5-14.95 kHz; "
                             f"check_bounds: {ck['check_bounds']}")
    r.step("atlas suggest", r.click_logged, "'Cell design'", "Atlas suggest")
    r.wait("document.querySelector('.suggest li button') !== null", 30, "suggestions")
    ck["suggestion"] = r.ui("document.querySelector('.suggest li button').textContent")
    r.step("load suggestion 1", lambda: (r.ui("document.querySelector('.suggest li button').click()"),
                                         r.wait("document.querySelector('.suggest li.on') !== null", 10)))
    n = r.n_jobs("evaluate")
    r.ui("__amm.click('Cell design', 'Evaluate (search tier)')")
    j = r.step("evaluate", r.wait_job, "evaluate", n, 900)
    ck["evaluate"] = dict(status=j["status"], seconds=round(j["t_end"] - j["t_start"], 1))
    r.wait("document.querySelector('.bands svg polyline') !== null", 30, "bands")
    r.shot("2_evaluate", caption=f"2 Atlas suggestion 1 ({ck['suggestion'][:60]}) evaluated at the search tier: "
                                 "bands, C*, not a certificate")
    n = r.n_jobs("certify")
    r.ui("__amm.click('Cell design', 'Certify')")
    jc = r.step("certify", r.wait_job, "certify", n, 3600)
    out = jc["output"].get("result") or {}
    ck["certify"] = dict(status=jc["status"], seconds=round(jc["t_end"] - jc["t_start"], 1),
                         queue_wait_s=round(jc["t_start"] - jc["t_queued"], 1), verdict=out.get("verdict"),
                         E100_MPa=out.get("E100_MPa"), safe_interval=(out.get("gap") or {}).get("safe_interval"))
    print("   certificate:", ck["certify"], flush=True)
    if out.get("verdict") == "certified":
        r.ui("__amm.set(document.querySelector('.submitbox select[aria-label=decision]'), 'release')")
        r.ui("__amm.click(document.querySelector('.submitbox'), 'Submit')")
        r.step("submit release", r.wait, "!!document.querySelector('.outcomecard.oc-certified_candidate')", 30)
    r.shot("3_certified", caption=f"3 Certificate: {out.get('verdict')} (guarded E100 >= "
                                  f"{(out.get('E100_MPa') or float('nan')):.1f} MPa), released by submit")
    n = r.n_jobs("screen_manufacturing")
    r.ui("__amm.click('Export and manufacturing screening', 'Screen manufacturing')")
    js = r.step("screen", r.wait_job, "screen_manufacturing", n, 600)
    ck["screen"] = (js["output"].get("result") or {}).get("verdict")
    n = r.n_jobs("export")
    r.ui("__amm.click('Export and manufacturing screening', 'Export STL + report')")
    je = r.step("export", r.wait_job, "export", n, 600)
    ck["export"] = dict(status=je["status"], name=(je["output"].get("result") or {}).get("name"))
    r.wait("document.querySelectorAll('.exportfiles a').length >= 3", 30, "download links")
    r.ui("document.querySelector('section.export').scrollIntoView()")
    r.shot("4_export", caption=f"4 Manufacturing screening ({ck['screen']}) and export: cell STL, tiled 3x3x3 STL, "
                               "report.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8768)
    ap.add_argument("--cdp-port", type=int, default=9332)
    a = ap.parse_args()
    base = f"http://127.0.0.1:{a.port}"
    root = V6 / "case1" / "gui_sessions"
    rec = dict(started=time.strftime("%Y-%m-%d %H:%M:%S"), checks={})
    srv = edge = cdp = None
    profile = tempfile.mkdtemp(prefix="amm-v6-edge-")
    t0 = time.time()
    try:
        srv = subprocess.Popen([sys.executable, "-B", "-m", "app.server", "--live", "--port", str(a.port),
                                "--root", str(root)], cwd=str(ROOT))
        for _ in range(240):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=2).read()
                break
            except OSError:
                time.sleep(0.5)
        edge = subprocess.Popen([E.EDGE, "--headless=new", f"--remote-debugging-port={a.cdp_port}",
                                 "--remote-debugging-address=127.0.0.1", f"--user-data-dir={profile}",
                                 "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                                 "--disable-sync", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                 "--window-size=1680,1250", "about:blank"])
        for _ in range(120):
            try:
                pages = [p for p in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{a.cdp_port}/json/list",
                                                                      timeout=2).read()) if p.get("type") == "page"]
                if pages:
                    break
            except OSError:
                pass
            time.sleep(0.5)
        cdp = E.CDP(pages[0]["webSocketDebuggerUrl"])
        cdp("Page.enable")
        cdp("Runtime.enable")
        r = MountRun(base, cdp, SHOTS)
        r.step("open GUI", r.open)
        scenario(r, rec["checks"])
        rec.update(steps=r.steps, screenshots=r.screens, ok=True)
    except BaseException as ex:  # noqa: BLE001
        rec.update(ok=False, error=f"{type(ex).__name__}: {ex}")
        raise
    finally:
        rec["seconds"] = round(time.time() - t0, 1)
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
        (V6 / "case1" / "gui_walkthrough.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
