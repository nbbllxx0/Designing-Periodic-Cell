"""Replay a V6 session log without any LLM (amm.tools.replay: bit-exact comparison of ok, state hash and every
result) and, on the same re-executed calls, a tolerance comparison: per call the largest relative difference of any
number, and every non-numeric difference (verdicts, outcomes, designs, strings). File hashes and byte counts follow
from the numbers written into the files, so they are listed separately.
    python scripts/verify/v6/replay_session.py <session_dir> <out_json>"""
import json, sys, time
from pathlib import Path
import amm  # noqa: F401
from amm import tools

FLOOR = 1e-9  # absolute floor (normalized or MPa values), so round-off zeros (e.g. off-diagonal C) do not count
DERIVED = ("sha256", "bytes", "result_hash", "state_hash", "spec_hash")
rec = []
_orig = tools.Session.call


def _call(self, name, args=None, actor="script", progress=None, cancel=None):
    out = _orig(self, name, args, actor, progress, cancel)
    rec.append(dict(tool=name, out=out))
    return out


tools.Session.call = _call


def walk(a, b, path, acc):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k in tools.VOLATILE:
                continue
            if k not in a or k not in b:
                acc["other"].append(dict(path=f"{path}.{k}", log=a.get(k), replay=b.get(k)))
            else:
                walk(a[k], b[k], f"{path}.{k}", acc)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", acc)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if a != b:
            key = path.rsplit(".", 1)[-1].split("[")[0]
            if key in DERIVED:
                acc["derived"].append(path)
            else:
                r = abs(a - b) / max(abs(a), abs(b), FLOOR)  # entries that are zero up to round-off: absolute floor
                if r > acc["max_rel"]:
                    acc["max_rel"], acc["max_rel_path"] = r, path
    elif a != b:
        key = path.rsplit(".", 1)[-1].split("[")[0]
        (acc["derived"] if key in DERIVED else acc["other"]).append(
            path if key in DERIVED else dict(path=path, log=str(a)[:80], replay=str(b)[:80]))


t = time.perf_counter()
log = tools.read_log(Path(sys.argv[1]) / "session.jsonl")
r = tools.replay(log)
calls = [e for e in log if e.get("type") == "call"]
per = []
for e, o in zip(calls, rec):
    acc = dict(max_rel=0.0, max_rel_path=None, other=[], derived=[])
    if e["ok"] and o["out"]["ok"]:
        walk(tools.strip_volatile(e["result"]), tools.strip_volatile(o["out"]["result"]), "", acc)
    elif e["ok"] != o["out"]["ok"]:
        acc["other"].append(dict(path="ok", log=e["ok"], replay=o["out"]["ok"]))
    per.append(dict(seq=e["seq"], tool=e["tool"], **acc))
r["tolerance"] = dict(
    max_rel_numeric=max(p["max_rel"] for p in per),
    non_numeric_differences=sum(len(p["other"]) for p in per),
    calls_with_numeric_differences=[(p["seq"], p["tool"], p["max_rel"], p["max_rel_path"]) for p in per if p["max_rel"] > 0],
    derived_differences=[(p["seq"], p["tool"], p["derived"][:6]) for p in per if p["derived"]],
    other=[(p["seq"], p["tool"], p["other"][:6]) for p in per if p["other"]])
r["seconds"] = round(time.perf_counter() - t, 1)
Path(sys.argv[2]).write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: r[k] for k in ("exact", "n_calls", "n_compared", "same_code", "schema", "seconds")}),
      json.dumps(r["tolerance"], default=str)[:1500])
