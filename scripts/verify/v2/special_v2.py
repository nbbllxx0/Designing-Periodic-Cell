"""V2 rows that need raw transport access: malformed JSON through MCP (JSON-RPC over stdio, no SDK client) and
through the GUI HTTP API, transport guards, tool lists per profile; and the rows read from the headless-Edge pass.

    python scripts/ops/gpulock_run.py v2 -- python scripts/verify/v2/special_v2.py mcp
    python scripts/verify/v2/special_v2.py gui --gui http://127.0.0.1:8767
    python scripts/verify/v2/special_v2.py edge --record <e2e_live_*.json>
    python scripts/verify/v2/special_v2.py --protocol        # append these expectations (before running)

Expectations (pre-defined, 2026-11-08):
  MCP  mcp_malformed_line     a line that is not JSON: the server stays up, the session log gets no record, the next
                              valid call is answered (a JSON-RPC parse error reply is allowed but not required)
       mcp_args_not_object    tools/call with "arguments": "x": an error reply (JSON-RPC error or isError), no crash,
                              no record
       mcp_wrong_type         tools/call set_target {"density_max": "abc"}: isError, and the failure is logged as a
                              call with ok false (docs/mcp.md: "rejected and logged like any other failure")
       mcp_tools_C / _B       tools/list: 17 tools in profile C, 14 in profile B (no check_bounds, certify, as_built)
  GUI  gui_malformed_json     POST /api/tools/set_target with body "{bad": HTTP 400 "body must be JSON", seq unchanged
       gui_json_not_object    body "[1, 2]": HTTP 400 "JSON object", seq unchanged
       gui_wrong_ctype        Content-Type text/plain: HTTP 415, seq unchanged
       gui_foreign_host       Host: evil.example: HTTP 403
       gui_bad_actor          actor "robot": HTTP 400
       gui_tools_C / _B       GET /api/tools: 17 available in C, 14 in B
       gui_health             GET /api/health: mode live, schema amm-tools/3
  Edge (app/e2e_live.py against the same live server, every action a click in headless Edge)
       edge_certified         scenario 1: certify (after one cancelled run) -> verdict certified; release -> outcome card
       edge_cancel_rollback   the cancelled certify leaves seq and the certify budget unchanged
       edge_screen            screening verdict "screen passed"
       edge_export            export outcome certified_candidate; all download links valid (STL, report.json, zip)
       edge_refusal_rejected  refusal before any evidence rejected (refusal-evidence message shown)
       edge_proven_infeasible refusal after check_bounds accepted: outcome proven_infeasible citing the bound record
"""
from __future__ import annotations

import argparse
import csv
import json
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2lib  # noqa: E402

SPECIAL = [
    ("mcp", "mcp_malformed_line", "invalid: malformed JSON (MCP)", "server alive; no record; next call answered"),
    ("mcp", "mcp_args_not_object", "invalid: arguments not an object (MCP)", "error reply; no crash; no record"),
    ("mcp", "mcp_wrong_type", "invalid: wrong value type, logged (MCP)", "isError; logged with ok false"),
    ("mcp", "mcp_tools_C", "tool list profile C (MCP)", "17 tools"),
    ("mcp", "mcp_tools_B", "tool list profile B (MCP)", "14 tools, no check_bounds/certify/as_built"),
    ("gui", "gui_malformed_json", "invalid: malformed JSON (GUI API)", "HTTP 400 'body must be JSON'; seq unchanged"),
    ("gui", "gui_json_not_object", "invalid: JSON not an object (GUI API)", "HTTP 400 'JSON object'; seq unchanged"),
    ("gui", "gui_wrong_ctype", "invalid: wrong content type (GUI API)", "HTTP 415; seq unchanged"),
    ("gui", "gui_foreign_host", "invalid: foreign Host header (GUI API)", "HTTP 403"),
    ("gui", "gui_bad_actor", "invalid: unknown actor (GUI API)", "HTTP 400"),
    ("gui", "gui_tools_C", "tool list profile C (GUI API)", "17 available"),
    ("gui", "gui_tools_B", "tool list profile B (GUI API)", "14 available"),
    ("gui", "gui_health", "live mode and schema (GUI API)", "mode live, schema amm-tools/3"),
    ("gui-edge", "edge_certified", "certify + release by clicks (Edge)", "verdict certified; outcome card certified"),
    ("gui-edge", "edge_cancel_rollback", "cancel a running certificate (Edge)", "cancelled; seq and budget unchanged"),
    ("gui-edge", "edge_screen", "screening by clicks (Edge)", "screen passed"),
    ("gui-edge", "edge_export", "export + downloads (Edge)", "outcome certified_candidate; downloads valid"),
    ("gui-edge", "edge_refusal_rejected", "refusal without evidence (Edge)", "rejected with the refusal-evidence message"),
    ("gui-edge", "edge_proven_infeasible", "outcome proven_infeasible by clicks (Edge)", "accepted, cites the bound record"),
]
OBS = v2lib.OUT / "observations" / "main"


def row(iface, check, ok, observed, session="", scenario="X_transport"):
    cap = next(c for i, k, c, e in SPECIAL if k == check)
    exp = next(e for i, k, c, e in SPECIAL if k == check)
    return dict(scenario=scenario, check=check, capability=cap, interface=iface, profile="C" if not check.endswith("_B") else "B",
                tool="transport", expected=exp, expected_refusal=check.startswith(("mcp_malformed", "mcp_args", "mcp_wrong",
                                                                                  "gui_malformed", "gui_json", "gui_wrong",
                                                                                  "gui_foreign", "gui_bad", "edge_refusal")),
                observed=observed, passed=bool(ok), failures=[] if ok else [observed], session=session)


# ---- MCP over raw stdio -----------------------------------------------------------------------------------------
class Raw:
    def __init__(self, sdir: Path, profile: str):
        self.p = subprocess.Popen([v2lib.PY, "-B", "-m", "amm.mcp_server", "--session", str(sdir), "--profile", profile],
                                  cwd=str(v2lib.ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        self.q = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.err = []
        threading.Thread(target=lambda: self.err.extend(self.p.stderr), daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.q.put(line.decode("utf-8", "replace"))

    def send(self, obj_or_text):
        t = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text)
        self.p.stdin.write((t + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def recv(self, want_id=None, timeout=60):
        t = time.time()
        while time.time() - t < timeout:
            try:
                m = json.loads(self.q.get(timeout=1))
            except queue.Empty:
                continue
            except json.JSONDecodeError:
                continue
            if want_id is None or m.get("id") == want_id:
                return m
        return None

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(30)
        except Exception:  # noqa: BLE001
            self.p.kill()


def run_mcp():
    rows = []
    for prof in ("C", "B"):
        sdir = v2lib.SESS / "mcp" / f"X_transport_{prof}"
        if sdir.exists():
            raise RuntimeError(f"{sdir} exists")
        sdir.mkdir(parents=True)
        log = sdir / "session.jsonl"
        r = Raw(sdir, prof)
        r.send(dict(jsonrpc="2.0", id=1, method="initialize", params=dict(
            protocolVersion="2025-06-18", capabilities={}, clientInfo=dict(name="v2-raw", version="1"))))
        init = r.recv(1, 120)
        r.send(dict(jsonrpc="2.0", method="notifications/initialized"))
        r.send(dict(jsonrpc="2.0", id=2, method="tools/list", params={}))
        tl = r.recv(2)
        names = [t["name"] for t in (tl or {}).get("result", {}).get("tools", [])]
        sref = str(log.relative_to(v2lib.ROOT)).replace("\\", "/")
        if prof == "C":
            rows.append(row("mcp", "mcp_tools_C", len(names) == 17, f"{len(names)} tools", sref))
            n0 = len(log.read_text(encoding="utf-8").splitlines())
            r.send('{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {')
            rep3 = r.recv(None, 8)
            r.send(dict(jsonrpc="2.0", id=4, method="tools/call", params=dict(name="set_material",
                                                                             arguments={"name": "316L"})))
            rep4 = r.recv(4)
            n1 = len(log.read_text(encoding="utf-8").splitlines())
            alive = r.p.poll() is None
            ok4 = bool(rep4 and not rep4.get("result", {}).get("isError") and "error" not in rep4)
            rows.append(row("mcp", "mcp_malformed_line", alive and ok4 and n1 == n0 + 1,
                            f"reply to the malformed line: {json.dumps(rep3)[:160] if rep3 else 'none'}; alive {alive}; "
                            f"next call ok {ok4}; records +{n1 - n0} (the valid call)", sref))
            r.send(dict(jsonrpc="2.0", id=5, method="tools/call", params=dict(name="set_target", arguments="x")))
            rep5 = r.recv(5, 30)
            n2 = len(log.read_text(encoding="utf-8").splitlines())
            err5 = bool(rep5 and ("error" in rep5 or rep5.get("result", {}).get("isError")))
            rows.append(row("mcp", "mcp_args_not_object", err5 and r.p.poll() is None and n2 == n1,
                            f"reply {json.dumps(rep5)[:200] if rep5 else 'none'}; records +{n2 - n1}", sref))
            r.send(dict(jsonrpc="2.0", id=6, method="tools/call", params=dict(name="set_target",
                                                                             arguments={"density_max": "abc"})))
            rep6 = r.recv(6, 30)
            last = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
            ok6 = bool(rep6 and rep6.get("result", {}).get("isError")) and last.get("tool") == "set_target" \
                and last.get("ok") is False
            txt = "".join(c.get("text", "") for c in (rep6 or {}).get("result", {}).get("content", []))
            rows.append(row("mcp", "mcp_wrong_type", ok6, f"isError {bool(rep6 and rep6.get('result', {}).get('isError'))}: "
                            f"{txt[:120]}; logged ok={last.get('ok')} error={str(last.get('error'))[:80]}", sref))
        else:
            ok = len(names) == 14 and not {"check_bounds", "certify", "as_built"} & set(names)
            rows.append(row("mcp", "mcp_tools_B", ok, f"{len(names)} tools: {sorted(set(names))}", sref))
        r.close()
        (sdir / "raw_transcript.json").write_text(json.dumps(dict(init=init, tools=names, stderr_tail=[
            x.decode("utf-8", "replace") for x in r.err[-20:]]), indent=1), encoding="utf-8")
    return rows


# ---- GUI raw ----------------------------------------------------------------------------------------------------
def run_gui(base):
    g = v2lib.GuiDriver(base, "C")
    sref = str(g.log.relative_to(v2lib.ROOT)).replace("\\", "/") if g.log.is_relative_to(v2lib.ROOT) else str(g.log)
    rows = []

    def seq():
        return g.req("GET", "/api/session")[1]["seq"]

    g.call("set_material", {"name": "316L"})
    s0 = seq()
    code, out = g.req("POST", "/api/tools/set_target", raw=b"{bad")
    rows.append(row("gui", "gui_malformed_json", code == 400 and "body must be JSON" in str(out) and seq() == s0,
                    f"HTTP {code} {out}; seq {seq()} (before {s0})", sref, "X_transport_gui"))
    code, out = g.req("POST", "/api/tools/set_target", raw=b"[1, 2]")
    rows.append(row("gui", "gui_json_not_object", code == 400 and "JSON object" in str(out) and seq() == s0,
                    f"HTTP {code} {out}; seq {seq()}", sref, "X_transport_gui"))
    code, out = g.req("POST", "/api/tools/set_target", raw=json.dumps(dict(args=dict(density_max=0.3))).encode(),
                      headers={"Content-Type": "text/plain"})
    rows.append(row("gui", "gui_wrong_ctype", code == 415 and seq() == s0, f"HTTP {code} {out}; seq {seq()}", sref,
                    "X_transport_gui"))
    code, out = g.req("GET", "/api/session", headers={"Host": "evil.example"})
    rows.append(row("gui", "gui_foreign_host", code == 403, f"HTTP {code} {out}", sref, "X_transport_gui"))
    code, out = g.req("POST", "/api/tools/set_target", dict(args=dict(density_max=0.3), actor="robot"))
    rows.append(row("gui", "gui_bad_actor", code == 400 and seq() == s0, f"HTTP {code} {out}", sref, "X_transport_gui"))
    tl = g.req("GET", "/api/tools")[1]["tools"]
    n = sum(1 for t in tl if t["available"])
    rows.append(row("gui", "gui_tools_C", n == 17, f"{n} available of {len(tl)}", sref, "X_transport_gui"))
    h = g.req("GET", "/api/health")[1]
    rows.append(row("gui", "gui_health", h.get("mode") == "live" and h.get("schema") == "amm-tools/3",
                    f"mode {h.get('mode')}, schema {h.get('schema')}, code {h.get('code')}", sref, "X_transport_gui"))
    gb = v2lib.GuiDriver(base, "B")
    tl = gb.req("GET", "/api/tools")[1]["tools"]
    names = [t["name"] for t in tl if t["available"]]
    ok = len(names) == 14 and not {"check_bounds", "certify", "as_built"} & set(names)
    srefb = str(gb.log.relative_to(v2lib.ROOT)).replace("\\", "/")
    rows.append(row("gui", "gui_tools_B", ok, f"{len(names)} available: {sorted(names)}", srefb, "X_transport_gui"))
    return rows


# ---- Edge record --------------------------------------------------------------------------------------------------
def run_edge(record_path):
    rec = json.loads(Path(record_path).read_text(encoding="utf-8"))
    c = rec.get("checks", {})
    ref = str(Path(record_path).relative_to(v2lib.ROOT)).replace("\\", "/")
    cert = c.get("certify", {})
    rows = [
        row("gui-edge", "edge_certified", rec.get("certified") is True and cert.get("verdict") == "certified",
            f"verdict {cert.get('verdict')}, outcome {cert.get('outcome')}, {cert.get('seconds')} s, rung {cert.get('rung')}",
            ref, "X_edge"),
        row("gui-edge", "edge_cancel_rollback", (c.get("cancel") or {}).get("status") == "cancelled"
            and c["cancel"]["seq_after"] == c["cancel"]["seq_before"] and c["cancel"]["budget_certify_after"] == 0,
            json.dumps(c.get("cancel"))[:220], ref, "X_edge"),
        row("gui-edge", "edge_screen", (c.get("screen") or {}).get("verdict") == "screen passed",
            json.dumps(c.get("screen")), ref, "X_edge"),
        row("gui-edge", "edge_export", (c.get("export") or {}).get("outcome") == "certified_candidate"
            and all(v.get("valid") for v in (c.get("downloads") or {"x": {}}).values()),
            json.dumps(dict(export=c.get("export"), downloads=c.get("downloads")))[:300], ref, "X_edge"),
        row("gui-edge", "edge_refusal_rejected", "refusal needs evidence" in str(c.get("rejected", "")),
            str(c.get("rejected"))[:200], ref, "X_edge"),
        row("gui-edge", "edge_proven_infeasible", (c.get("refusal") or {}).get("outcome") == "proven_infeasible"
            and any(k == "bound_violation" for _, k in (c.get("refusal") or {}).get("cites", [])),
            json.dumps(c.get("refusal")), ref, "X_edge"),
    ]
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", choices=["mcp", "gui", "edge"])
    ap.add_argument("--gui", default="http://127.0.0.1:8767")
    ap.add_argument("--record")
    ap.add_argument("--protocol", action="store_true")
    a = ap.parse_args(argv)
    if a.protocol:
        p = v2lib.OUT / "expectations_transport.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["interface", "check", "capability", "expected"])
            for r in SPECIAL:
                w.writerow(r)
        print(f"{len(SPECIAL)} rows -> {p}")
        return 0
    OBS.mkdir(parents=True, exist_ok=True)
    import amm  # noqa: F401
    rows = run_mcp() if a.what == "mcp" else run_gui(a.gui) if a.what == "gui" else run_edge(a.record)
    out = OBS / f"special__{a.what}.json"
    out.write_text(json.dumps(dict(rows=rows, finished=time.strftime("%Y-%m-%d %H:%M:%S")), indent=1), encoding="utf-8")
    for r in rows:
        print(f"  [{r['interface']}] {r['check']}: {'PASS' if r['passed'] else 'FAIL'}  {r['observed'][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
