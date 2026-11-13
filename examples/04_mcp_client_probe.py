"""Connect to the amm MCP server the way an agent client does, without any LLM: spawn it over stdio, list its tools
and make three calls.

    python examples/04_mcp_client_probe.py [--profile C|B]

Needs the `mcp` extra (pip install "amm[mcp]"). The server writes its session log to a temporary directory,
printed at the end. Use this to check an installation before pointing Claude Code, Codex or another MCP client at
`python -m amm.mcp_server` (docs/mcp.md).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def probe(profile: str) -> int:
    sess = tempfile.mkdtemp(prefix="amm_mcp_")
    params = StdioServerParameters(command=sys.executable,
                                   args=["-B", "-m", "amm.mcp_server", "--session", sess, "--profile", profile])
    t0 = time.perf_counter()
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print(f"server {init.server_info.name!r} ready in {time.perf_counter() - t0:.1f} s")
            tools = (await s.list_tools()).tools
            print(f"{len(tools)} tools (profile {profile}): " + ", ".join(t.name for t in tools))
            out = await s.call_tool("set_material", {"name": "316L"})
            print("set_material ->", out.content[0].text)
            out = await s.call_tool("set_target", {"density_max": 0.16, "E100_min": {"value": 38.6, "unit": "GPa"}})
            print("set_target ->", json.loads(out.content[0].text)["normalized"])
            if profile == "C":
                out = await s.call_tool("check_bounds", {})
                res = json.loads(out.content[0].text)
                print("check_bounds -> verdict", res["verdict"], "| violated:",
                      [f"{v['bound']}: {v['statement']}" for v in res["violated"]])
            out = await s.call_tool("set_target", {"bogus": 1})
            print("invalid call -> is_error", out.is_error, "|", out.content[0].text[:120])
    with open(f"{sess}/session.jsonl", encoding="utf-8") as f:
        n = sum(1 for _ in f)
    print(f"session log: {sess}/session.jsonl ({n} records: header + one per call)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="C", choices=["B", "C"])
    return asyncio.run(probe(ap.parse_args().profile))


if __name__ == "__main__":
    sys.exit(main())
