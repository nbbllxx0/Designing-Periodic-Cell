"""V18 (2026-11-10): exact-geometry (body-fitted) references for the two cube-and-bar engineering cells, answering the
audit items that the engineering cells have no reference independent of amm's voxel geometry.

Cells: the certified mount (PA12, cube_bars c 0.592174 w 0.151304, nu 0.39; certificate 7db650ec44d50a1d) and the 316L
filter (cube_bars c 0.786957 w 0.06, nu 0.3; finer gap check results/verification/v15/filters.json, undetermined).
The PA12 sphere-and-ligament filter is curved and is not covered by the exact model.

Solver: the V1c DOLFINx comparison pipeline unchanged (scripts/verify/dolfinx: DOLFINx 0.11.0 + dolfinx_mpc 0.11.0,
complex PETSc, container amm/dolfinx-mpc:0.11.0-complex, 8 cores, 40 GB), exact union of boxes on breakpoint-aligned
tensor grids, Q2 elements (Rayleigh-Ritz: each band is an upper bound of the continuum band at that k).
  gap:    run_case.py steps search, l1, l2, l3, l4 (Q2 at n = 10, 15, 20 on the certificate's 37 k plus DOLFINx's own
          search k; n = 30 at the two edge k), judged with compare.extrapolate / classify_* (V1c protocol).
  static: the mount's cubic moduli from long-wavelength acoustic speeds (no static code): k along [100] and [110] at
          |k| = 0.05 pi and 0.1 pi, Q2 at n = 10, 15, 20; C = phi rho_s v^2 with phi the exact solid fraction,
          v(k) = v0 + a k^2 extrapolated to k -> 0, then the mesh sequence extrapolated by the V1c rule;
          E100 = (C11 - C12)(C11 + 2 C12)/(C11 + C12), G = C44, K = (C11 + 2 C12)/3, compared with the certificate's
          guarded static interval.
CPU only (container); no GPU, no LLM. Approved by the author 2026-11-10 ("3 major experiments ... if so we run"; the
body-fitted reference for these two cells was the recommended part).

    python scripts/experiments/v18_dolfinx_engineering.py export
    python scripts/experiments/v18_dolfinx_engineering.py run
    python scripts/experiments/v18_dolfinx_engineering.py analyse
Outputs: results/verification/dolfinx/inputs/eng_*.json, raw/eng_*/..., results/verification/v18/references.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "results/verification/dolfinx"
INP, RAW = D / "inputs", D / "raw"
OUT = ROOT / "results/verification/v18"
HERE = ROOT / "scripts/verify/dolfinx"
MOUNT_CERT = "results/verification/v6/case1/session_design/certificates/7db650ec44d50a1d_08d26401ae0bf0dc.json"
V15 = "results/verification/v15/filters.json"
CASES = {"eng_mount_cb_c0.592_w0.151": "mount", "eng_316L_cb_c0.787_w0.06": "316L"}
K1 = 0.05 * np.pi
STATIC_LV = (10, 15, 20, 30)  # n = 30 added after the first analysis: order clipped at 0.5 on 10/15/20


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def static_ks():
    s = 1 / np.sqrt(2)
    return [[K1, 0, 0], [2 * K1, 0, 0], [K1 * s, K1 * s, 0], [2 * K1 * s, 2 * K1 * s, 0]]


def export():
    from amm import bloch  # live amm: kpath / ibz_interior are the certificate's k sets
    INP.mkdir(parents=True, exist_ok=True)
    path, _ = bloch.kpath(4)
    interior = bloch.ibz_interior(10, 0)
    mc = load(ROOT / MOUNT_CERT)
    v15 = load(ROOT / V15)["cells"]["316L"]
    srcs = {
        "mount": dict(certificate=MOUNT_CERT, spec=mc["spec"], nu=mc["solver"]["nu"], b=mc["blocks"]["bloch"],
                      role="engineering mount (certified)"),
        "316L": dict(certificate=V15 + "#cells.316L", spec=v15["spec"], nu=v15["nu"], b=v15["bloch"],
                     role="engineering filter (undetermined, finer gap check)"),
    }
    for name, key in CASES.items():
        s = srcs[key]
        b, conv = s["b"], s["b"]["convergence"]
        adv = (np.pi * np.asarray(b["adversarial"]["ks"], float).reshape(-1, 3)).tolist()
        assert len(path) + len(interior) + len(adv) == b["n_k"], (name, b["n_k"])
        p = s["spec"]["params"]
        case = dict(name=name, role=s["role"], certificate=s["certificate"], spec=s["spec"], nu=s["nu"],
                    below_band=b["claim"]["below_band"], claim=[b["claim"]["f_lo"], b["claim"]["f_hi"]],
                    amm=dict(edges=conv["edges"], phase_edges=conv.get("phase_edges"),
                             safe_interval=conv["safe_interval"], mode=conv.get("mode")),
                    ks=dict(path=path.tolist(), interior=interior.tolist(), adversarial=adv),
                    geometry=dict(kind="cube_bars", c=p["c"], w=p["w"]), fcm={})
        (INP / f"{name}.json").write_text(json.dumps(case, indent=1), encoding="utf-8")
        print("wrote", INP / f"{name}.json")
    (RAW / "eng_static_ks.json").parent.mkdir(parents=True, exist_ok=True)
    (RAW / "eng_static_ks.json").write_text(json.dumps(static_ks()), encoding="utf-8")


def run():
    py = sys.executable
    for name in CASES:
        r = subprocess.run([py, str(HERE / "run_case.py"), name, "--steps", "search,l1,l2,l3,l4"], cwd=ROOT)
        if r.returncode:
            raise SystemExit(f"run_case failed for {name}")
    # mount static moduli: long-wavelength speeds
    sys.path.insert(0, str(HERE))
    from run_case import container  # noqa: E402
    name = "eng_mount_cb_c0.592_w0.151"
    out = RAW / name
    for n in STATIC_LV:
        f = out / f"static_q2_n{n}.json"
        if f.exists():
            continue
        cmd = (f"mpirun -n 4 python3 scripts/verify/dolfinx/bloch_dolfinx.py --case {(INP / f'{name}.json').relative_to(ROOT).as_posix()} "
               f"--deg 2 --nev 6 --model exact --n {n} --split --ks {(RAW / 'eng_static_ks.json').relative_to(ROOT).as_posix()} "
               f"--out {f.relative_to(ROOT).as_posix()}")
        container(f"eng_static_n{n}", cmd)


def _moduli(rec_by_k, nu, phi):
    """Cubic moduli (units of E_s) from the three acoustic branches at the four static k."""
    ct = np.sqrt(1.0 / (2 * (1 + nu)))

    def speeds(k):
        r = rec_by_k[tuple(np.round(k, 9))]
        f = np.sort(np.array(r["f"][:3]))
        return 2 * np.pi * ct * f / np.linalg.norm(k)

    ks = static_ks()
    v100 = [speeds(ks[0]), speeds(ks[1])]
    v110 = [speeds(ks[2]), speeds(ks[3])]
    ext = lambda a, b: (4 * a - b) / 3  # v(k) = v0 + c k^2 with k2 = 2 k1
    vt100, vl100 = ext(v100[0][:2].mean(), v100[1][:2].mean()), ext(v100[0][2], v100[1][2])
    v3 = ext(v110[0], v110[1])
    C44 = phi * vt100 ** 2
    C11 = phi * vl100 ** 2
    # [110]: one shear branch is C44 (polarized along z); of the other two the larger is longitudinal
    iz = int(np.argmin(np.abs(phi * v3 ** 2 - C44)))
    rest = sorted(np.delete(v3, iz))
    CT2, CL = phi * rest[0] ** 2, phi * rest[1] ** 2
    C12_t = C11 - 2 * CT2
    C12_l = 2 * CL - C11 - 2 * C44
    C12 = C12_t
    E100 = (C11 - C12) * (C11 + 2 * C12) / (C11 + C12)
    return dict(C11=C11, C12=C12, C44=C44, C12_from_L110=C12_l, E100=E100, G=C44, bulk=(C11 + 2 * C12) / 3,
                z_branch_C44_rel=float(abs(phi * v3[iz] ** 2 - C44) / C44), dispersion_rel_vl100=float(
                    abs(v100[1][2] - v100[0][2]) / v100[0][2]))


def analyse():
    sys.path.insert(0, str(HERE))
    import compare as cmp  # noqa: E402  (V1c protocol functions)
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for name, key in CASES.items():
        c = load(INP / f"{name}.json")
        nb = c["below_band"]
        L = {n: cmp.load(RAW / name / f"q2_n{n}.json") for n in (10, 15, 20, 30)}
        used = [15, 20, 30] if L[30] else [10, 15, 20]
        ks = [r["k"] for r in L[used[-1]]["records"]]
        E = {n: cmp.edges(L[n]["records"], nb, ks) for n in used}
        h = [1.0 / n for n in used]
        rlo = cmp.extrapolate(h, [E[n][0] for n in used])
        rhi = cmp.extrapolate(h, [E[n][1] for n in used])
        s_lo, s_hi = c["amm"]["safe_interval"]
        f_lo, f_hi = c["claim"]
        g = dict(role=c["role"], claim=c["claim"], amm_safe=[s_lo, s_hi], amm_edges=c["amm"]["edges"],
                 levels=used, dolfinx_edges={str(n): dict(lo=E[n][0], hi=E[n][1]) for n in used},
                 ref_lo=rlo, ref_hi=rhi,
                 verdict_lo=cmp.classify_lo(s_lo, rlo["ext"], rlo["u"]) if s_lo is not None else "no safe edge",
                 verdict_hi=cmp.classify_hi(s_hi, rhi["ext"], rhi["u"]) if s_hi is not None else "no safe edge",
                 claim_inside_reference=bool(f_lo >= rlo["ext"] + 2 * rlo["u"] and f_hi <= rhi["ext"] - 2 * rhi["u"]),
                 claim_inside_finest_gap=bool(f_lo > E[used[-1]][0] and f_hi < E[used[-1]][1]),
                 n_k_finest=len(ks), timing=cmp.load(RAW / name / "timing.json"))
        if s_lo is not None and s_hi is not None:
            g["margin_over_2u"] = dict(lo=(s_lo - rlo["ext"]) / (2 * rlo["u"]), hi=(rhi["ext"] - s_hi) / (2 * rhi["u"]))
        res[key] = dict(gap=g)
    # mount static
    name = "eng_mount_cb_c0.592_w0.151"
    c = load(INP / f"{name}.json")
    cw, ww = c["geometry"]["c"], c["geometry"]["w"]
    phi = cw ** 3 + 3 * ww ** 2 * (1 - cw)
    mods = {}
    for n in STATIC_LV:
        d = cmp.load(RAW / name / f"static_q2_n{n}.json")
        if d:
            mods[n] = _moduli({tuple(np.round(r["k"], 9)): r for r in d["records"]}, c["nu"], phi)
    if len(mods) == len(STATIC_LV):
        used = STATIC_LV[-3:]  # the three finest levels, as for the gap edges
        h = [1.0 / n for n in used]
        cert = load(ROOT / MOUNT_CERT)["blocks"]["static"]["convergence"]["quantities"]
        st = dict(phi_exact=phi, levels=list(STATIC_LV), levels_reference=list(used), per_level=mods)
        for q in ("E100", "G", "bulk"):
            r = cmp.extrapolate(h, [mods[n][q] for n in used])
            gl, gu = cert[q]["lower"], cert[q]["upper"]
            st[q] = dict(ref=r, amm_guarded=[gl, gu], amm_extrapolated=cert[q]["extrapolated"],
                         ref_inside_guard=bool(gl <= r["ext"] <= gu),
                         lower_bound_sound=("sound" if gl <= r["ext"] - 2 * r["u"] else
                                            ("marginal" if gl <= r["ext"] + 2 * r["u"] else "unsound")))
        st["E100_target"] = load(ROOT / MOUNT_CERT)["targets"]["E100_min"]
        res["mount"]["static"] = st
    (OUT / "references.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: {kk: (vv if kk != "static" else {q: vv[q] for q in ("E100",) if q in vv})
                          for kk, vv in v.items()} for k, v in res.items()}, indent=1, default=float)[:4000])


if __name__ == "__main__":
    {"export": export, "run": run, "analyse": analyse}[sys.argv[1]]()
