"""MCP server (stdio) for the tool contract. Any MCP client (Codex CLI, Claude Code) drives the same logged tools.

    python -B -m amm.mcp_server --session DIR --profile B|C [--brief BRIEF.json]

--brief: a benchmark brief; its `oracle` facts answer ask_clarification deterministically (amm.bench.Oracle).
Arguments reach Session.call unvalidated, so a malformed call is rejected and logged like any other failure.
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
import typing

INSTRUCTIONS = ("amm: tools to design periodic unit cells (TPMS, strut lattices, mass-in-frame resonators) for "
                "stiffness and elastic-wave band-gap targets. Set the spec (set_material, set_constraints, "
                "set_target), explore (list_families, evaluate, search) and finish with submit.")


MCP_MISSING = "the MCP server needs the MCP Python SDK: pip install amm[mcp]"


def _raw_args_model():
    from pydantic import ConfigDict
    try:
        from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase
    except ImportError as e:
        raise ImportError(MCP_MISSING) from e

    class RawArgs(ArgModelBase):
        model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

        def model_dump_one_level(self):
            return {"__raw__": dict(self.model_extra or {})}
    return RawArgs


def build_server(session):
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError as McpToolError
    except ImportError as e:
        raise ImportError(MCP_MISSING) from e
    from .tools import TOOLS
    srv = MCPServer("amm", instructions=INSTRUCTIONS)
    raw = _raw_args_model()
    for name in session.tools():
        t = TOOLS[name]
        hints = typing.get_type_hints(t["fn"], include_extras=True)
        params = [p.replace(annotation=hints.get(p.name, typing.Any)) for p in t["params_by"][session.schema]]

        def make(name=name, params=params):
            def fn(**kw):
                out = session.call(name, kw.get("__raw__", kw), actor="agent")
                if not out["ok"]:
                    raise McpToolError(out["error"])
                return json.dumps(out["result"], separators=(",", ":"), ensure_ascii=False)
            fn.__name__ = name
            fn.__signature__ = inspect.Signature(params)
            fn.__annotations__ = {p.name: p.annotation for p in params}
            return fn
        srv.add_tool(make(), name=name, description=t["doc"], structured_output=False)
        srv._tool_manager.get_tool(name).fn_metadata.arg_model = raw
    return srv


def main(argv=None):
    sys.dont_write_bytecode = True
    for st in (sys.stdin, sys.stdout):  # JSON-RPC is UTF-8; Windows consoles default to cp1252
        if hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--profile", default="C", choices=["B", "C"])
    ap.add_argument("--brief", help="benchmark brief JSON; its oracle answers ask_clarification")
    a = ap.parse_args(argv)
    from .tools import Session
    answerer = None
    if a.brief:
        from .bench import Oracle
        answerer = Oracle(json.loads(open(a.brief, encoding="utf-8").read()))
    s = Session(a.session, profile=a.profile, answerer=answerer)
    build_server(s).run("stdio")


if __name__ == "__main__":
    main()
