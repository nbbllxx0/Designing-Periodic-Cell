"""V1c host-side orchestrator: runs the DOLFINx levels of one case in the container, in the order of the protocol
(results/verification/dolfinx/NOTES.md), then the amm-side band evaluations at DOLFINx's own k (frozen code, lock).

    python scripts/verify/dolfinx/run_case.py <case> [--steps search,l1,l2,l3,id,amm]

Steps (each skipped when its output exists):
  search  DOLFINx search at the coarsest level (exact: Q2 n=10; fcm: Q2 n=10, 1 point per sub-cube), split ranks
  l1, l2  Q2 at the two coarser levels (exact: n = 10, 15; fcm: n = 16, 20) at S_amm + S_dfx (split ranks)
  l3      Q2 at the finest level (exact: n = 20; fcm: n = 30) at the subset: 2 extreme k per edge from l2 plus
          Gamma, X, M, R (all ranks on one k); the subset is already present at the coarser levels
  id      Q1 identity model n=20 at 6 k (Gamma, X, M, R, interior[0], adversarial[0])
  amm     amm identity model at the same 6 k; amm certificate model n=20 and 30 at S_dfx
Outputs: results/verification/dolfinx/raw/<case>/*.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
INP = ROOT / "results/verification/dolfinx/inputs"
RAW = ROOT / "results/verification/dolfinx/raw"
HERE = Path(__file__).resolve().parent
AMM_PY = "python"  # CUDA torch + pypardiso (E4 environment)
PI = np.pi
# Q2 levels (deviation 1 in NOTES.md: Q2 at n = 30 / 40 exceeded the 40 GB container memory on the dense cells)
LEVELS = {"exact": [10, 15, 20], "fcm": [16, 20, 30]}
L4 = {"exact": 30, "fcm": 40}  # extra finest level at the two edge k only
# deviation 8 (compute budget, decided after the strut search took 44 min, before its comparison): smaller search
# for the last case, and one k per edge (plus Gamma, X, M, R) at the finest fcm level
SEARCH_OPTS = {"thin_sl_c0.402_w0.061_nu0.3": "--n-random 40 --rounds 3 --top 2"}
SUBSET_PER_EDGE = {"exact": 2, "fcm": 1}
SYM = [[0, 0, 0], [PI, 0, 0], [PI, PI, 0], [PI, PI, PI]]


def container(name, cmd):
    t0 = time.time()
    full = ["C:/Program Files/Git/usr/bin/bash.exe", str(HERE / "run_container.sh"), name, cmd]  # Git Bash (not WSL bash)
    print(">>", cmd, flush=True)
    r = subprocess.run(full, cwd=ROOT)
    dt = time.time() - t0
    print(f"<< {r.returncode} in {dt:.0f} s", flush=True)
    if r.returncode:
        raise SystemExit(f"container step failed: {cmd}")
    return dt


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def subset(res_file, nb, per_edge=2):
    """k of the per_edge most extreme values of band nb (max) and nb+1 (min), plus Gamma, X, M, R."""
    d = json.load(open(res_file))
    F = np.array([r["f"] for r in d["records"]])
    K = np.array([r["k"] for r in d["records"]])
    lo = np.argsort(-F[:, nb - 1])
    hi = np.argsort(F[:, nb])
    pick = []
    for order in (lo, hi):
        got = 0
        for i in order:
            if not any(np.allclose(K[i], K[j]) for j in pick):
                pick.append(int(i))
                got += 1
            if got == per_edge:
                break
    ks = [K[i].tolist() for i in pick]
    for s in SYM:
        if not any(np.allclose(s, k) for k in ks):
            ks.append(list(map(float, s)))
    return ks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--steps", default="search,l1,l2,l3,id,amm")
    a = ap.parse_args()
    case_f = INP / f"{a.case}.json"
    case = json.load(open(case_f))
    nb = case["below_band"]
    exact = case["geometry"] is not None and case["geometry"]["kind"] == "cube_bars"
    model = "exact" if exact else "fcm"
    out = RAW / a.case
    out.mkdir(parents=True, exist_ok=True)
    timing_f = out / "timing.json"
    timing = json.load(open(timing_f)) if timing_f.exists() else {}
    steps = a.steps.split(",")
    py = "python3 scripts/verify/dolfinx/bloch_dolfinx.py"
    cs = f"--case {rel(case_f)} --deg 2 --nev {nb + 4}"
    mpi = "mpirun -n 8 "
    S_amm = case["ks"]["path"] + case["ks"]["interior"] + case["ks"]["adversarial"]

    def run(tag, cmd):
        if (out / f"{tag}.json").exists():
            return
        timing[tag] = round(container(f"{a.case[:20]}_{tag}", cmd), 1)
        json.dump(timing, open(timing_f, "w"), indent=1)

    def per_k(tag, n, ks_file):
        """Joint-rank runs leak memory over successive k (a run of 8 k was killed at 40 GB): a fresh container per k,
        then the records are merged into <tag>.json."""
        if (out / f"{tag}.json").exists():
            return
        ks = json.load(open(ks_file))
        parts = []
        for i, k in enumerate(ks):
            pf = out / f"{tag}_k{i}.json"
            run(f"{tag}_k{i}", f"{mpi}{py} {cs} --model {model} --n {n} --ks '{json.dumps(k)}' --out {rel(pf)}")
            parts.append(json.load(open(pf)))
        merged = dict(parts[0], records=[r for p in parts for r in p["records"]],
                      seconds=sum(p["seconds"] for p in parts), parts=[f"{tag}_k{i}.json" for i in range(len(ks))])
        json.dump(merged, open(out / f"{tag}.json", "w"), indent=1)

    # search
    f_search = out / "search.json"
    if "search" in steps:
        q = "" if exact else "--qsub 1"
        run("search", f"{mpi}{py} {cs} --model {model} --n 10 {q} --mode search {SEARCH_OPTS.get(a.case, '')} "
                      f"--out {rel(f_search)}")
    S_dfx = []
    if f_search.exists():
        s = json.load(open(f_search))["search"]
        S_dfx = s["lo"]["ks"] + s["hi"]["ks"]
    ks_all = out / "ks_all.json"
    if S_dfx and not ks_all.exists():
        json.dump(S_amm + S_dfx, open(ks_all, "w"))
    json.dump(S_dfx, open(out / "ks_dfx.json", "w"))
    lv = LEVELS["exact" if exact else "fcm"]
    for step, n in (("l1", lv[0]), ("l2", lv[1])):  # full k set, every rank its own k
        if step in steps:
            run(f"q2_n{n}", f"{mpi}{py} {cs} --model {model} --n {n} --split --ks {rel(ks_all)} "
                            f"--out {rel(out / f'q2_n{n}.json')}")
    ks_sub = out / "ks_sub.json"  # finest-level subset from the second level
    if (out / f"q2_n{lv[1]}.json").exists() and not ks_sub.exists():
        json.dump(subset(out / f"q2_n{lv[1]}.json", nb, SUBSET_PER_EDGE[model if exact else "fcm"]),
                  open(ks_sub, "w"))
    if "l3" in steps and ks_sub.exists():  # all ranks on one k (MUMPS in parallel), one container per k
        per_k(f"q2_n{lv[2]}", lv[2], ks_sub)
    # l4 (deviation 5 in NOTES.md, added after the first case): one finer level at the two edge k of l3
    f3 = out / f"q2_n{lv[2]}.json"
    ks_edge = out / "ks_edge.json"
    if f3.exists() and not ks_edge.exists():
        d3 = json.load(open(f3))["records"]
        klo = max(d3, key=lambda r: r["f"][nb - 1])["k"]
        khi = min(d3, key=lambda r: r["f"][nb])["k"]
        json.dump([klo] + ([khi] if not np.allclose(klo, khi) else []), open(ks_edge, "w"))
    if "l4" in steps and ks_edge.exists():
        n4 = L4["exact" if exact else "fcm"]
        per_k(f"q2_n{n4}", n4, ks_edge)
    # cross-check of the eigen solver and the serial fast path: SLEPc subspace iteration (shift-invert, MUMPS) on
    # matrices from dolfinx_mpc.assemble_matrix, second level, the two edge k
    if "slepc" in steps and ks_edge.exists():
        run(f"q2_n{lv[1]}_slepc", f"{mpi}{py} {cs} --model {model} --n {lv[1]} --split --no-fast --eps-type subspace "
                                  f"--ks {rel(ks_edge)} --out {rel(out / f'q2_n{lv[1]}_slepc.json')}")
    # identity
    ks_id = out / "ks_id.json"
    if not ks_id.exists():
        json.dump(SYM + [case["ks"]["interior"][0], case["ks"]["adversarial"][0]], open(ks_id, "w"))
    if "id" in steps:
        run("q1id_n20", f"{mpi}{py} --case {rel(case_f)} --deg 1 --nev {nb + 4} --model fcm_id --n 20 --split "
                        f"--ks {rel(ks_id)} --out {rel(out / 'q1id_n20.json')}")
    if "amm" in steps:
        amm = ROOT / "results/verification/dolfinx/amm"
        jobs = [("id", 20, ks_id)]
        if S_dfx:
            jobs += [("cert", 20, out / "ks_dfx.json"), ("cert", 30, out / "ks_dfx.json")]
        for m, n, kf in jobs:
            target = amm / f"{a.case}_{m}_n{n}_{kf.stem}.json"
            if target.exists():
                continue
            t0 = time.time()
            r = subprocess.run([AMM_PY, str(HERE / "amm_bands.py"), a.case, m, str(n), str(kf)], cwd=ROOT)
            if r.returncode:
                raise SystemExit("amm_bands failed")
            timing[f"amm_{m}_n{n}"] = round(time.time() - t0, 1)
            json.dump(timing, open(timing_f, "w"), indent=1)
    print("done", a.case, timing)


if __name__ == "__main__":
    main()
