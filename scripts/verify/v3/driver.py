"""V3 runner: targets in processing order; per target one search process (all methods) then one certificate
process; one row per (target, method) in <out>/rows/ and runs.csv regenerated after each target. Resumable.
Compute cut rule of NOTES.md section 7 applied after each target. Run under scripts/ops/gpulock_run.py.

    driver.py [--out DIR] [--targets PATH] [--only ID,ID] [--cap-hours 15] [--spent-hours X]
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PY = sys.executable
PRIMARY_METHODS = ["M1", "M2", "M3", "M4", "M5", "M6"]
CALIB_METHODS = ["M4", "M6"]
CUTS = ["drop_calibration", "drop_M6", "primary_16"]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def env(threads):
    e = dict(os.environ)
    e.update(MKL_NUM_THREADS=str(threads), OMP_NUM_THREADS=str(threads), PYTHONUNBUFFERED="1")
    return e


def run(cmd, threads, log):
    t = time.perf_counter()
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n### {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(cmd)}\n")
        f.flush()
        rc = subprocess.call(cmd, stdout=f, stderr=subprocess.STDOUT, env=env(threads), cwd=str(ROOT))
    if rc != 0:
        raise SystemExit(f"child failed ({rc}): {' '.join(cmd)}; see {log}")
    return time.perf_counter() - t


def row_for(out, tgt, m):
    r = json.loads((out / "search" / f"{tgt['target_id']}_{m}.json").read_text(encoding="utf-8"))
    f = r["final"]
    row = dict(target_id=tgt["target_id"], set=tgt["set"], order=tgt["order"], material=tgt["material"],
               nu=tgt["nu"], target_type=tgt["target_type"], witness_family=tgt["witness_family"],
               difficulty=tgt["difficulty"], method=m, method_name=r["method_name"], objective=r["objective"],
               final_kind=f["spec"]["kind"], final_family=f["spec"]["family"],
               final_params=json.dumps(f["spec"]["params"], sort_keys=True), final_hash=f["hash"],
               from_atlas=r["from_atlas"], calibrated_domain=f["calibrated_domain"],
               slack_nominal=f["slack_nominal"], slack_expected=f["slack_expected"], slack_pess=f["slack_pess"],
               evals_spent=r["n_evaluations"], evals_to_final=r["evals_to_final"],
               search_seconds=r["search_seconds"], evaluator_seconds=r["evaluator_seconds"],
               throughput_evals_per_s=(r["n_evaluations"] / r["evaluator_seconds"]) if r["evaluator_seconds"] else None)
    certify = f["slack_nominal"] > 0
    row["certify_attempted"] = certify
    row["cert_calls"] = int(certify)
    if certify:
        s = json.loads((out / "certs" / f"{tgt['target_id']}_{f['hash']}.summary.json").read_text(encoding="utf-8"))
        row.update(cert_verdict=s["verdict"], certified=s["verdict"] == "certified", cert_seconds=s["seconds"],
                   certified_slack=s["certified_slack"], cert_shared_with=",".join(x for x in s["methods"] if x != m),
                   static_verdict=s["static_verdict"], gap_verdict=s.get("gap_verdict"))
    else:
        row.update(cert_verdict="not_certified_search_tier_miss", certified=False, cert_seconds=0.0,
                   certified_slack=None, cert_shared_with="", static_verdict=None, gap_verdict=None)
    row["workflow_seconds"] = row["search_seconds"] + row["cert_seconds"]
    return row


def write_csv(out):
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "rows").glob("*.json"))]
    rows.sort(key=lambda r: (r["order"], r["method"]))
    if not rows:
        return
    keys = list(rows[0])
    with open(out / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main():
    out = Path(arg("--out", str(ROOT / "results" / "verification" / "v3")))
    tpath = Path(arg("--targets", str(out / "targets.json")))
    cap = float(arg("--cap-hours", "15")) * 3600
    targets = json.loads(tpath.read_text(encoding="utf-8"))["targets"]
    only = arg("--only")
    if only:
        targets = [t for t in targets if t["target_id"] in only.split(",")]
    state_p = out / "state.json"
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else dict(
        spent_seconds=float(arg("--spent-hours", "0")) * 3600, per_target={}, cuts=[], log=[])
    log = out / "driver_children.log"
    (out / "rows").mkdir(parents=True, exist_ok=True)
    for tgt in sorted(targets, key=lambda t: t["order"]):
        tid = tgt["target_id"]
        if tgt["set"] == "calibration" and "drop_calibration" in state["cuts"]:
            continue
        if tgt["set"] == "primary" and "primary_16" in state["cuts"] and tgt["order"] >= 16:
            continue
        methods = PRIMARY_METHODS if tgt["set"] == "primary" else CALIB_METHODS
        if "drop_M6" in state["cuts"]:
            methods = [m for m in methods if m != "M6"]
        if all((out / "rows" / f"{tid}_{m}.json").exists() for m in methods):
            continue
        t0 = time.time()
        ts = run([PY, str(HERE / "search_child.py"), tid, ",".join(methods), str(out), "--targets", str(tpath)], 4, log)
        tc = run([PY, str(HERE / "cert_child.py"), tid, str(out), "--targets", str(tpath)], 16, log)
        for m in methods:
            (out / "rows" / f"{tid}_{m}.json").write_text(json.dumps(row_for(out, tgt, m)), encoding="utf-8")
        write_csv(out)
        dt = time.time() - t0
        state["spent_seconds"] += dt
        state["per_target"][tid] = dict(seconds=round(dt, 1), search=round(ts, 1), cert=round(tc, 1),
                                        set=tgt["set"], done=time.strftime("%Y-%m-%d %H:%M:%S"))
        # cut rule (NOTES.md section 7)
        done = [v["seconds"] for v in state["per_target"].values()]
        left = [t for t in targets if t["target_id"] not in state["per_target"]
                and not (t["set"] == "calibration" and "drop_calibration" in state["cuts"])
                and not (t["set"] == "primary" and "primary_16" in state["cuts"] and t["order"] >= 16)]
        proj = state["spent_seconds"] + (sum(done) / len(done)) * len(left)
        msg = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} {tid} done in {dt:.0f} s (search {ts:.0f}, cert {tc:.0f}); "
               f"spent {state['spent_seconds'] / 3600:.2f} h, projected {proj / 3600:.2f} h")
        if proj > cap:
            nxt = next((c for c in CUTS if c not in state["cuts"]), None)
            if nxt:
                state["cuts"].append(nxt)
                msg += f"; CUT applied: {nxt}"
        state["log"].append(msg)
        print(msg, flush=True)
        state_p.write_text(json.dumps(state, indent=1), encoding="utf-8")
    print("driver finished", flush=True)


if __name__ == "__main__":
    main()
