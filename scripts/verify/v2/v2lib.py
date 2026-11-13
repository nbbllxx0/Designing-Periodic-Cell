"""V2 drivers (library, MCP client, GUI HTTP API, CLI), predicate checks and the scenario runner.

Every driver returns the same normalized call output {ok, seq, result | error} so that one expectation is checked
the same way through every interface. No LLM is called anywhere. The MCP driver is an MCP client with no model
(the pattern of examples/04_mcp_client_probe.py); the GUI driver talks to a running live server on 127.0.0.1 only.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "verification" / "v2"
SESS = OUT / "sessions"
PY = sys.executable


# =================================================================================================================
# path access and predicates
# =================================================================================================================
_TOK = re.compile(r"([^.\[\]]+)|\[(\*|\d+)\]")


def get(obj, path: str):
    """Value at a dotted path with [i] / [*]; a [*] returns a list. Missing -> KeyError."""
    cur = [obj]
    star = False
    for name, idx in _TOK.findall(path):
        nxt = []
        for c in cur:
            if name:
                if not isinstance(c, dict) or name not in c:
                    raise KeyError(path)
                nxt.append(c[name])
            elif idx == "*":
                if not isinstance(c, list):
                    raise KeyError(path)
                nxt.extend(c)
                star = True
            else:
                i = int(idx)
                if not isinstance(c, list) or i >= len(c):
                    raise KeyError(path)
                nxt.append(c[i])
        cur = nxt
    return cur if star else cur[0]


def resolve(v, labels: dict):
    if isinstance(v, str) and v.startswith("$") and "." in v and v[1:].split(".", 1)[0] in labels:
        lab, p = v[1:].split(".", 1)
        return get(labels[lab], p)
    if isinstance(v, dict):
        return {k: resolve(x, labels) for k, x in v.items()}
    if isinstance(v, list):
        return [resolve(x, labels) for x in v]
    return v


def check(expect: list, o: dict, labels: dict, report=None) -> tuple[bool, list[str]]:
    """Evaluate the predicates on output o. Returns (passed, list of failure texts)."""
    fails = []
    for e in expect:
        k = e[0]
        try:
            if k == "ok":
                if bool(o.get("ok")) != e[1]:
                    fails.append(f"ok={o.get('ok')} (expected {e[1]}); " + str(o.get("error") or "")[:200])
            elif k == "exit":
                if o.get("exit") != e[1]:
                    fails.append(f"exit {o.get('exit')} (expected {e[1]})")
            elif k == "refused_or":
                lab = labels.get(e[2]) if len(e) > 2 else None
                if (lab is not None and not lab.get("ok")) or not o.get("ok"):
                    continue
                r = o.get("result") or {}
                if not (r.get("verdict") == "PROVEN_INFEASIBLE" and any(b.get("bound") == e[1]
                                                                         for b in r.get("violated", []))):
                    fails.append(f"accepted: verdict {r.get('verdict')}, violated {[b.get('bound') for b in r.get('violated', [])]}")
            elif k == "report":
                if report is None:
                    fails.append("no report.json")
                    continue
                want = resolve(e[2], labels)
                try:
                    got = get(report, e[1])
                except KeyError:
                    got = "<missing>"
                if got != want:
                    fails.append(f"report.{e[1]} = {got!r} (expected {want!r})")
            else:
                path = e[1]
                want = resolve(e[2], labels) if len(e) > 2 else None
                try:
                    got = get(o, path)
                except KeyError:
                    fails.append(f"{path} missing")
                    continue
                if k == "eq" and got != want:
                    fails.append(f"{path} = {got!r} (expected {want!r})")
                elif k == "approx" and not (isinstance(got, (int, float)) and abs(got - want) <= e[3] * abs(want)):
                    fails.append(f"{path} = {got!r} (expected {want!r} rtol {e[3]})")
                elif k == "in" and got not in want:
                    fails.append(f"{path} = {got!r} (expected one of {want})")
                elif k == "all_in" and not (isinstance(got, list) and got and all(g in want for g in got)):
                    fails.append(f"{path} = {got!r} (expected all in {want})")
                elif k == "has" and str(want).lower() not in json.dumps(got).lower():
                    fails.append(f"{path} does not contain {want!r}: {str(got)[:240]}")
                elif k == "not_contains" and want in got:
                    fails.append(f"{path} contains {want!r}")
                elif k == "len" and len(got) != want:
                    fails.append(f"len({path}) = {len(got)} (expected {want})")
                elif k == "len_ge" and len(got) < want:
                    fails.append(f"len({path}) = {len(got)} (expected >= {want})")
                elif k == "true" and got is not True:
                    fails.append(f"{path} = {got!r} (expected True)")
                elif k == "false" and got is not False:
                    fails.append(f"{path} = {got!r} (expected False)")
                elif k == "none" and got is not None:
                    fails.append(f"{path} = {got!r} (expected None)")
                elif k == "notnone" and got is None:
                    fails.append(f"{path} is None")
        except Exception as ex:  # noqa: BLE001
            fails.append(f"check error {e}: {type(ex).__name__}: {ex}")
    return not fails, fails


def observed_summary(o: dict) -> str:
    if "exit" in o and o.get("cli_raw") is not None and o.get("tool") is None:
        r = o.get("cli_raw") or {}
        if o["exit"]:
            return f"exit {o['exit']}; {str(r.get('usage_error') or (r.get('error') or {}).get('error') or '')[:200]}"
        return f"exit 0; " + observed_summary(dict(ok=True, result=r.get("result")))
    if not o.get("ok"):
        return "refused: " + str(o.get("error"))[:220]
    r = o.get("result")
    if isinstance(r, dict):
        bits = []
        for k in ("verdict", "outcome", "passed", "exact"):
            if k in r:
                bits.append(f"{k}={r[k]}")
        if isinstance(r.get("atlas"), dict):
            bits.append(f"atlas={r['atlas'].get('verdict')}")
        if r.get("violated"):
            bits.append("violated=" + ",".join(b["bound"] for b in r["violated"]))
        if isinstance(r.get("outcome_card"), dict):
            bits.append("outcome=" + str(r["outcome_card"].get("outcome")))
        if "normalized" in r:
            bits.append("normalized=" + json.dumps(r["normalized"], sort_keys=True)[:140])
        if "best" in r and isinstance(r["best"], list):
            bits.append("kinds=" + ",".join(b["design"]["kind"] for b in r["best"]))
        if "results" in r and isinstance(r["results"], list):
            bits.append(f"{len(r['results'])} results")
        return "accepted" + (": " + "; ".join(bits) if bits else "")
    return "accepted"


# =================================================================================================================
# drivers
# =================================================================================================================
class LibDriver:
    name = "lib"

    def __init__(self, sdir: Path, profile: str):
        from amm import tools
        self.root = sdir
        self.s = tools.Session(sdir, profile=profile)
        self.log = sdir / "session.jsonl"

    def call(self, tool, args):
        out = self.s.call(tool, args, actor="script")
        return dict(ok=out["ok"], seq=out.get("seq"), **({"result": out["result"]} if out["ok"] else {"error": out["error"]}))

    def close(self):
        pass


class McpDriver:
    """An MCP client (no LLM) over stdio: python -B -m amm.mcp_server --session DIR --profile P."""
    name = "mcp"

    def __init__(self, sdir: Path, profile: str):
        self.root, self.log = sdir, sdir / "session.jsonl"
        self.loop = asyncio.new_event_loop()
        self.ready, self.err = threading.Event(), None
        self.th = threading.Thread(target=self._run, args=(sdir, profile), daemon=True)
        self.th.start()
        if not self.ready.wait(180):
            raise RuntimeError(f"MCP server did not start: {self.err}")
        if self.err:
            raise RuntimeError(self.err)

    def _run(self, sdir, profile):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main(sdir, profile))
        except BaseException as ex:  # noqa: BLE001
            self.err = f"{type(ex).__name__}: {ex}"
            self.ready.set()

    async def _main(self, sdir, profile):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=PY, args=["-B", "-m", "amm.mcp_server", "--session", str(sdir),
                                                         "--profile", profile], env=dict(os.environ), cwd=str(ROOT))
        self.stop = asyncio.Event()
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w, read_timeout_seconds=3600) as s:
                await s.initialize()
                self.s = s
                self.tools = [t.name for t in (await s.list_tools()).tools]
                self.ready.set()
                await self.stop.wait()

    def _last_seq(self):
        try:
            lines = self.log.read_text(encoding="utf-8").splitlines()
            return json.loads(lines[-1]).get("seq")
        except Exception:  # noqa: BLE001
            return None

    def call(self, tool, args):
        n_before = len(self.log.read_text(encoding="utf-8").splitlines()) if self.log.exists() else 0
        fut = asyncio.run_coroutine_threadsafe(self.s.call_tool(tool, args, read_timeout_seconds=3600), self.loop)
        res = fut.result(3700)
        text = "".join(getattr(c, "text", "") for c in res.content)
        n_after = len(self.log.read_text(encoding="utf-8").splitlines()) if self.log.exists() else 0
        seq = self._last_seq() if n_after > n_before else None
        if res.is_error:
            return dict(ok=False, seq=seq, error=text)
        try:
            return dict(ok=True, seq=seq, result=json.loads(text))
        except json.JSONDecodeError:
            return dict(ok=True, seq=seq, result=text)

    def close(self):
        if hasattr(self, "stop"):
            self.loop.call_soon_threadsafe(self.stop.set)
        self.th.join(60)


class GuiDriver:
    """The live GUI's HTTP API (POST /api/tools/{name} with wait=True). One GUI session per scenario."""
    name = "gui"

    def __init__(self, base: str, profile: str):
        self.base = base
        summ = self.post("/api/session/new", {"profile": profile})
        self.root = Path(summ["root"])
        self.log = self.root / "session.jsonl"

    def req(self, method, path, body=None, headers=None, raw: bytes | None = None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=3700) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as ex:
            try:
                return ex.code, json.loads(ex.read() or b"null")
            except json.JSONDecodeError:
                return ex.code, None

    def post(self, path, body):
        code, out = self.req("POST", path, body)
        if code != 200:
            raise RuntimeError(f"{path}: HTTP {code} {out}")
        return out

    def call(self, tool, args):
        code, out = self.req("POST", f"/api/tools/{tool}", dict(args=args, actor="user", wait=True, timeout=3600))
        if code != 200:
            return dict(ok=False, seq=None, error=f"HTTP {code}: {out}")
        if "job" in out:
            job = out["job"]
            o = job.get("output") or dict(ok=False, error=f"job {job.get('status')}: {job.get('error')}")
        else:
            o = out
        return dict(ok=bool(o.get("ok")), seq=o.get("seq"), **({"result": o.get("result")} if o.get("ok")
                                                                else {"error": o.get("error")}))

    def close(self):
        pass


CLI_CMD = {"check_bounds": "check-bounds", "atlas_suggest": "atlas-suggest", "evaluate": "evaluate",
           "certify": "certify", "export": "export"}
SPEC_TOOLS = ("set_material", "set_constraints", "set_target")


class CliDriver:
    """`python -B -m amm.cli` (the `amm` console script). The CLI has no persistent session: the scenario's spec
    steps are accumulated here (test harness, not CLI logic) and passed with --spec to each invocation, which is a
    new session directory."""
    name = "cli"

    def __init__(self, sdir: Path, profile: str):
        self.dir, self.profile, self.n = sdir, profile, 0
        self.spec = {}
        self.root = None
        self.last_session = None
        self.sessions = []

    def run(self, argv: list[str], use_spec=True, session=True):
        self.n += 1
        argv = list(argv)
        sub = argv[0]
        sd = self.dir / f"{self.n:02d}-{sub}"
        extra = []
        if sub != "replay" and session and "--nosession" not in argv:
            extra += ["--session", str(sd)]
        argv = [a for a in argv if a != "--nosession"]
        if sub != "replay" and "--profile" not in argv and sub in CLI_CMD.values():
            extra += ["--profile", self.profile]
        if use_spec and self.spec and sub in CLI_CMD.values():
            self.dir.mkdir(parents=True, exist_ok=True)
            sp = self.dir / f"{self.n:02d}-spec.json"
            sp.write_text(json.dumps(self.spec, indent=1), encoding="utf-8")
            extra += ["--spec", str(sp)]
        argv = [self.last_session if a == "$last_cli_session" else a for a in argv]
        cmd = [PY, "-B", "-m", "amm.cli"] + argv[:1] + extra + argv[1:]
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=3700)
        try:
            out = json.loads(p.stdout) if p.stdout.strip() else None
        except json.JSONDecodeError:
            out = None
        if "--session" in extra and (sd / "session.jsonl").exists():
            self.root, self.last_session = sd, str(sd / "session.jsonl")
            self.sessions.append(str(sd / "session.jsonl"))
        (self.dir).mkdir(parents=True, exist_ok=True)
        (self.dir / f"{self.n:02d}-{sub}.stdout.json").write_text(p.stdout, encoding="utf-8")
        if p.stderr.strip():
            (self.dir / f"{self.n:02d}-{sub}.stderr.txt").write_text(p.stderr, encoding="utf-8")
        return p.returncode, out, cmd

    def merge(self, tool, args):
        a = dict(args)
        if tool == "set_material":
            self.spec["material"] = a
        elif tool == "set_constraints":
            self.spec["constraints"] = dict(self.spec.get("constraints") or {}, **a)
        else:
            clear = a.pop("clear", False)
            self.spec["targets"] = a if clear else dict(self.spec.get("targets") or {}, **a)

    def call(self, tool, args):
        """A generic scenario step: spec tools run as part of `check-bounds` (their own call entry is the result);
        tool steps run their subcommand with the accumulated spec."""
        if tool in SPEC_TOOLS:
            saved = json.loads(json.dumps(self.spec))
            self.merge(tool, args)
            code, out, cmd = self.run(["check-bounds"])
            entry = next((c for c in (out or {}).get("calls", []) if c["tool"] == tool), None)
            if entry is None:
                return dict(ok=False, error=f"CLI exit {code}: no {tool} call", exit=code, cli_raw=out)
            if not entry["ok"]:
                self.spec = saved
            return dict(ok=entry["ok"], seq=entry.get("seq"), exit=code, cli_raw=out, tool=tool,
                        **({"result": entry["result"]} if entry["ok"] else {"error": entry["error"]}))
        sub = CLI_CMD[tool]
        argv = [sub]
        if tool == "atlas_suggest" and "top" in args:
            argv += ["--top", str(args["top"])]
        if tool == "evaluate":
            for d in args["designs"]:
                argv += ["--design", json.dumps(d)]
            if args.get("bands"):
                argv.append("--bands")
        if tool in ("certify", "export"):
            argv += ["--design", json.dumps(args["design"])]
        if tool == "export":
            for k, f in (("tiles", "--tiles"), ("resolution", "--resolution"), ("tile_resolution", "--tile-resolution"),
                         ("printer_min_feature_mm", "--printer-min-feature-mm")):
                if k in args:
                    argv += [f, str(args[k])]
        code, out, cmd = self.run(argv)
        calls = (out or {}).get("calls", [])
        entry = next((c for c in calls if c["tool"] == tool), None) or (calls[-1] if calls else None)
        if entry is None:
            return dict(ok=False, error=f"CLI exit {code}: {(out or {}).get('usage_error')}", exit=code, cli_raw=out)
        return dict(ok=entry["ok"], seq=entry.get("seq"), exit=code, cli_raw=out, tool=entry["tool"],
                    **({"result": entry["result"]} if entry["ok"] else {"error": entry["error"]}))

    def cli_step(self, argv):
        code, out, cmd = self.run(argv)
        o = dict(out or {})
        o["exit"] = code
        o["cli_raw"] = out
        o["argv"] = cmd[3:]
        return o

    def close(self):
        pass


# =================================================================================================================
# runner
# =================================================================================================================
def report_of(drv, o) -> dict | None:
    """report.json of an export output (path relative to the session root)."""
    try:
        res = o.get("result") or {}
        rel = res["files"]["report"]["path"]
        root = drv.root
        return json.loads((Path(root) / rel).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def run_scenario(scn: dict, iface: str, make_driver, log=print) -> dict:
    from matrix_spec import CLI_TOOLS
    sdir = SESS / iface / scn["id"]
    if iface != "gui" and sdir.exists() and any(sdir.iterdir()):
        raise RuntimeError(f"{sdir} exists: V2 sessions are never overwritten")
    if iface != "gui":
        sdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    drv = make_driver(sdir, scn["profile"])
    labels, rows, calls = {}, [], []
    try:
        for i, stp in enumerate(scn["steps"]):
            ifs = stp.get("ifaces") or scn["ifaces"]
            if iface not in ifs:
                continue
            if stp["tool"] == "__cli__":
                if iface != "cli":
                    continue
                t = time.time()
                o = drv.cli_step(stp["argv"])
            else:
                if iface == "cli" and stp["tool"] not in CLI_TOOLS:
                    continue
                args = resolve(stp["args"], labels)
                t = time.time()
                o = drv.call(stp["tool"], args)
            dt = round(time.time() - t, 2)
            if stp.get("label"):
                labels[stp["label"]] = o
            calls.append(dict(i=i, tool=stp["tool"], args=stp.get("args"), argv=stp.get("argv"), dt_s=dt,
                              ok=o.get("ok"), exit=o.get("exit"), seq=o.get("seq"),
                              error=o.get("error"), result=o.get("result"),
                              cli=(o.get("cli_raw") if iface == "cli" else None)))
            if stp.get("check"):
                rep = None
                if any(e[0] == "report" for e in stp["expect"]):
                    rep = report_of(drv, o)
                passed, fails = check(stp["expect"], o, labels, rep)
                if iface == "cli":
                    log_path = (drv.last_session or "") if o.get("exit") is not None else ""
                    session_ref = os.path.relpath(log_path, ROOT).replace("\\", "/") if log_path else ""
                else:
                    session_ref = os.path.relpath(drv.log, ROOT).replace("\\", "/")
                expected_refusal = any(e == ("ok", False) for e in stp["expect"]) or \
                    any(e[0] == "exit" and e[1] != 0 for e in stp["expect"])
                rows.append(dict(scenario=scn["id"], check=stp["check"], capability=stp["cap"], interface=iface,
                                 profile=scn["profile"], tool=stp["tool"] if stp["tool"] != "__cli__" else "amm " + stp["argv"][0],
                                 expected_refusal=expected_refusal, observed=observed_summary(o),
                                 passed=passed, failures=fails, seq=o.get("seq"), dt_s=dt, session=session_ref))
                log(f"  [{iface}] {scn['id']}/{stp['check']}: {'PASS' if passed else 'FAIL'} ({dt:.1f} s) "
                    f"{'; '.join(fails)[:300]}")
    finally:
        drv.close()
    extra = dict(cli_sessions=drv.sessions) if iface == "cli" else {}
    return dict(scenario=scn["id"], interface=iface, rows=rows, calls=calls, seconds=round(time.time() - t0, 1),
                root=os.path.relpath(drv.root, ROOT).replace("\\", "/") if drv.root else None, **extra)
