"""Certify the final designs of one target that pass the certify rule (nominal search-tier slack > 0).

    cert_child.py <target_id> <out_dir> [--targets path]
Identical designs share one certificate: <out_dir>/certs/<target_id>_<spec_hash>.json (full certificate) and
<out_dir>/certs/<target_id>_<spec_hash>.summary.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from amm import certify  # noqa: E402


def main(argv):
    tid, out = argv[0], Path(argv[1])
    tpath = argv[argv.index("--targets") + 1] if "--targets" in argv else common.OUT / "targets.json"
    tgt = next(t for t in common.load_targets(tpath) if t["target_id"] == tid)
    finals = {}
    for p in sorted((out / "search").glob(f"{tid}_M*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        if r["final"]["slack_nominal"] > 0:
            finals.setdefault(r["final"]["hash"], (r["final"]["spec"], []))[1].append(r["method"])
    for h, (spec, ms) in finals.items():
        path = out / "certs" / f"{tid}_{h}.json"
        if path.exists():
            continue
        t = time.perf_counter()
        c = certify.certify(spec, tgt["targets"], nu=tgt["nu"], as_built=False)
        c["wall_seconds_v3"] = round(time.perf_counter() - t, 1)
        s = common.cert_summary(c, tgt["targets"])
        s.update(target_id=tid, spec=spec, methods=ms, wall_seconds_v3=c["wall_seconds_v3"],
                 finished=time.strftime("%Y-%m-%d %H:%M:%S"))
        common.dump(path, c)
        common.dump(out / "certs" / f"{tid}_{h}.summary.json", s)
        print(f"[{tid}] cert {spec['kind']} {spec['params']} for {ms}: {c['verdict']} in {c['seconds']:.0f} s "
              f"(certified slack {s['certified_slack']})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
