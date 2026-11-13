"""Audit F10 (2026-11-06): re-certify feasible witnesses whose full certificate record is missing from work/certs.

For every S/G/M brief: the witness spec and the stated request from bench/v1/work/<id>.json are certified again with
the current checker (build._certify: as-built off, intended material and cell size). The certificate is stored in
work/certs/<id>_<key>.json with its checker hash. Missing records only, unless --all.

    witness_recert.py [--all] [IDS...]   -> bench/v1/witness_recert.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
from amm import certify  # noqa: E402

OUT = build.OUT


def main(args):
    P = json.loads((OUT / "plan.json").read_text(encoding="utf-8"))
    ids = [a for a in args if not a.startswith("--")] or [i for i in sorted(P["briefs"]) if i[0] in "SGM"]
    res_f = OUT / "witness_recert.json"
    res = json.loads(res_f.read_text(encoding="utf-8")) if res_f.exists() else {}
    for bid in ids:
        w = json.loads((OUT / "work" / f"{bid}.json").read_text(encoding="utf-8"))
        f = w["final"]
        b = dict(P["briefs"][bid], id=bid, nu=build.MAT_NU[P["briefs"][bid]["material"]])
        have = list((OUT / "work" / "certs").glob(f"{bid}_*.json"))
        matching = [p for p in have if json.loads(p.read_text(encoding="utf-8")).get("spec") == f["spec"]
                    and json.loads(p.read_text(encoding="utf-8")).get("targets") == f["normalized"]]
        if matching and "--all" not in args:
            continue
        print(bid, "certifying", f["spec"], flush=True)
        if "--all" in args:  # forced: bypass build's unversioned cache, store under a checker-keyed name
            import hashlib
            import time
            t0 = time.perf_counter()
            c = certify.certify(f["spec"], f["normalized"], nu=b["nu"], as_built=False)
            key = hashlib.sha256(json.dumps(dict(spec=f["spec"], t=f["normalized"], nu=b["nu"], checker=c["checker"]),
                                            sort_keys=True).encode()).hexdigest()[:16]
            (OUT / "work" / "certs" / f"{bid}_{key}.json").write_text(json.dumps(c, default=float), encoding="utf-8")
            summ = dict(verdict=c["verdict"], seconds=round(time.perf_counter() - t0, 1), forced=True)
        else:
            c, summ = build._certify(b, f["spec"], f["request"])
        summ.update(checker=c.get("checker"), matches_work_verdict=c["verdict"] == f["verdict"])
        res[bid] = summ
        res_f.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
        print(bid, c["verdict"], summ["seconds"], "s", "checker", c.get("checker"), flush=True)
    print("checker", certify.checker_hash(), "records", len(res))


if __name__ == "__main__":
    from e4 import GpuLock  # the project's exclusive solver lock: never alongside E4 jobs
    with GpuLock(f"witness_recert {' '.join(sys.argv[1:])}"):
        main(sys.argv[1:])
