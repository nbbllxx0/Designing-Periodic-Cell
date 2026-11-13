# E4 confirmatory result (amendment A2), 2026-11-07

Source: `analysis_A2.json` (from `e4.py analyze --tag e4 --amended A2`), `scores.json`, `scores_meta.json`
(234 jobs scored at 11:43 with the frozen checker f2e482d81382b400, releases certified). Codex gpt-6.1-sol, high,
repeat 1, confirmatory partition, 78 briefs per arm. Units are specs (54 with a witnessed or proven truth level).
No quota events (`amendments/quota_check.json`); no phase-1 job was interrupted (one pre-A1 interruption was rerun).

Arms (plan/E4_PREREG.md): D = LLM alone; B = spec tools + evaluate/search/atlas + submit; C = B + check_bounds + certify.

## Primary (H1): correct on decided briefs (witnessed + proven), C minus B
| | C | B | diff | 95% CI (cluster bootstrap) | specs C better / B better | p (sign-flip, 1e5 draws) |
|---|---|---|---|---|---|---|
| correct | 0.917 | 0.426 | **+0.491** | [0.361, 0.620] | 29 / 0 | < 1e-4 (floor of the test) |

## Secondary (Holm-adjusted)
| test | a | b | diff | 95% CI | p_holm |
|---|---|---|---|---|---|
| unsupported releases B - C | 0 | 0 | 0 | [0, 0] | 1.0 |
| false refusals B - C (witnessed) | 0.738 | 0.107 | +0.631 | [0.500, 0.762] | 5e-5 |
| overclaim B - C (unresolved) | 0.143 | 0 | +0.143 | [0, 0.429] | 1.0 (7 specs) |
| correct C - D | 0.917 | 0.167 | +0.750 | [0.639, 0.852] | 5e-5 |
| resolved ambiguous C - B | 1.0 | 1.0 | 0 | [0, 0] | 1.0 |

## Outcome counts per arm (78 briefs each)
| outcome | D | B | C |
|---|---|---|---|
| success (released, certificate holds) | 0 | 15 | 52 |
| correct refusal (proven infeasible) | 9 | 12 | 12 |
| false refusal (feasible, witnessed) | 55 | 43 | 6 |
| abstention | 7 | 6 | 8 |
| overclaim | 1 | 1 | 0 |
| no answer | 6 | 1 | 0 |
| unsupported release | 0 | 0 | 0 |

## Reading (for the paper)
- The gain of C over B comes almost entirely from **fewer false refusals** on feasible targets (43 -> 6), not from
  blocking unsafe releases: no arm released a design whose certificate failed. Without `certify`/`check_bounds`,
  the agent mostly declined to release designs it could not verify. This changes the S-claim wording: the
  certificate tools are what let the agent *commit* to feasible designs, rather than a guard against bad ones.
- Unresolved briefs (8 per arm): none is scored correct in any arm. C abstained on all 8; B abstained on 6, overclaimed 1, gave no answer on 1; D abstained on 7, overclaimed 1.
- Limits: one Codex repeat (A1/A2), so repeat-level reliability is not estimable; no Claude replication; no arm-O
  reference (cut by A2). p is at the resolution floor of a 1e5-draw permutation test.
