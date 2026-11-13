"""V21 (2026-11-10): held-out test of the released gap guard on ten new cube-and-bar cells.

Protocol (frozen before any held-out number): results/verification/v21_heldout/PROTOCOL.md (SHA-256 in FROZEN.txt).
Cells and claims come from a seeded draw and the search-tier gap. amm runs the released checker (f99ce2b2f65d7630) at
its defaults. References use the unchanged DOLFINx exact-geometry pipeline (scripts/verify/dolfinx; V18 rule).
CPU (+ GPU for amm's k search); no LLM.

    python scripts/experiments/v21_heldout.py draw      # cells, search tier, claims -> cells.json
    python scripts/experiments/v21_heldout.py certify   # 2 certificates per cell -> certs/
    python scripts/experiments/v21_heldout.py export    # DOLFINx case files (claim-B certificate) -> dolfinx/inputs
    python scripts/experiments/v21_heldout.py run       # DOLFINx levels per case (run_case.py)
    python scripts/experiments/v21_heldout.py analyse   # grading -> results.json
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v21_heldout"
D = ROOT / "results/verification/dolfinx"
INP, RAW = D / "inputs", D / "raw"
HERE = ROOT / "scripts/verify/dolfinx"
CHECKER = "f99ce2b2f65d7630"
SEED = 20261110
NUS = (0.3, 0.342, 0.39)
STRATA = [("T", 3, (0.06, 0.10)), ("R", 7, (0.10, 0.25))]
C_RANGE = (0.40, 0.75)
MIN_REL = 0.10


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def dump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, default=float), encoding="utf-8")


def used_cells():
    """(c, w) of every cube-and-bar cell used earlier in the study (protocol rejection rule 2)."""
    out = set()

    def walk(x):
        if isinstance(x, dict):
            if x.get("kind") == "cube_bars" and isinstance(x.get("params"), dict) and "c" in x["params"]:
                out.add((float(x["params"]["c"]), float(x["params"]["w"])))
            g = x.get("geometry")
            if isinstance(g, dict) and g.get("kind") == "cube_bars":
                out.add((float(g["c"]), float(g["w"])))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(load(ROOT / "results/g2/classification_v3.json"))
    files = (glob.glob(str(ROOT / "results/g2/phase_ladder/*.json")) + glob.glob(str(INP / "*.json"))
             + glob.glob(str(ROOT / "results/verification/v3/certs/*.json")))
    for f in files:
        try:
            d = load(f)
        except Exception:
            continue
        walk(d.get("spec", d) if isinstance(d, dict) else d)
        if isinstance(d, dict) and "geometry" in d:
            walk({"geometry": d["geometry"]})
    for f in glob.glob(str(ROOT / "results/verification/indep/*.json")):
        m = re.search(r"cube_bars_c([0-9.]+)_w([0-9.]+)_", Path(f).name)
        if m:
            out.add((float(m.group(1)), float(m.group(2))))
    out |= {(0.592174, 0.151304), (0.786957, 0.06)}  # engineering cells
    return sorted(out)


def draw():
    from amm import evaluate
    rng = np.random.default_rng(SEED)
    used = used_cells()
    cells, log = [], []
    for stratum, k, (w0, w1) in STRATA:
        got = 0
        while got < k:
            c = round(float(rng.uniform(*C_RANGE)), 4)
            w = round(float(rng.uniform(w0, w1)), 4)
            nu = float(NUS[int(rng.integers(len(NUS)))])
            rec = dict(stratum=stratum, c=c, w=w, nu=nu)
            if w >= c:
                log.append(dict(rec, rejected="w >= c")); continue
            near = [u for u in used if abs(u[0] - c) < 0.02 and abs(u[1] - w) < 0.02]
            if near:
                log.append(dict(rec, rejected=f"near used cell {near[0]}")); continue
            spec = dict(family="resonator", kind="cube_bars", params=dict(c=c, w=w))
            ev = evaluate.evaluate(spec, nu=nu)
            if not ev.get("valid", True):
                log.append(dict(rec, rejected="invalid geometry")); continue
            gaps = ev.get("gaps") or []
            if not gaps or gaps[0]["rel"] < MIN_REL:
                log.append(dict(rec, rejected=f"search-tier widest gap rel {gaps[0]['rel'] if gaps else 0:.3f} < 0.10"))
                continue
            g = gaps[0]
            W = g["f_hi"] - g["f_lo"]
            rec.update(spec=spec, search_gap=g,
                       claims=dict(A=[g["f_lo"] + 0.25 * W, g["f_hi"] - 0.25 * W],
                                   B=[g["f_lo"] + 0.05 * W, g["f_hi"] - 0.05 * W]),
                       name=f"ho_cb_c{c}_w{w}_nu{nu}")
            cells.append(rec)
            log.append(dict(stratum=stratum, c=c, w=w, nu=nu, accepted=rec["name"]))
            got += 1
    dump(OUT / "cells.json", dict(seed=SEED, protocol_sha256=(OUT / "FROZEN.txt").read_text().split()[0],
                                  n_used_excluded=len(used), cells=cells, draws=log))
    print(json.dumps([(c["name"], c["search_gap"]["rel"]) for c in cells], indent=0))
    print(f"{len(log)} draws, {len(cells)} accepted")


def certify():
    from amm import certify as C
    assert C.checker_hash() == CHECKER, C.checker_hash()
    cells = load(OUT / "cells.json")["cells"]
    for cell in cells:
        for key in ("B", "A"):
            f = OUT / "certs" / f"{cell['name']}_{key}.json"
            if f.exists():
                continue
            lo, hi = cell["claims"][key]
            t0 = time.time()
            cert = C.certify(cell["spec"], {"gap": dict(f_lo=lo, f_hi=hi)}, nu=cell["nu"], as_built=False)
            assert cert["checker"] == CHECKER
            dump(f, cert)
            b = cert["blocks"].get("bloch", {})
            print(f"{cell['name']} {key}: {cert['verdict']} "
                  f"safe={b.get('convergence', {}).get('safe_interval')} ({time.time() - t0:.0f} s)", flush=True)


def export():
    from amm import bloch
    path, _ = bloch.kpath(4)
    interior = bloch.ibz_interior(10, 0)
    for cell in load(OUT / "cells.json")["cells"]:
        if (INP / f"{cell['name']}.json").exists() or not (OUT / "certs" / f"{cell['name']}_B.json").exists():
            continue
        cert = load(OUT / "certs" / f"{cell['name']}_B.json")
        b = cert["blocks"]["bloch"]
        conv = b.get("convergence") or {}  # absent when the counts failed: the reference needs only k and nb
        adv = (np.pi * np.asarray(b["adversarial"]["ks"], float).reshape(-1, 3)).tolist()
        assert len(path) + len(interior) + len(adv) == b["n_k"], (cell["name"], b["n_k"])
        case = dict(name=cell["name"], role="held-out (V21)", certificate=f"results/verification/v21_heldout/certs/{cell['name']}_B.json",
                    spec=cell["spec"], nu=cell["nu"], below_band=b["claim"]["below_band"],
                    claim=[b["claim"]["f_lo"], b["claim"]["f_hi"]],
                    amm=dict(edges=conv.get("edges"), phase_edges=conv.get("phase_edges"),
                             safe_interval=conv.get("safe_interval") or [None, None], mode=conv.get("mode")),
                    ks=dict(path=path.tolist(), interior=interior.tolist(), adversarial=adv),
                    geometry=dict(kind="cube_bars", c=cell["c"], w=cell["w"]), fcm={})
        dump(INP / f"{cell['name']}.json", case)
        print("wrote", INP / f"{cell['name']}.json")


def run(only=None):
    py = sys.executable
    for cell in load(OUT / "cells.json")["cells"]:
        if only and cell["name"] not in only:
            continue
        if not (INP / f"{cell['name']}.json").exists():
            continue
        r = subprocess.run([py, str(HERE / "run_case.py"), cell["name"], "--steps", "search,l1,l2,l3,l4"], cwd=ROOT)
        print(cell["name"], "exit", r.returncode, flush=True)


def analyse():
    sys.path.insert(0, str(HERE))
    import compare as cmp  # noqa: E402  (V1c rule functions, unchanged)
    res, summ = {}, dict(edges={}, claims={})
    for cell in load(OUT / "cells.json")["cells"]:
        name = cell["name"]
        c = load(INP / f"{name}.json")
        nb = c["below_band"]
        L = {n: cmp.load(RAW / name / f"q2_n{n}.json") for n in (10, 15, 20, 30)}
        used = [15, 20, 30] if L[30] else [10, 15, 20]
        if not all(L[n] for n in used):
            res[name] = dict(status="reference incomplete"); continue
        ks = [r["k"] for r in L[used[-1]]["records"]]
        E = {n: cmp.edges(L[n]["records"], nb, ks) for n in used}
        h = [1.0 / n for n in used]
        rlo = cmp.extrapolate(h, [E[n][0] for n in used])
        rhi = cmp.extrapolate(h, [E[n][1] for n in used])
        fin_lo, fin_hi = E[used[-1]][0], E[used[-1]][1]
        out = dict(stratum=cell["stratum"], spec=cell["spec"], nu=cell["nu"], below_band=nb, levels=used,
                   ref_lo=rlo, ref_hi=rhi, dolfinx_finest=[fin_lo, fin_hi], claims={})
        for key in ("A", "B"):
            cert = load(OUT / "certs" / f"{name}_{key}.json")
            b = cert["blocks"].get("bloch", {})
            conv = b.get("convergence") or {}
            s_lo, s_hi = (conv.get("safe_interval") or [None, None])
            f_lo, f_hi = cell["claims"][key]
            if f_lo >= rlo["ext"] + 2 * rlo["u"] and f_hi <= rhi["ext"] - 2 * rhi["u"]:
                truth = "true"
            elif f_lo < rlo["ext"] - 2 * rlo["u"] or f_hi > rhi["ext"] + 2 * rhi["u"]:
                truth = "false"
            else:
                truth = "indeterminate"
            v_lo = cmp.classify_lo(s_lo, rlo["ext"], rlo["u"]) if s_lo is not None else "no safe edge"
            v_hi = cmp.classify_hi(s_hi, rhi["ext"], rhi["u"]) if s_hi is not None else "no safe edge"
            certain = bool(s_hi is not None and s_hi > fin_hi)
            rec = dict(claim=[f_lo, f_hi], verdict=cert["verdict"], reason=b.get("verdict", {}).get("reason"),
                       truth=truth, safe=[s_lo, s_hi], edge_lo=v_lo, edge_hi=v_hi, unsound_for_certain=certain,
                       feature=b.get("feature"), seconds=cert.get("seconds"))
            if s_lo is not None and s_hi is not None:
                rec["gap_given_up"] = 1 - (s_hi - s_lo) / (rhi["ext"] - rlo["ext"])
                rec["margin_over_2u"] = dict(lo=(s_lo - rlo["ext"]) / (2 * rlo["u"]), hi=(rhi["ext"] - s_hi) / (2 * rhi["u"]))
            out["claims"][key] = rec
            for v in (v_lo, v_hi):
                summ["edges"][v] = summ["edges"].get(v, 0) + 1
            k = f"{truth}/{cert['verdict']}"
            summ["claims"][k] = summ["claims"].get(k, 0) + 1
        res[name] = out
    unsound = summ["edges"].get("unsound", 0)
    false_cert = summ["claims"].get("false/certified", 0)
    summ["primary"] = dict(unsound_safe_edges=unsound, certified_false_claims=false_cert,
                           passed=bool(unsound == 0 and false_cert == 0))
    dump(OUT / "results.json", dict(summary=summ, cells=res))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    step = sys.argv[1]
    {"draw": draw, "certify": certify, "export": export, "analyse": analyse,
     "run": lambda: run(sys.argv[2:] or None)}[step]()
