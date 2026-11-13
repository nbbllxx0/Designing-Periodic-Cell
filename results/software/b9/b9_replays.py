"""B9 check: replay the GUI live sessions and the tutorial sessions with the DEFAULT arguments (root=None)."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\AI\AgenticMetamaterials")
sys.path.insert(0, str(ROOT))
import amm  # noqa: E402,F401
from amm import certify, tools  # noqa: E402

logs = sorted((ROOT / "results" / "gui" / "sessions").glob("*/session.jsonl")) + [
    ROOT / "examples" / "outputs" / "02_session" / "session.jsonl",
    ROOT / "examples" / "outputs" / "03_session" / "session.jsonl"]
out = dict(code=tools.code_hash(), checker=certify.checker_hash(), replays={})
for p in logs:
    t0 = time.perf_counter()
    r = tools.replay(p)  # default arguments
    key = str(p.relative_to(ROOT)).replace("\\", "/")
    out["replays"][key] = dict(exact=r["exact"], n_calls=r["n_calls"], n_compared=r["n_compared"],
                               mismatches=r["mismatches"], root=r["root"], identity=r["identity"],
                               decision_changes=r["decision_changes"], seconds=round(time.perf_counter() - t0, 1))
    print(key, r["exact"], r["n_calls"], r["root"], r["identity"]["checker_log_source"], round(time.perf_counter() - t0, 1),
          r["mismatches"][:2], flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
print("exact:", sum(v["exact"] for v in out["replays"].values()), "of", len(out["replays"]))
