"""V4 item 4: solve time and peak memory against resolution n, CPU (PARDISO) and GPU where both paths exist,
plus MKL thread scaling. One fresh process per measurement (clean peak working set, MKL threads fixed at start).

    python scripts/ops/gpulock_run.py v4 -- python scripts/verify/v4/scaling.py

Representative cell: cube_bars c = 0.6, w = 0.2 (the resonator bench design of results/speed/NOTES.md), nu = 0.3,
finite-cell partial voxels as in the certificate (geometry.design_cell + fem.build_mesh(cov, sub)).
- static (CPU only; amm has no GPU static solver): n = 16, 24, 32, 48, 64. Times: voxelization, mesh build,
  homog.homogenize (assembly + PARDISO mtype 2 factorization + 6 solves + post-processing; 2 repeats), and a
  component breakdown (assembly, analysis+factorization, solve) with the same amm calls. PARDISO memory from
  iparm(15)-(17) where reported.
- Bloch CPU (certificate path): n = 10, 20, 30, 40. InertiaCounter.counts: the first factorization at a k-point
  (symbolic analysis + numeric) and later ones (numeric only, pattern reused), one shift each; one shift-invert
  Lanczos edge solve (InertiaCounter.edge).
- Bloch GPU (search-tier path, dense complex64): n = 10 and 20 (n >= 30 needs > 24 GB per dense k-point matrix
  triple and is not attempted; the estimate is recorded). One k-point cold and warm, and the 21-point path at n=10.
- threads: static n = 48 and Bloch CPU n = 30 at MKL_NUM_THREADS = OMP_NUM_THREADS = 4, 8, 16, 24.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SPEC = dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.2))
NU = 0.3
RAWF = common.RAW / "scaling.jsonl"


def _mesh(n):
    from amm import fem, geometry
    t = time.perf_counter()
    cov, sub, info = geometry.design_cell(SPEC, n)
    t_geo = time.perf_counter() - t
    t = time.perf_counter()
    mesh = fem.build_mesh(cov, sub=sub, nu=NU)
    t_mesh = time.perf_counter() - t
    return mesh, info, round(t_geo, 3), round(t_mesh, 3)


def child_static(n):
    import numpy as np
    import scipy.sparse as sp
    from amm import fem, homog
    from amm.pardiso import Pardiso
    mesh, info, t_geo, t_mesh = _mesh(n)
    m0 = common.mem()
    reps = []
    for _ in range(2):
        t = time.perf_counter()
        r = homog.homogenize(mesh=mesh)
        reps.append(round(time.perf_counter() - t, 3))
    m1 = common.mem()
    # component breakdown, same amm calls as homog.homogenize
    t = time.perf_counter()
    K = mesh.assemble("K")
    keep = np.arange(3, mesh.ndof)
    U = sp.triu(K[keep][:, keep].tocsr(), format="csr")
    U.sort_indices()
    t_asm = time.perf_counter() - t
    xloc = fem.OFF * mesh.h
    chi0 = np.stack([(xloc @ e.T).ravel() for e in homog.STRAINS])
    fe = np.einsum("eij,mj->mei", mesh.Ke, chi0)
    F = np.stack([np.bincount(mesh.edof.ravel(), weights=fe[m].ravel(), minlength=mesh.ndof) for m in range(6)], 1)
    s = Pardiso(mtype=2)
    t = time.perf_counter()
    s.factor(U)
    t_fac = time.perf_counter() - t
    t = time.perf_counter()
    s.solve(F[keep])
    t_sol = time.perf_counter() - t
    ip = {f"iparm{i}": int(s.s.get_iparm(i)) for i in (15, 16, 17, 18)}
    s.free()
    common.emit(dict(kind="static", n=n, ndof=mesh.ndof, ne=mesh.ne, nnz=int(len(mesh.indices)),
                     density=round(info["density"], 5), t_geometry_s=t_geo, t_mesh_s=t_mesh,
                     t_homogenize_s=reps, t_assemble_s=round(t_asm, 3), t_factor_s=round(t_fac, 3),
                     t_solve6_s=round(t_sol, 3), E100=r["E100"], max_residual=r["max_residual"],
                     mem_before_solve=m0, mem_after=m1, pardiso=ip, env=common.env_record()))


def child_bloch_cpu(n, f_lo, f_hi):
    from amm import bloch
    mesh, info, t_geo, t_mesh = _mesh(n)
    m0 = common.mem()
    ic = bloch.InertiaCounter(mesh)
    k1, k2, k3 = [bloch.np.array(k) * bloch.np.pi for k in ((0.5, 0.0, 0.0), (0.5, 0.5, 0.0), (0.5, 0.5, 0.5))]
    t = time.perf_counter()
    c1 = ic.counts(k1, [f_lo])
    t_first = time.perf_counter() - t
    t = time.perf_counter()
    c2 = ic.counts(k2, [f_lo, f_hi])
    t_two = time.perf_counter() - t
    t = time.perf_counter()
    e = ic.edge(k3, f_lo, "below")
    t_edge = time.perf_counter() - t
    ip = {f"iparm{i}": int(ic.solver.s.get_iparm(i)) for i in (15, 16, 17, 18)}
    ic.free()
    common.emit(dict(kind="bloch_cpu", n=n, ndof=mesh.ndof, real2n=2 * mesh.ndof, density=round(info["density"], 5),
                     t_geometry_s=t_geo, t_mesh_s=t_mesh, t_count_first_s=round(t_first, 3),
                     t_count_per_factor_s=round(t_two / 2, 3), t_edge_lanczos_s=round(t_edge, 3),
                     counts=[c1, c2], edge=e, mem_before=m0, mem_after=common.mem(), pardiso=ip,
                     env=common.env_record()))


def child_bloch_gpu(n):
    from amm import bloch
    import torch
    mesh, info, t_geo, t_mesh = _mesh(n)
    N = mesh.ndof
    per_k_gb = 3 * N * N * 8 / 1e9
    rec = dict(kind="bloch_gpu", n=n, ndof=N, density=round(info["density"], 5), t_geometry_s=t_geo,
               t_mesh_s=t_mesh, dense_per_k_gb=round(per_k_gb, 2))
    if per_k_gb > 18:
        rec.update(skipped=f"dense K, M, A of {N} x {N} complex64 need {per_k_gb:.1f} GB per k-point (> 24 GB card)")
        common.emit(dict(rec, env=common.env_record()))
        return
    ks, _ = bloch.kpath(4)
    torch.cuda.reset_peak_memory_stats()
    t = time.perf_counter()
    gb = bloch.GPUBands(mesh, device="cuda")
    torch.cuda.synchronize()
    t_setup = time.perf_counter() - t
    times = []
    for i in range(3):
        t = time.perf_counter()
        try:
            gb(ks[i * 5:i * 5 + 1], nev=24)
        except torch.OutOfMemoryError as e:  # recorded as a result: the dense path does not fit at this n
            rec.update(skipped=f"CUDA out of memory at one k-point ({str(e).splitlines()[0]})",
                       gpu_peak_alloc_mb=round(torch.cuda.max_memory_allocated() / 2**20, 1))
            common.emit(dict(rec, env=common.env_record()))
            return
        torch.cuda.synchronize()
        times.append(round(time.perf_counter() - t, 3))
    rec.update(t_setup_s=round(t_setup, 3), t_1k_s=times)
    if n <= 10:
        t = time.perf_counter()
        gb(ks, nev=24)
        torch.cuda.synchronize()
        rec["t_path21_s"] = round(time.perf_counter() - t, 3)
    rec.update(gpu_peak_alloc_mb=round(torch.cuda.max_memory_allocated() / 2**20, 1), mem_after=common.mem())
    common.emit(dict(rec, env=common.env_record()))


def child_probe():
    from amm import atlas, evaluate
    r = evaluate.evaluate(SPEC, nu=NU, keep_bands=False, **atlas.SEARCH_TIER)
    common.emit(dict(kind="probe", gaps=r["gaps"], E100=r["E100"], density=r["density"]))


def driver():
    done = {(r["kind"], r["n"], r["env"]["MKL_NUM_THREADS"]) for r in common.read_jsonl(RAWF) if "n" in r}
    probe = [r for r in common.read_jsonl(RAWF) if r["kind"] == "probe"]
    if not probe:
        p = common.run_child([__file__, "--child", "probe"], dict(MKL_NUM_THREADS=16, OMP_NUM_THREADS=16))
        common.append_jsonl(RAWF, p)
        probe = [p]
    g = probe[0]["gaps"][0]
    w = g["f_hi"] - g["f_lo"]
    f_lo, f_hi = g["f_lo"] + 0.25 * w, g["f_hi"] - 0.25 * w
    plan = [("static", n, 16) for n in (16, 24, 32, 48, 64)]
    plan += [("bloch_cpu", n, 16) for n in (10, 20, 30, 40)]
    plan += [("bloch_gpu", n, 16) for n in (10, 20, 30)]
    plan += [("static", 48, th) for th in (4, 8, 24)] + [("bloch_cpu", 30, th) for th in (4, 8, 24)]
    for kind, n, th in plan:
        if (kind, n, str(th)) in done:
            continue
        args = [__file__, "--child", kind, str(n)] + ([str(f_lo), str(f_hi)] if kind == "bloch_cpu" else [])
        r = common.run_child(args, dict(MKL_NUM_THREADS=th, OMP_NUM_THREADS=th))
        common.append_jsonl(RAWF, r)
        keys = [k for k in r if k.startswith("t_") or k in ("ndof", "skipped", "gpu_peak_alloc_mb")]
        print(kind, n, th, {k: r[k] for k in keys}, r.get("mem_after", {}).get("peak_wset_mb"), flush=True)


if __name__ == "__main__":
    if "--child" in sys.argv:
        a = sys.argv[sys.argv.index("--child") + 1:]
        if a[0] == "probe":
            child_probe()
        elif a[0] == "static":
            child_static(int(a[1]))
        elif a[0] == "bloch_cpu":
            child_bloch_cpu(int(a[1]), float(a[2]), float(a[3]))
        else:
            child_bloch_gpu(int(a[1]))
    else:
        driver()
