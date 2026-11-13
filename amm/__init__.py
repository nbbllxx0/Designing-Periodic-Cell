"""AgenticMetamaterials core package (independent project; see 00_INDEPENDENT_PROJECT__NOT_AgenticTO.md).

Units inside the solvers are normalized: solid Young's modulus E_s = 1, Poisson ratio nu_s, density rho_s = 1,
cell edge a = 1. Frequencies are reported as f* = f a / c_t with c_t the solid's shear-wave speed.

Importing amm solves nothing (B3, 2026-11-07). It sets the MKL environment defaults (MKL_NUM_THREADS=16,
MKL_CBWR=AUTO,STRICT) and installs the MKL-before-torch import guard; MKL itself is initialized lazily, before
torch loads or at the first PARDISO use. The ordering guarantee is explained in amm/_runtime.py.
"""
__version__ = "0.2.0"

from . import _runtime

_runtime.set_env_defaults()
_runtime.install_guard()


def __getattr__(name):
    # MKL_CBWR_STATUS: the MKL reproducibility mode that took (AUTO|STRICT = 0x10002 = 65538, off = 1). Reading it
    # initializes MKL (a 1x1 PARDISO solve) if that has not happened yet; before 2026-11-07 it was set at import.
    if name == "MKL_CBWR_STATUS":
        return _runtime.cbwr_status()
    raise AttributeError(f"module 'amm' has no attribute {name!r}")
