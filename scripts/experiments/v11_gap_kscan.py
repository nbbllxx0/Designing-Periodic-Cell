"""V11 (audit round 1, 2026-11-08): dense irreducible-wedge control for complete-gap acceptance.

For every certified gap cell reported in the paper (the eight DOLFINx-comparison cells, the extra quadratic
finite-cell cell, and the three engineering designs), count Bloch eigenvalues below both claim endpoints at every
point of a regular grid on the irreducible wedge 0 <= kz <= ky <= kx <= pi (step pi/S, all faces and edges included,
so the M-R edge is covered), on the lowest counted certificate resolution (n = 20, grid phase 0).
A point fails if either count differs from the certificate's band index (the claim interval would then contain a mode
of the discrete model at that k). CPU only (PARDISO LDL^T), no LLM.

    python scripts/experiments/v11_gap_kscan.py [--steps 12] [--n 20] [--only CASE] [--time]
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
from amm import bloch
from amm.certify import _mesh

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v11"


def cases():
    out = []
    for f in sorted((ROOT / "results/verification/dolfinx").glob("*.json")):
        if f.name.startswith(("summary",)):
            continue
        d = json.loads(f.read_text())
        if "spec" in d and "claim" in d:
            out.append(dict(case=d["case"], src="V1c", spec=d["spec"], nu=d["nu"], below_band=d["below_band"],
                            claim=d["claim"]))
    out.append(dict(case="thin_sl_c0.357_w0.109_nu0.3", src="V1b",
                    spec=dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.357, w=0.109)), nu=0.3,
                    below_band=None, claim=None))  # claim filled from v1b/summary.json
    v1b = json.loads((ROOT / "results/verification/v1b/summary.json").read_text())
    g = v1b["thin_sl_c0.357_w0.109_nu0.3"]["gap"]
    out[-1]["claim"] = g["claim"]
    for name, cert, nu in (("mount_PA12", "v6/case1/session_design/certificates/7db650ec44d50a1d_08d26401ae0bf0dc.json", 0.39),
                           ("filter_PA12", "v6/case2/session_PA12/certificates/e5519f4fdbef64db_e212dc39bc22b626.json", 0.39),
                           ("filter_316L", "v6/case2/session_316L/certificates/f1d00ed043a926f1_0dc7c12bea6f73f4.json", 0.3)):
        d = json.loads((ROOT / "results/verification" / cert).read_text())
        c = d["blocks"]["bloch"]["claim"]
        out.append(dict(case=name, src="V6", spec=d["spec"], nu=nu, below_band=c["below_band"],
                        claim=[c["f_lo"], c["f_hi"]], cert=cert))
    return out


def wedge(S):
    pts = []
    for i in range(S + 1):
        for j in range(i + 1):
            for l in range(j + 1):
                pts.append((i, j, l))
    return np.pi * np.array(pts, float) / S


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--only", default=None)
    ap.add_argument("--time", action="store_true", help="time 3 k-points per case and exit")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ks = wedge(a.steps)
    rows = []
    for c in cases():
        if a.only and c["case"] != a.only:
            continue
        m, info = _mesh(c["spec"], a.n, c["nu"])
        ic = bloch.InertiaCounter(m)
        t0 = time.perf_counter()
        f_lo, f_hi = c["claim"]
        nb = c["below_band"]
        if nb is None:
            nb = ic.counts(np.zeros(3), [f_lo])[0]["below"]
        fails, odd = [], 0
        use = ks[:3] if a.time else ks
        for k in use:
            lo, hi = ic.counts(k, [f_lo, f_hi])
            odd += lo["odd"] + hi["odd"] + lo["perturbed"] + hi["perturbed"]
            if lo["below"] != nb or hi["below"] != nb:
                fails.append(dict(k_over_pi=np.round(k / np.pi, 4).tolist(), below_lo=lo["below"], below_hi=hi["below"]))
        ic.free()
        dt = time.perf_counter() - t0
        row = dict(case=c["case"], src=c["src"], spec=c["spec"], nu=c["nu"], n=a.n, ndof=m.ndof, below_band=nb,
                   claim=[f_lo, f_hi], steps=a.steps, n_k=len(use), n_fail=len(fails), fails=fails[:20],
                   numerical_flags=int(odd), seconds=round(dt, 1))
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("case", "n_k", "n_fail", "numerical_flags", "seconds")}), flush=True)
    if not a.time:
        tag = f"_{a.only}" if a.only else ""
        (OUT / f"kscan_n{a.n}_S{a.steps}{tag}.json").write_text(json.dumps(rows, indent=1))
