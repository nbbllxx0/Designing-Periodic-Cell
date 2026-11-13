"""Run the search methods for one target (one process; resumable per method).

    search_child.py <target_id> <M1,M2,...> <out_dir> [--targets path]
Writes <out_dir>/search/<target_id>_<M>.json.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402  (imports amm before torch)


def main(argv):
    tid, methods, out = argv[0], argv[1].split(","), Path(argv[2])
    tpath = argv[argv.index("--targets") + 1] if "--targets" in argv else common.OUT / "targets.json"
    tgt = next(t for t in common.load_targets(tpath) if t["target_id"] == tid)
    todo = [m for m in methods if not (out / "search" / f"{tid}_{m}.json").exists()]
    if not todo:
        return 0
    if any(m != "M1" for m in todo):  # warm-up (CUDA context, kernels, MKL), not timed, not counted
        t = time.perf_counter()
        from amm import evaluate, atlas
        warm = atlas.make_spec("gyroid", dict(density=0.3), "sheet")  # fixed, target-independent; result discarded
        evaluate.evaluate_batch([warm], nu=tgt["nu"], keep_bands=True, **atlas.SEARCH_TIER)
        print(f"[{tid}] warm-up {time.perf_counter() - t:.1f} s", flush=True)
    for m in todo:
        r = common.run_method(m, tgt)
        common.dump(out / "search" / f"{tid}_{m}.json", r)
        f = r["final"]
        print(f"[{tid}] {m} {r['method_name']}: {r['n_evaluations']} evals, {r['search_seconds']:.1f} s, final "
              f"{f['spec']['kind']} nominal {f['slack_nominal']:+.4f} expected {f['slack_expected']:+.4f} "
              f"(eval {r['evals_to_final']}, atlas {r['from_atlas']})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
