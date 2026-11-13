"""LLM access through subscription CLIs only (pattern from AgenticTO's agentto.llm.cli, re-implemented).

Policy: no pay-as-you-go API. Every LLM session runs through a CLI logged in with the author's subscription:
Codex CLI (ChatGPT login) first, Claude Code optional. `assert_subscription_only` runs before every session and
refuses if an API-key variable is set or the CLI is not on a subscription login.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

API_KEY_VARS = ("OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")
ENDPOINT_VARS = ("OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL")  # stripped: no redirect to an API endpoint
DEFAULT_CODEX_MODEL = "gpt-6.1-sol"
CODEX_FEATURES_OFF = ("shell_tool", "browser_use", "browser_use_external", "in_app_browser", "computer_use", "apps",
                      "image_generation", "multi_agent", "plugins", "memories", "hooks")
DEFAULT_CODEX_EFFORT = "high"
ROOT = Path(__file__).resolve().parents[1]


class PolicyError(RuntimeError):
    pass


def codex_bin() -> str:
    exe = os.environ.get("AMM_CODEX") or shutil.which("codex")
    if not exe:
        raise FileNotFoundError("codex CLI not found (set AMM_CODEX)")
    return exe


def claude_bin() -> str:
    exe = os.environ.get("AMM_CLAUDE") or shutil.which("claude")
    if not exe:
        raise FileNotFoundError("claude CLI not found (set AMM_CLAUDE)")
    return exe


def assert_subscription_only(provider: str = "codex"):
    present = [v for v in API_KEY_VARS if os.environ.get(v)]
    if present:
        raise PolicyError(f"API-key variables set ({present}); refusing: pay-as-you-go API use is prohibited")
    if provider == "codex":
        out = subprocess.run([codex_bin(), "login", "status"], capture_output=True, text=True, timeout=60)
        text = (out.stdout + out.stderr).strip()
        if "ChatGPT" not in text:
            raise PolicyError(f"codex is not logged in with a ChatGPT subscription: {text!r}")
        return text
    elif provider == "claude":
        out = subprocess.run([claude_bin(), "auth", "status"], capture_output=True, text=True, timeout=60)
        try:
            st = json.loads(out.stdout)
        except json.JSONDecodeError:
            st = {}
        if not st.get("loggedIn") or st.get("authMethod") != "claude.ai":
            raise PolicyError(f"claude is not logged in with a claude.ai subscription: {out.stdout.strip()[:200]!r}")


def _clean_env():
    env = dict(os.environ)
    for v in API_KEY_VARS + ENDPOINT_VARS:
        env.pop(v, None)
    env["PYTHONPATH"] = str(ROOT)
    env.setdefault("MKL_NUM_THREADS", "16")
    env.setdefault("MKL_CBWR", "AUTO,STRICT")  # bit-reproducible MKL for exact replay (amm/__init__.py)
    return env


def server_args(session_dir: Path, profile: str, brief: Path | None = None) -> list[str]:
    a = ["-B", "-W", "ignore", "-m", "amm.mcp_server", "--session", str(Path(session_dir).resolve()),
         "--profile", profile]
    if brief is not None:
        a += ["--brief", str(Path(brief).resolve())]
    return [x.replace("\\", "/") for x in a]


def codex_mcp_config(session_dir: Path, profile: str, brief: Path | None = None, python: str | None = None,
                     tool_timeout_s: int = 2400) -> list[str]:
    """`-c` overrides giving a Codex session exactly one MCP server, the amm tool contract (with
    --ignore-user-config no other server is loaded)."""
    py = (python or sys.executable).replace("\\", "/")
    env = {"PYTHONPATH": str(ROOT).replace("\\", "/"), "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS", "16"),
           "MKL_CBWR": "AUTO,STRICT", "PYTHONUTF8": "1"}   # UTF-8 stdio: Windows defaults to cp1252
    return [f'mcp_servers.amm.command="{py}"',
            "mcp_servers.amm.args=" + json.dumps(server_args(session_dir, profile, brief)),
            "mcp_servers.amm.env={" + ",".join(f'{k}="{v}"' for k, v in env.items()) + "}",
            "mcp_servers.amm.startup_timeout_sec=120",
            'mcp_servers.amm.default_tools_approval_mode="approve"',   # exec mode cannot prompt
            f"mcp_servers.amm.tool_timeout_sec={tool_timeout_s}"]


@dataclass
class CliResult:
    provider: str
    model: str
    effort: str
    cli_version: str
    final: str
    usage: dict
    events: list = field(default_factory=list)
    wall_s: float = 0.0
    returncode: int = 0
    stderr: str = ""
    timed_out: bool = False


def _kill_tree(pid: int):
    """Kill a CLI and its children (the MCP server holds the GPU); by PID only, never by process name."""
    if os.name == "nt":
        r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, text=True)
        if r.returncode not in (0, 128):  # 128: already gone
            print(f"[harness] taskkill /T /PID {pid} returned {r.returncode}: {r.stdout.strip()} {r.stderr.strip()}",
                  flush=True)
    else:
        try:
            os.killpg(pid, 9)
        except OSError:
            pass


def _run_cli(cmd: list[str], prompt: str | None, timeout: float, env: dict, cwd: str | None = None):
    """Run a CLI; on timeout kill its process tree and keep the partial output. Returns (rc, out, err, timed_out)."""
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", env=env, cwd=cwd, start_new_session=os.name != "nt")
    try:
        out, err = p.communicate(prompt, timeout=timeout)
        return p.returncode, out, err, False
    except subprocess.TimeoutExpired:
        _kill_tree(p.pid)
        try:
            out, err = p.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            p.kill()
            out, err = p.communicate(timeout=60)
        return -9, out or "", (err or "") + f"\n[harness] timeout after {timeout:.0f} s: process tree killed", True


def _events(text: str) -> list:
    ev = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                ev.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return ev


def run_codex(prompt: str, workdir: Path, model: str = DEFAULT_CODEX_MODEL, effort: str = DEFAULT_CODEX_EFFORT,
              extra_config: list[str] | None = None, timeout: float = 5400) -> CliResult:
    """One headless Codex session: user config ignored, read-only sandbox (shell commands are refused: without
    the user's Windows sandbox setting no command can run), nothing persisted; the only tools are the MCP servers
    passed in `extra_config`. Events are kept in workdir/events.jsonl, also after a timeout."""
    auth = assert_subscription_only("codex")
    exe = codex_bin()
    version = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    last = workdir / "last_message.txt"
    cmd = [exe, "exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
           "-s", "read-only", "-C", str(workdir), "-m", model, "-c", f'model_reasoning_effort="{effort}"',
           "-o", str(last), "-c", 'forced_login_method="chatgpt"']  # Codex itself refuses API-key auth
    for f in CODEX_FEATURES_OFF:  # explicit tool boundary: only the MCP servers in extra_config (audit re-check #11)
        cmd += ["-c", f"features.{f}=false"]
    cmd += ["-c", 'web_search="disabled"']
    for c in extra_config or []:
        cmd += ["-c", c]
    cmd.append("-")
    (workdir / "auth.txt").write_text(f"{auth}\nforced_login_method=chatgpt\n", encoding="utf-8")
    t = time.perf_counter()
    rc, out, err, timed_out = _run_cli(cmd, prompt, timeout, _clean_env())
    wall = time.perf_counter() - t
    (workdir / "events.jsonl").write_text(out, encoding="utf-8")
    (workdir / "stderr.txt").write_text(err, encoding="utf-8")
    events = _events(out)
    usage = {}
    for e in events:
        u = e.get("usage") if isinstance(e, dict) else None
        if isinstance(u, dict):
            for k, v in u.items():
                if isinstance(v, (int, float)):
                    usage[k] = usage.get(k, 0) + v
    final = last.read_text(encoding="utf-8") if last.exists() else ""
    r = CliResult("codex", model, effort, version, final, usage, events, wall, rc, err[-4000:])
    r.timed_out = timed_out
    return r


DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"


def claude_mcp_config(session_dir: Path, profile: str, brief: Path | None, path: Path, python: str | None = None) -> Path:
    py = (python or sys.executable).replace("\\", "/")
    env = {"PYTHONPATH": str(ROOT).replace("\\", "/"), "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS", "16"),
           "MKL_CBWR": "AUTO,STRICT", "PYTHONUTF8": "1"}
    cfg = {"mcpServers": {"amm": {"type": "stdio", "command": py, "args": server_args(session_dir, profile, brief),
                                  "env": env}}}
    path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return path


def run_claude(prompt: str, workdir: Path, mcp_config: Path | None = None, model: str = DEFAULT_CLAUDE_MODEL,
               timeout: float = 5400) -> CliResult:
    """One headless Claude Code session on the claude.ai subscription: no built-in tools (no shell, no file
    access), only the amm MCP server when given (--strict-mcp-config), no settings files, nothing persisted."""
    assert_subscription_only("claude")
    exe = claude_bin()
    version = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--model", model,
           "--tools", "", "--setting-sources", "", "--strict-mcp-config"]
    if mcp_config is not None:
        cmd += ["--mcp-config", str(mcp_config), "--allowedTools", "mcp__amm"]
    st = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=60).stdout
    (workdir / "auth.txt").write_text(st, encoding="utf-8")
    t = time.perf_counter()
    rc, out, err, timed_out = _run_cli(cmd, prompt, timeout, _clean_env(), cwd=str(workdir))
    wall = time.perf_counter() - t
    (workdir / "events.jsonl").write_text(out, encoding="utf-8")
    (workdir / "stderr.txt").write_text(err, encoding="utf-8")
    events = _events(out)
    res = next((e for e in reversed(events) if e.get("type") == "result"), {})
    u = res.get("usage") or {}
    usage = dict(input_tokens=u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                 + u.get("cache_creation_input_tokens", 0), cached_input_tokens=u.get("cache_read_input_tokens", 0),
                 output_tokens=u.get("output_tokens", 0))
    final = res.get("result") or ""
    (workdir / "last_message.txt").write_text(final, encoding="utf-8")
    r = CliResult("claude", model, "default", version, final, usage, events, wall, rc, err[-4000:])
    r.timed_out = timed_out
    return r
