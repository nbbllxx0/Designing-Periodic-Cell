"""Tutorial (a): evaluate one unit cell at the search tier and read its full homogenized stiffness tensor C*.

    python examples/01_evaluate_tensor.py

What it shows
  * a design session through the tool contract (amm.tools.Session), the same calls an agent or the GUI makes;
  * `evaluate`: density, E100, G, bulk, nu100, complete band gaps, and (schema amm-tools/2) the full 6x6 tensor C*
    in Voigt order 11 22 33 23 13 12 with engineering shear, normalized by the solid's Young's modulus E_s, plus
    C_MPa for the chosen material and derived quantities (cubic constants, Zener ratio, directional moduli,
    Voigt-Reuss averages, eigenvalues).

Search-tier values are fast estimates (static n = 20, bands n = 10), biased stiff by several per cent. They are NOT
certificates; tutorial 02 certifies a design.

Needs only the core install (no atlas data, no GPU: without CUDA the band solver runs on the CPU, slower and not
bit-identical to the GPU path). Runtime: about 5-15 s on a GPU machine, longer on CPU only.
"""
from __future__ import annotations

import json
import platform
import sys
import time

import numpy as np

import amm  # import amm before torch: MKL's OpenMP runtime must initialize first (amm/_runtime.py)
from amm import tools


def main() -> int:
    t0 = time.perf_counter()
    import torch  # noqa: E402  (after amm, on purpose)
    from amm import bloch
    print(f"amm {amm.__version__}, Python {platform.python_version()}, torch {torch.__version__}, "
          f"band solver device: {bloch.resolve_device('cuda')}")

    s = tools.Session(root=None, profile="C")          # root=None: no session log on disk
    print("tools:", ", ".join(s.tools()))
    r = s.call("set_material", {"name": "Ti6Al4V"})    # E = 113.8 GPa, nu = 0.342, rho = 4430 kg/m^3
    assert r["ok"], r
    print("material:", {k: r["result"][k] for k in ("material", "E_Pa", "nu", "rho_kg_m3")})
    assert s.call("set_constraints", {"cell_size": 5, "cell_size_unit": "mm"})["ok"]  # needed for gaps in Hz

    design = {"kind": "gyroid", "params": {"density": 0.25, "mode": "sheet"}}
    t1 = time.perf_counter()
    out = s.call("evaluate", {"designs": [design]})
    t_eval = time.perf_counter() - t1
    assert out["ok"], out
    res = out["result"]
    row = res["results"][0]
    print(f"\nevaluate {design} ({res['tier']}), {t_eval:.1f} s")
    for k in ("density", "E100", "G", "bulk", "nu100", "valid"):
        print(f"  {k:8s} {row[k]}")
    for k in ("E100_MPa", "G_MPa", "bulk_MPa"):
        print(f"  {k:8s} {row[k]:.1f}")
    print("  complete gaps (f* = f a / c_t):", [(round(g["f_lo"], 4), round(g["f_hi"], 4)) for g in row["gaps"]]
          or "none")
    print("  gaps in Hz (5 mm cell):", [(round(a), round(b)) for a, b in row.get("gaps_Hz", [])] or "none")

    C = np.array(row["C"])
    np.set_printoptions(precision=5, suppress=True, linewidth=120)
    print("\nC* / E_s (Voigt order 11 22 33 23 13 12, engineering shear):")
    print(C)
    print("\nC* in MPa:")
    print(np.array(row["C_MPa"]).round(1))
    d = row["derived"]
    print("\nderived:")
    for k in ("C11", "C12", "C44", "zener", "cubic_deviation", "E100", "E110", "E111", "nu12", "bulk_voigt", "bulk_reuss",
              "shear_voigt", "shear_reuss", "min_eig"):
        if k in d:
            print(f"  {k:16s} {d[k]:.6g}")
    if "eigenvalues" in d:
        print("  eigenvalues     ", np.round(d["eigenvalues"], 6))
    print("  note:", d["note"])

    # a few consistency checks a reader can rely on
    assert np.allclose(C, C.T, atol=1e-8 * np.abs(C).max()), "C* is symmetric"
    assert np.linalg.eigvalsh(C).min() > 0, "C* is positive definite"
    assert abs(d["E100"] - row["E100"]) <= 1e-3 * row["E100"] + 1e-12, "E100 from the tensor matches the row"
    print(f"\nchecks passed (symmetric, positive definite, E100 consistent); total {time.perf_counter() - t0:.1f} s")
    print("summary:", json.dumps(dict(design=design, density=row["density"], E100=row["E100"],
                                      zener=d.get("zener"), seconds_evaluate=round(t_eval, 1),
                                      python=platform.python_version(), platform=platform.platform())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
