# Week 4: tool contract, MCP server, replay, Codex probe on 5 briefs

Status (2026-11-05): gate "replay exact" **met**. 5 of 5 Codex sessions replay exactly without an LLM on the code
that wrote them (`C/summary.json`). Each replay re-runs every call, certificates included, and compares the full
results bit for bit, timing fields excepted. 5 of 5 decisions match the briefs' expected outcomes (section 4).

## 1. What was built

| Piece | File | Pattern |
|---|---|---|
| Tool contract, 14 tools | `amm/tools.py` | AgenticTO `agentto.tools`, new code |
| Session log + LLM-free replay | `amm/tools.py` (`Session.call`, `replay`) | same |
| MCP server (stdio), profiles B and C | `amm/mcp_server.py` | AgenticTO `agentto.mcp_server` |
| Subscription-only CLI runner | `amm/llm.py` | AgenticTO `agentto.llm.cli` |
| Briefs, deterministic clarification oracle, session runner | `amm/bench.py` | AgenticTO `agentto.bench.Oracle` |
| Probe | `bench/probe/P1-P5.json`, `scripts/probe/run_probe.py` | — |

Tools:
- spec: `set_material`, `set_constraints` (cell size, families), `set_target`, `set_source`;
- check: `check_bounds` (C only), `ask_clarification`;
- design: `list_families`, `evaluate`, `search`;
- release: `certify` (C only), `submit`;
- session: `undo`, `get_session`.

Profile B has no bounds and no certificates. In profile C, `submit(release)` needs a certificate with verdict
"certified" for that design and the current targets, computed in the same session. `export` (STL + report) and
`perturb` are not built yet; the as-built check runs inside `certify`.

Every call is validated (pydantic, extra keys rejected) and appended to `session.jsonl` with:
- `seq`, `actor`, `tool`, `args`, `ok`;
- `result` or `error`;
- `state_hash` and `result_hash`;
- clarification answers.

The session header records the hash of the `amm` sources. `replay` re-runs every call in a fresh session and
compares ok, state hash and the result with the timing fields removed. It reports `same_code` (a log is replayed
exactly only on the code that wrote it). Calls are serialized because the MCP client may send them concurrently.

Codex runs as `codex exec` with:
- user config ignored, a read-only sandbox, nothing persisted;
- exactly one MCP server (amm) with tools approved;
- gpt-6.1-sol at effort high, on the ChatGPT subscription (checked before every session; API keys are refused).

All five briefs get the same prompt (`amm/bench.PROMPT`).

## 2. Briefs (ground truth)

| Brief | Request (as the agent sees it) | Expected | Truth source |
|---|---|---|---|
| P1 | 316L, solid fraction ≤ 26 %, E100 ≥ 11.5 GPa, G ≥ 9.5 GPa | release | G2 cell schwarz_p sheet 0.25, certified true claim |
| P2 | 316L, 10 mm cell, complete gap 100-195 kHz | release | G2 cell cube_bars c 0.6 w 0.2, certified gap 99.7-199.4 kHz |
| P3 | Ti-6Al-4V, solid fraction ≤ 20 %, E100 ≥ 35 GPa | refuse, PROVEN_INFEASIBLE | Voigt: E ≤ 0.2 × 113.8 = 22.8 GPa |
| P4 | P1 without the material | ask, then release | material missing (needed to normalize GPa and for nu_s) |
| P5 | 316L, 10 mm cell, complete gap 140-375 kHz | refuse, NOT_FOUND_IN_FAMILIES | 26 % wider than any atlas gap at f* 0.85 (not a proof) |

## 3. Three probe rounds and what each found

**Round 0 (`C_v0_nondeterministic/`): replay was not exact.** Two sources of non-determinism:
1. **GPU search tier.** The band assembly used `index_add_`, whose CUDA atomics add in a run-dependent order.
   With complex64 this moved low band edges by up to 5e-4 relative, for example f_lo 0.17688 vs 0.17696 for the
   same design. Fix: a fixed-order gather-sum (`bloch.GPUBands`). The result is now bit-identical across runs,
   batch compositions and processes (`tests/test_determinism.py`).
2. **CPU PARDISO.** Threaded factorization differed in the last bits between processes (E100 hex
   ...6932 / ...6909 / ...6930). Fix: MKL conditional numerical reproducibility, `MKL_CBWR=AUTO,STRICT`, set by
   `amm/__init__` and the launchers, and checked (`amm.MKL_CBWR_STATUS`). Cost: about 4 % on a static solve
   (4.09-4.17 s → 4.24-4.36 s at n = 48).
3. ARPACK's random start vector (gap-edge Lanczos) depends on the process's call history, so it is now fixed.

The atlas was computed before fix 1. Its values carry the old assembly's float32 noise (≤ 5e-4 on low band
edges), well inside the calibrated search-tier error.

**Round 1 (`C_v1_before_gap_fixes/`): 4 replays exact, and P2 refused a feasible request.** Two tool bugs:
1. `evaluate` returned no gaps. It dropped the band array that `atlas.row_gaps` needs, so the agent's follow-up
   evaluations all showed "no gap".
2. The static block required every static quantity to converge, even those without a target. For the gap-only
   P2, the certificate climbed the whole static ladder (750 s) and ended "undetermined" on untargeted
   quantities. The agent then refused (UNDETERMINED), although the gap block had certified the gap.
   Fix: convergence is required only for the targeted quantities.
   - Effect on G2 (saved solves re-scored): 3 cells had a rung blocked only by untargeted bulk modulus.
   - gyroid sheet 0.15 would certify one rung earlier; its claim is true and no bound lies beyond every limit
     estimate.
   - The two octet cells are unchanged: their targets still lie inside the band at that rung.
   - G2 still has 0 false certifications.

Also fixed: UTF-8 stdio in the MCP server, and calls serialized (P4 had a `get_session` running while `certify`
was still in progress).

**Round 2 (`C/`, final code): 5 of 5 replays exact.** Table in section 4.

## 4. Final probe (round 2)

| Brief | Expected | Decision (verdict / design) | Asked | Tool calls (failed) | Certify calls | Search objective | Replay exact (same code) | Session wall | Input tokens (cached) | Output tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | release | release / schwarz_p {"density": 0.255, "mode": "sheet"} | 0 | 14 (0) | 2: undetermined, certified | pess | True (True) | 836 s | 2,135,123 (2,066,816) | 4,836 |
| P2 | release | release / sphere_ligaments {"c": 0.393746, "w": 0.061183} | 0 | 13 (1) | 1: certified | expected | True (True) | 748 s | 1,996,553 (1,940,352) | 3,053 |
| P3 | refuse / PROVEN_INFEASIBLE | refuse / PROVEN_INFEASIBLE | 0 | 4 (0) | 0: – | – | True (True) | 34 s | 101,378 (85,376) | 369 |
| P4 | ask_then_release | release / schwarz_p {"density": 0.255, "mode": "sheet"} | 1 | 15 (0) | 2: undetermined, certified | pess | True (True) | 868 s | 2,409,947 (2,341,632) | 4,577 |
| P5 | refuse / NOT_FOUND_IN_FAMILIES | refuse / NOT_FOUND_IN_FAMILIES | 0 | 12 (1) | 0: – | expected | True (True) | 116 s | 384,964 (362,752) | 935 |

- All 5 decisions match the expected outcome:
  - 3 releases of certified designs;
  - a refusal with PROVEN_INFEASIBLE (Voigt bound, named in the submission);
  - a refusal with NOT_FOUND_IN_FAMILIES, which the agent's note says is not a proof;
  - P4 asked for the material, and the oracle chose 316L.
- The released P2 design (sphere_ligaments c 0.394 w 0.061) is near the thin edge of the calibrated domain
  (w ≥ 0.06). It is certified all the same: the certificate does not use the search-tier calibration.
- Failed calls were argument errors the tool rejected (search budget 100 > 96), and the agent corrected them.

## 5. Agent behaviour worth noting for week 5

- **Objective choice:** in the final round, the agent picked the search objective "pess" in 2 of the 4 sessions
  that searched (P1, P4) and "expected" in the other 2. In rounds 0-1 it was almost always "pess". The tool
  description says "expected" is the best estimate. Pessimistic searches still produced designs that certified.
- **Certification at the boundary:** asked for density ≤ 0.26, the agent first certified density 0.26 itself
  ("undetermined": the guarded density upper bound sits above 0.26). It then backed off to 0.255-0.259, which
  certified. Two certificates per feasible static brief cost about 10 minutes.
- **Questions:** P4 asked about the material, as it should. In round 1, P1 asked about the cell size, which a
  static brief does not need; the oracle answered "free". The week-5 question-rate metric must count both kinds.
- **Encoding:** free-text notes with an en dash arrive mis-encoded ("100â€“195"). The bytes are already wrong in
  Codex's own output, so this is cosmetic and touches only free-text fields. Numeric arguments are unaffected.
- **Robustness:** P2's released design is robust to a 0.01 a as-built offset (`robust = true`); the P1 and P4
  releases are not. (Corrected 2026-11-06 after the audit, `results/audit/week5_2026-11-06/report.md` F12; this
  line first said "no released design is robust".)

## 6. Cost

Final round, 5 sessions:
- 43 min of session wall time; 33 min of it in `certify`;
- 36 min of replay;
- 7,027,965 input tokens (6,796,928 cached, 97 %) and 13,770
  output tokens, on the ChatGPT subscription.

All three rounds: 14 Codex sessions (round 0: 4, one of them interrupted; round 1: 5; round 2: 5).
