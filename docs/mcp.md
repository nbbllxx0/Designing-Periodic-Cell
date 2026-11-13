# MCP server: connecting an agent

`amm.mcp_server` exposes the tool contract ([tool_contract.md](tool_contract.md)) over the Model Context Protocol
(stdio transport). An MCP client, such as Claude Code, Codex CLI or your own, drives the same logged
`amm.tools.Session` that scripts and the GUI use. The server starts no LLM and calls none.

Install: `pip install "amm[mcp]"` (MCP Python SDK >= 2.3). Without the SDK, `build_server` raises
`ImportError: the MCP server needs the MCP Python SDK: pip install amm[mcp]`.

## Start the server

```
python -B -m amm.mcp_server --session SESSION_DIR [--profile C|B] [--brief BRIEF.json]
```

| Option | Meaning |
|---|---|
| `--session` | directory for `session.jsonl`, `certificates/` and `exports/` (created if needed). Use a new directory for each design session. |
| `--profile` | `C` (default) is the full system. `B` is the benchmark ablation arm, with no `check_bounds`, `certify` or `as_built`. |
| `--brief` | a benchmark brief (`bench/v1/briefs/*.json`). Its oracle answers `ask_clarification` deterministically. Without it, `ask_clarification` returns the error "no user is available to answer in this session". |

The server speaks JSON-RPC on stdin and stdout, which it reconfigures to UTF-8, so it is meant to be launched by
a client and not run by hand. Tool arguments go to `Session.call` without changes, so a malformed call is
rejected and logged like any other failure. The client sees `is_error: true` with the validation message. Tool
calls run one at a time. `certify` takes 20 s to 20 min and `search` takes 1-15 min, so set the client's tool
timeout to at least 40 min (amm's own runner uses 2400 s).

## Check an installation without an LLM

```
python examples/04_mcp_client_probe.py
```

This spawns the server with the MCP Python client, lists its tools and makes three calls. The recorded output is
in `examples/outputs/04_mcp_client_probe.log`: 17 tools in profile C, a `check_bounds` call that names the
violated Voigt bound V1, and an invalid call rejected with "Extra inputs are not permitted".

## Claude Code

A JSON MCP configuration in the form `amm.llm.claude_mcp_config` writes (the form the benchmark runs used). The
paths are examples, so adjust them to your environment:

```json
{"mcpServers": {"amm": {
  "type": "stdio",
  "command": "C:/path/to/python.exe",
  "args": ["-B", "-W", "ignore", "-m", "amm.mcp_server", "--session", "C:/work/amm_sessions/s01", "--profile", "C"],
  "env": {"MKL_NUM_THREADS": "16", "MKL_CBWR": "AUTO,STRICT", "PYTHONUTF8": "1"}}}}
```

Pass it with `claude --mcp-config amm_mcp.json`. Add `--strict-mcp-config` to load only this server. The amm
tools then appear as `mcp__amm__<tool>`.

## Codex CLI

The `-c` overrides that `amm.llm.codex_mcp_config` builds:

```
codex exec -c 'mcp_servers.amm.command="C:/path/to/python.exe"' \
  -c 'mcp_servers.amm.args=["-B","-W","ignore","-m","amm.mcp_server","--session","C:/work/amm_sessions/s01","--profile","C"]' \
  -c 'mcp_servers.amm.env={MKL_NUM_THREADS="16",MKL_CBWR="AUTO,STRICT",PYTHONUTF8="1"}' \
  -c 'mcp_servers.amm.startup_timeout_sec=120' -c 'mcp_servers.amm.tool_timeout_sec=2400' "<your request>"
```

The same keys can go into `~/.codex/config.toml` under `[mcp_servers.amm]`.

These two client configurations are the forms the benchmark harness generated and used (`amm/llm.py`,
`results/bench/`). They were not re-run for this page, because that would mean LLM calls. The server side was
checked with the probe above.

## Environment

- With `pip install amm` (the wheel), nothing else is needed. In a source checkout without installation, set
  `PYTHONPATH` to the checkout, as `amm.llm` does.
- `MKL_CBWR=AUTO,STRICT` makes the session replay bit-exactly (`amm.tools.replay`). `import amm` sets it if it is
  unset.
- `PYTHONUTF8=1` avoids cp1252 stdio on Windows consoles.

## After the session

`SESSION_DIR/session.jsonl` holds every call. `amm.tools.replay("SESSION_DIR/session.jsonl")` re-runs it without
an LLM and reports whether every result and state hash matches. The answer the agent submitted, with its outcome
card and cited evidence, is the last `submit` record.
