# V10 diagnostic (deviation D3): replay examples/outputs/03_session into a kept root, then compare report.json
import json, sys, difflib
from pathlib import Path
import amm  # noqa
from amm import tools
root = Path("/out/diag03"); root.mkdir(parents=True, exist_ok=True)
r = tools.replay(tools.read_log("/in/repo/examples/outputs/03_session/session.jsonl"), root=str(root))
print("exact", r["exact"], [(m["seq"], m["tool"], m["field"]) for m in r["mismatches"]])
new = sorted(root.rglob("report.json"))
print("reports", new)
old = Path("/in/repo/examples/outputs/03_session/exports/bcc_268f8017_bf53ba/report.json").read_text()
for p in new:
    t = p.read_text()
    print(p, len(t.encode()), "vs", len(old.encode()))
    for l in difflib.unified_diff(old.splitlines(), t.splitlines(), "windows_log", "linux_replay", n=0, lineterm=""):
        print(l)
