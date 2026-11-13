"""Thin wrapper over MKL PARDISO (via pypardiso) with explicit phases.

The symbolic analysis (phase 11) depends only on the sparsity pattern, so it runs once per pattern; each new
matrix on the same pattern needs only numeric factorization (phase 22). For symmetric indefinite matrices
(mtype -2) PARDISO reports the inertia: iparm(22) positive and iparm(23) negative eigenvalues of the factored
matrix, and iparm(14) perturbed pivots. A count is only trusted when iparm(14) == 0.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from pypardiso import PyPardisoSolver

from . import _runtime


class Pardiso:
    def __init__(self, mtype: int):
        # MKL's runtime is initialized (once, by a 1x1 solve) before the first real factorization: the same
        # sequence of MKL calls as the import-time warm-up that amm/__init__.py did before 2026-11-07
        _runtime.ensure_mkl("first PARDISO solver")
        self.s = PyPardisoSolver(mtype=mtype)
        self.s.set_statistical_info_off()
        self._pattern = None
        self._A = None

    def _same_pattern(self, A: sp.csr_matrix) -> bool:
        p = self._pattern
        return p is not None and p[0] is A.indptr and p[1] is A.indices

    def factor(self, A: sp.csr_matrix) -> dict:
        """A: CSR upper triangle (symmetric types). Returns factor statistics."""
        A = A if A.has_sorted_indices else A.sorted_indices()
        b = np.zeros(A.shape[0])
        if not self._same_pattern(A):
            self.s.set_phase(11)
            self.s._call_pardiso(A, b)
            self._pattern = (A.indptr, A.indices)
        self.s.set_phase(22)
        self.s._call_pardiso(A, b)
        self._A = A
        return dict(n_pos=int(self.s.get_iparm(22)), n_neg=int(self.s.get_iparm(23)),
                    n_perturbed=int(self.s.get_iparm(14)))

    def solve(self, b: np.ndarray) -> np.ndarray:
        self.s.set_phase(33)
        # PARDISO reads multiple right-hand sides column by column (Fortran order)
        b = np.asfortranarray(b, dtype=np.float64)
        x = self.s._call_pardiso(self._A, b)
        return np.asarray(x).reshape(b.shape)

    def free(self):
        self.s.free_memory(everything=True)
        self._pattern = None
        self._A = None
