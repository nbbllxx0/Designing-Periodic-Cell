import os, sys, time, numpy as np
import amm
from amm import geometry as G, fem, bloch
n = int(sys.argv[1])
mesh = fem.build_mesh(G.clean(G.resonator("cube_bars", n, c=0.6, w=0.2))[0])
ic = bloch.InertiaCounter(mesh)
ks = bloch.ibz_interior(6, 1)
ic.counts(ks[0], [0.5])
t = time.perf_counter()
for k in ks:
    ic.counts(k, [0.5])
print(f"threads={os.environ.get('MKL_NUM_THREADS','all')} n={n} ndof={mesh.ndof} {1000*(time.perf_counter()-t)/len(ks):.0f} ms/factorization", flush=True)
