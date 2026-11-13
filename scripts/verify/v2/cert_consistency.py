"""V2: the same spec and design through several interfaces give the same certificate key and the same certificate
(timing removed). Compares the PA12 static certificate of MCP S11, GUI S11 and CLI S12 (and tutorial 02's recorded
one), and writes results/verification/v2/cert_consistency.json.

    python scripts/verify/v2/cert_consistency.py
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2lib  # noqa: E402
from amm import tools  # noqa: E402

def cert_of(log):
    recs = tools.read_log(log)
    c = [r for r in recs if r.get("type") == "call" and r["tool"] == "certify" and r["ok"]]
    gs = [r for r in recs if r.get("type") == "call" and r["tool"] == "get_session" and r["ok"] and r["result"]["certificates"]]
    keys = sorted(gs[0]["result"]["certificates"]) if gs else None
    files = sorted(p.name for p in (Path(log).parent / "certificates").glob("*.json"))
    return c[0]["result"] if c else None, keys, files

out = {}
srcs = dict(mcp=v2lib.SESS / "mcp/S11_certified_static/session.jsonl",
            cli=next(iter(sorted((v2lib.SESS / "cli/S12_cli").glob("*-certify/session.jsonl"))), None),
            tutorial02=v2lib.ROOT / "examples/outputs/02_session/session.jsonl")
for g in sorted((v2lib.SESS / "gui").glob("live-*/session.jsonl")):
    r = [x for x in tools.read_log(g) if x.get("type") == "call" and x["tool"] == "certify" and x["ok"]
         and x["result"]["design"]["kind"] == "sphere_ligaments" and x["result"]["design"]["params"].get("c") == 0.12]
    if r:
        srcs["gui"] = g
for k, p in srcs.items():
    if p is None or not Path(p).exists():
        continue
    res, keys, files = cert_of(p)
    out[k] = dict(log=str(Path(p).relative_to(v2lib.ROOT)).replace("\\", "/"), result_hash=tools.result_hash(res),
                  verdict=res["verdict"], spec_hash=res["spec_hash"], E100_lower=res["static"]["bounds"]["E100"]["lower"],
                  cert_files=files, cert_keys=keys)
hashes = {k: v["result_hash"] for k, v in out.items()}
v2 = {k: v for k, v in hashes.items() if k != "tutorial02"}
summary = dict(certificates=out, identical_results_v2=len(set(v2.values())) == 1,
               identical_with_tutorial02=len(set(hashes.values())) == 1,
               cert_file_names_v2=sorted({f for k, v in out.items() if k != "tutorial02" for f in v["cert_files"]}))
(v2lib.OUT / "cert_consistency.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print(json.dumps(summary, indent=1))
