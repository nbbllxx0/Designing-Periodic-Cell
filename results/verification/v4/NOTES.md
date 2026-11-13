# V4: performance (throughput, latency, certificate time, workflow time, scaling)

Plan item V4 (`plan/SOFTWARE_PAPER_PLAN.md`, claim S3, table T6, figure F6). Run 2026-11-08 (local time 04:4x-05:25)
by `scripts/verify/v4/`. No LLM was called. `amm/` was not edited. Throughput, response latency, certificate time and
workflow time are reported separately (S3 wording). V7 (GUI latency, browser vs solver) and V8 (interaction cost)
are not covered here.

## Code version and environment

- amm 0.2.0, **checker hash f141e46cb67a78db**, tool code hash 5970bf55108f1584 (`amm.tools.code_hash`), recorded
  by every fresh process (`raw/*.jsonl`, field `env`). The checker hash equals the one in the V3 and V1b certificates.
- Python 3.10.18, numpy 2.2.6, scipy 1.15.3, pypardiso 0.4.7, Intel oneAPI MKL 2026.2 (build 20260915), torch
  2.5.1+cu124 (CUDA 12.4), BoTorch 0.14.0, GPyTorch 1.14, psutil 7.2.2, matplotlib 3.10.7.
- Hardware: NVIDIA GeForce RTX 4090 (24 GB), Intel i9-13900KF (8 P + 16 E cores, 32 logical CPUs), Windows 11
  (build 26200).
- Threads: `MKL_NUM_THREADS = OMP_NUM_THREADS = 16` (amm's default, the agent launcher's setting) unless a row says
  otherwise; `MKL_CBWR=AUTO,STRICT` (amm default); torch reported 16 threads. The search tier uses 4 static worker
  threads (`atlas.SEARCH_TIER`).
- All fresh runs held the shared lock (`scripts/ops/gpulock_run.py v4 -- ...`), one timing job at a time; nothing
  else was running. Exception: `reuse.py` (reads JSON/CSV files for a few seconds) ran once while the throughput job
  was running.

## Method

| Item | Script | What is timed |
|---|---|---|
| 1 throughput | `throughput.py` | `evaluate.evaluate_batch(specs, nu=0.3, keep_bands=True, **atlas.SEARCH_TIER)` (static n = 20 CPU PARDISO in 4 threads, Bloch n = 10 dense complex64 on the GPU, 21 k, 24 eigenvalues), the search tool's evaluator. One fresh process per (family, batch B, threads). Cold = first call of the process (CUDA context, cuSOLVER, MKL init, finite-cell tables; Python import time recorded separately). Warm = max(2, 16/B) further calls on new random specs, plus one warm call on the cold call's specs. Families: gyroid network (density 0.12-0.45), bcc struts (r 0.05-0.12, R = 0), cube_bars (c 0.4-0.8). B = 1, 4, 16, 64 at 16 threads; B = 16 also at 4 threads (V3's search-process setting). |
| 2 latency | `latency.py` | `amm.tools.Session.call(name, args, actor="agent")`, the call the MCP server makes, in one fresh process, profile C. Wall time around the call (equals the logged `dt_s` to within 3 ms). See `latency.csv` notes for the designs and specs. |
| 3 certificates | `reuse.py` | timing blocks of existing certificates (no rerun) + 3 fresh certificates through the `certify` tool (repeats of V3 certificates S20/M4, G15/M5, M05/M4). |
| 4 scaling | `scaling.py` | one fresh process per point; cube_bars c 0.6, w 0.2, nu 0.3, finite-cell voxels. Static: `homog.homogenize` (min of 2 repeats) + breakdown; Bloch CPU: `InertiaCounter.counts` (one factorization at one shift; first call adds the symbolic analysis) and one `InertiaCounter.edge` Lanczos solve; Bloch GPU: `GPUBands` at one k. Memory: process peak working set (psutil) and `torch.cuda.max_memory_allocated`. |
| 5 workflow | `reuse.py` | V3 `runs.csv`: workflow = search seconds + certificate seconds per target x method (checked: equals the `workflow_seconds` column to 0.0 s in all 128 rows). |

Tables: `tables.py`; figure: `figure.py` (data plot only).

## Results

### 1. Search-tier throughput (`throughput.csv`)

Warm median cells/s (range over warm calls) and cold cells/s, 16 threads:

| family | B = 1 | B = 4 | B = 16 | B = 64 |
|---|---|---|---|---|
| gyroid network | 1.30 (0.80-1.39); cold 0.75 | 1.29; cold 0.93 | 1.22; cold 1.16 | 1.16; cold 1.14 |
| bcc struts | 1.67 (1.02-1.80); cold 0.92 | 1.67; cold 1.30 | 1.85; cold 1.63 | 1.68; cold 1.66 |
| cube_bars | 1.60 (1.09-1.82); cold 0.87 | 1.59; cold 1.53 | 1.62; cold 1.61 | 1.56; cold 1.60 |

- About 0.55-0.85 s per cell. Batching does not raise throughput: the best B is 1 (gyroid) or 16 (bcc, cube_bars), and B = 64 is 3-11 % below it. `evaluate_batch`
  voxelizes and solves the GPU bands of each cell in turn on the main thread; only the static solves run in the
  4-thread pool, so a batch overlaps CPU static with GPU Bloch work but never batches the GPU work across cells.
- Cold cost: Python import 2.0-2.6 s; the first call is about 0.5-1 s slower than a warm call (B = 1: 1.09-1.33 s
  cold vs 0.60-0.77 s per cell warm); at B = 16 and 64 cold throughput is 0-12 % below warm (struts B = 16: 1.63 vs 1.85 cells/s).
- GPU memory: peak allocated 5.0-6.2 GB (`GPUBands` sizes k-chunks to about 6 GB), but the PyTorch caching allocator reserved 7.4-23.4 GB (23.4 GB for gyroid at B = 16): cells of different size leave cached blocks, so a search-tier process can hold nearly the whole 24 GB card. Process working set 1.0-1.6 GB.
- 4 MKL threads at B = 16: 1.24 / 1.91 / 1.64 cells/s (gyroid / bcc / cube_bars), equal to or 2-4 % above 16
  threads (4 workers x 16 threads oversubscribe the CPU).

### 2. Tool latency (`latency.csv`, per call in `raw/latency_calls.csv`)

Fresh, through `Session.call` (median [min, max], n calls; cold = first call in the process):

| tool | median s | range s | n | notes |
|---|---|---|---|---|
| set_material / set_target / set_constraints | < 0.001 (set_material 0.19-0.27 s when it loads an atlas) | | 10 / 10 / 1 | |
| check_bounds | 0.686 | 0.677-0.693 | 6 | bounds + atlas oracle |
| atlas_suggest (atlas lookup) | 0.690 | 0.677-0.697 | 6 | |
| evaluate, 1 design | 0.90 | 0.59-2.59 (cold 2.59) | 6 | 6 designs, 3 families |
| evaluate, 16 designs | 10.93 | 10.91-11.06 | 3 | 0.68 s per design |
| screen_manufacturing | 6.13 | 5.75-7.62 | 6 | tiles 3, resolution 64 |
| export | 6.26 | 5.95-7.65 | 6 | STL + report.json |
| search (default budget 32) | 33.2 | 26.7-52.3 | 6 | 6 V3 targets, one call each |
| certify | 259.9 | 101.0-343.8 | 3 | as-built on |

Reused, E4 agent sessions (Codex, 234 sessions, logged `dt_s`, older code 90f3823f15cbeff4, successful calls):
check_bounds median 0.65 s (n 77), atlas_suggest 0.65 s (124), evaluate 1 design 2.57 s (14; mostly the first CUDA
use of the process), evaluate 16 designs 8.59 s (4), search 76.9 s (133; agents chose budgets 40-96, 93 calls at
96: median 78.7 s, max 755.7 s), certify 240.9 s (82; range 42-2440 s). V3 library search at budget 48 (M4, 24
targets): median 43.7 s (31.0-80.0 s).

### 3. Certificate time (`cert_times.csv` row level, `cert_times_summary.csv`)

| source (code) | n | total median s | IQR s | range s | static median | Bloch median | as-built median |
|---|---|---|---|---|---|---|---|
| V3 (checker f141e46c, as-built off, alone, 16 thr) | 85 | 203.9 | 105.4-389.1 | 53.6-900.5 | 87.5 | 220.4 (n 46) | - |
| V3 static targets | 39 | 104.5 | | 53.6-759.0 | | | |
| V3 gap targets | 28 | 280.3 | | 75.4-756.8 | 55.8 | 223.0 | |
| V3 combined targets | 18 | 353.7 | | 112.5-900.5 | 99.6 | 219.4 | |
| V1b (f141e46c, as-built on, concurrent jobs, 12 thr) | 6 | 588.8 | 449.3-693.5 | 152.7-974.1 | 151.8 | 517.4 | 22.1 |
| E4 (f2e482d81382b400, pre-B3, as-built on, agent sessions) | 82 | 240.9 | 119.2-320.9 | 42.2-2440.1 | 58.0 | 204.2 | 10.7 |
| V4 fresh (f141e46c, as-built on, alone) | 3 | 259.9 | | 101.0-343.8 | 96.9 | 188.8 | 11.8 |

By family (V3): TPMS 106.0 s (n 33), struts 226.5 s (10), resonators 305.7 s (42). E4: TPMS 103.3 s (15), struts
387.5 s (13), resonators 246.8 s (54). Static target certificates are mostly TPMS; Bloch blocks dominate gap and
combined certificates.

**Tie to the current code:** the 3 fresh certificates give the same verdicts as V3 (all certified) and their static
and Bloch blocks are identical to the V3 certificates field by field after removing timing fields (the only
remaining differences are `edge_extra_seconds`, a timing field). Block times agree within 1 %: S20 static 96.9 vs
96.4 s; G15 static 52.9 vs 53.0 s, Bloch 195.1 vs 195.6 s; M05 static 146.1 vs 146.4 s, Bloch 182.4 vs 182.1 s.
So the V3 timings stand for the current code. V1b ran under CPU contention (V1b NOTES) and is slower; E4 used the
pre-B1-B3 code (different checker hash; B1-B3 report bit-identical outputs) and includes Ti/PA12/316L agent targets.

### 4. Scaling with resolution (`scaling.csv`), cube_bars c 0.6, w 0.2

| n | static ndof | static solve s | static peak MB | Bloch ndof | count s (1 factor.) | Lanczos edge s | CPU peak MB | GPU 1 k s | GPU alloc MB |
|---|---|---|---|---|---|---|---|---|---|
| 10 | | | | 1,272 | 0.022 | 0.126 | 130 | 0.015 (21 k: 0.31) | 1,576 |
| 16 | 5,118 | 0.43 | 133 | | | | | | |
| 20 | | | | 8,166 | 0.138 | 1.10 | 312 | 1.25 | 3,626 |
| 24 | 17,826 | 0.56 | 313 | | | | | | |
| 30 | | | | 25,428 | 0.658 | 4.41 | 998 | CUDA OOM (19.4 GB allocated) | |
| 32 | 35,802 | 0.78 | 587 | | | | | | |
| 40 | | | | 57,810 | 2.30 | 12.6 | 2,543 | not attempted | |
| 48 | 107,886 | 2.17 | 1,895 | | | | | | |
| 64 | 253,338 | 6.75 | 5,088 | | | | | | |

- Static at n = 64: factorization 4.53 s, 6 solves 0.88 s, assembly 0.41 s, mesh build 2.54 s (outside the solve).
- Static is CPU only: amm has no GPU static solver. The two Bloch paths are different solvers (GPU dense eigensolve
  for the search tier; CPU sparse inertia counts for the certificate), not two implementations of one.
- Dense GPU Bloch is O(N^3) per k: 0.015 s at n = 10, 1.25 s at n = 20 (83x for 6.4x ndof); n = 30 does not fit.
- MKL threads (one process each): static n = 48, 4 / 8 / 16 / 24 threads: 2.61 / 1.94 / 2.17 / 2.25 s
  (factorization 1.59 / 0.93 / 1.00 / 1.06 s); Bloch count n = 30: 0.887 / 0.600 / 0.658 / 0.671 s.

### 5. Workflow time, spec to certified design (`workflow.csv`; V3, budget 48)

| method | certified / 20 | median s, certified successes [range] | median s, all targets | s per certified design |
|---|---|---|---|---|
| M1 atlas-only | 12 | 109.5 [54.0, 688.2] | 153.4 | 331.8 |
| M2 Sobol | 6 | 190.4 [126.4, 633.8] | 88.3 | 589.4 |
| M3 DE | 9 | 173.0 [98.8, 657.0] | 171.9 | 625.1 |
| M4 BO full (amm) | 14 | 191.0 [95.5, 651.8] | 191.0 | 346.9 |
| M5 BO no seeding | 9 | 201.2 [134.9, 680.4] | 155.9 | 440.6 |
| M6 BO no correction | 14 | 184.0 [94.6, 946.7] | 184.0 | 406.5 |

Search is 41-51 s median for the searching methods (0.8 s for atlas-only); the certificate dominates the workflow.
"s per certified design" = total workflow time over all 20 targets / certified successes. Failures without a
certificate (search-tier miss) have workflow = search time only, which lowers the all-target medians of M2 and M5.

## Caveats

- One machine, one run per point (throughput: 2-16 warm calls; scaling: 1-2 repeats). The thread-scaling points
  are single processes; differences of < 10 % are within run-to-run noise seen elsewhere in this run.
- Throughput specs are random within each box; per-cell cost depends on the cell's solid volume, so B = 1 ranges are
  wide (0.8-1.8 cells/s). Batches of 64 exceed the evaluate tool's 16-design cap (library calls).
- Latency calls ran in one session; search calls used six different targets (one each), so their range mixes
  target and process effects; certify n = 3.
- E4 latencies and certificate times come from older code (checker f2e482d81382b400, code 90f3823f15cbeff4).
  E4's search latency mixes agent-chosen budgets (40-96).
- Peak memory is the process working-set peak (includes mesh and Python), not the PARDISO factor alone; PARDISO's
  iparm(15)-(17) are in `scaling.csv` as reported by MKL.
- Compute: about 36 min of locked wall time (throughput 922 s, latency + 3 certificates 1048 s, scaling 101 + 61 s,
  smoke test about 10 s), within the 2 h cap.

## Anomalies and performance observations (reported, not fixed)

1. **Batching gives no gain.** `evaluate_batch` runs voxelization and GPU bands cell by cell; throughput is flat or
   falls slightly with B (best at B = 1-16, B = 64 3-11 % lower). Batching the GPU eigensolves across cells (or
   overlapping voxelization) is the likely speed-up; not tried.
2. **16 MKL threads is not the fastest here.** 8 threads beat 16 on the static n = 48 solve (1.94 vs 2.17 s) and on
   the Bloch n = 30 count (0.600 vs 0.658 s), single measurements. `_runtime.py` sets 16 by default (it was chosen
   against 32 on 2026-11-03). A larger test (n = 64, repeats) would be needed before changing the default.
3. **GPU dense Bloch runs out of memory at n = 30** (ndof 25,428; 19.4 GB allocated when it failed). `GPUBands`
   sizes chunks to about 6 GB but never below one k-point and has no memory guard. No production impact found: the
   search tier and `adversarial_ks` use n = 10.
4. `edge_extra_seconds` in the Bloch block is a timing field not listed in `tools.VOLATILE`; certificates compared
   with `strip_volatile` differ in it. Tool results do not carry it, so replay is unaffected.
5. **GPU memory held by the search tier**: 5-6 GB allocated but up to 23.4 GB reserved by the caching allocator (see section 1). Anything else on the GPU during a search would compete for it; the shared lock avoids this.
6. E4 tails: one search call took 755.7 s and one certificate 2440 s (older code); V3 and V4 maxima on the current
   checker are 80.0 s (search, budget 48) and 900.5 s (certificate).

## Files

`throughput.csv`, `latency.csv`, `cert_times.csv` (row level, 176 certificates), `cert_times_summary.csv`,
`scaling.csv`, `workflow.csv`, `T6_v4.csv`, `fig_v4_performance.png`; raw: `raw/throughput.jsonl`,
`raw/latency_calls.jsonl|csv`, `raw/scaling.jsonl`, `raw/cert_times_rows.csv`, `raw/workflow_rows.csv`,
`raw/e4_tool_calls.csv`, console logs; `latency_session/` (session log, 3 certificates, 6 exports).
Scripts: `scripts/verify/v4/{common,throughput,latency,scaling,reuse,tables,figure}.py`.
