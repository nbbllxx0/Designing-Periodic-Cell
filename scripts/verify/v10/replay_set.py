"""V10: replay a list of session logs (amm.tools.replay, no LLM) and the tolerance comparison of v10lib.

    python scripts/ops/gpulock_run.py v10 -- python scripts/verify/v10/replay_set.py <set> <log> [<log> ...]
    python scripts/verify/v10/replay_set.py <set> --list <file with one log path per line>

One JSON per log in <OUT>/raw/<set>/<id>.json (id = path relative to ROOT, '/' -> '__'); an existing file is kept
(resume). The run is sequential, in one process.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v10lib as L  # noqa: E402


def rid(p: Path) -> str:
    try:
        rel = p.resolve().relative_to(L.ROOT.resolve())
    except ValueError:
        rel = Path(p.name)
    s = str(rel).replace("\\", "/")
    return s.replace("/session/session.jsonl", "").replace("/session.jsonl", "").replace("/", "__")


def main(argv):
    name = argv[0]
    logs = argv[1:]
    if logs and logs[0] == "--list":
        logs = [l.strip() for l in Path(logs[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    import amm  # noqa: F401  (environment defaults before torch)
    env = L.env_brief()
    print("env", json.dumps(env), flush=True)
    outdir = L.OUT / "raw" / name
    outdir.mkdir(parents=True, exist_ok=True)
    t_set = time.time()
    for lp in logs:
        p = Path(lp)
        if not p.is_absolute():
            p = L.ROOT / p
        out = outdir / f"{rid(p)}.json"
        if out.exists():
            print("skip (done)", out.name, flush=True)
            continue
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            recs, rep, rec, secs = L.replay_with_outputs(p)
            tol = L.tolerance_report(recs, rec)
            err = None
        except Exception as ex:  # noqa: BLE001
            try:
                from amm import tools
                recs = tools.read_log(p)
            except Exception:  # noqa: BLE001
                recs = []
            rep, tol, secs, err = None, None, None, f"{type(ex).__name__}: {ex}\n{traceback.format_exc()[-1500:]}"
        h = L.header(recs) if recs else {}
        calls = [r for r in recs if r.get("type") == "call"]
        res = dict(set=name, log=str(p.relative_to(L.ROOT) if p.is_relative_to(L.ROOT) else p).replace("\\", "/"),
                   log_sha256=L.file_sha(p), started=started, seconds=None if secs is None else round(secs, 1),
                   header=h, n_calls=len(calls), tools=sorted({c["tool"] for c in calls}),
                   n_certify=sum(1 for c in calls if c["tool"] == "certify"),
                   n_search=sum(1 for c in calls if c["tool"] == "search"),
                   n_export=sum(1 for c in calls if c["tool"] == "export"),
                   logged_tool_seconds=round(sum((c.get("dt_s") or 0) for c in calls), 1),
                   env=env, replay=rep, tolerance=tol, error=err)
        L.jdump(res, out)
        ex = rep["exact"] if rep else None
        print(f"{res['log']}: exact {ex} mism {len(rep['mismatches']) if rep else '-'} "
              f"tol {tol.get('within_tolerance') if tol else '-'} [{res['seconds']} s]", flush=True)
    print(f"set {name} done in {round(time.time() - t_set, 1)} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
