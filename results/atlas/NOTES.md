# Week 3: family atlas (E2) and the `search` tool

Status (2026-11-04): the atlas is complete at nu_s = 0.3, 0.342 and 0.39 (3 × 2,722 cells), so the gate "feasibility
map complete" is met. The oracle and
search pass their gate checks (section 5). 4 of 5 designs the search found pass the full certificate (section 6). All values in the atlas are
**search-tier values, not certificates**.

Code: `amm/atlas.py` (grid, error model, slacks, oracle), `amm/search.py` (BoTorch search). Scripts:
`scripts/atlas/` (`run_atlas.py`, `queue_nu.sh`, `calibrate.py`, `extend_calibration.py`, `plot_map.py`,
`gate.py`). BoTorch 0.14.0, GPyTorch 1.14, PyTorch 2.5.1+cu124 (installed into the `amm` env with pip).

## 1. Grid

| Family | Kinds | Parameters (box) | Cells per kind |
|---|---|---|---|
| TPMS | gyroid, schwarz_p, diamond, iwp × sheet / network | density 0.06–0.60 | 56 (28 per mode) |
| Struts | sc, bcc, octet | strut radius r 0.04–0.15, node-sphere R 0 or r + 0.03 … 0.32 | 465 |
| Resonators | cube_bars | core c 0.30–0.86, bar w 0.06–0.36, w ≤ c − 0.04 | 554 |
| Resonators | sphere_ligaments | core c 0.12–0.46, ligament w 0.06–0.34, w ≤ 2c − 0.02 | 549 |

There are 2,722 cells per Poisson ratio, on a 28 × 24 grid per 2-D box (`atlas.grid_specs`). The plan said
"20k per family". The grid is denser than the search tier's error, so a finer grid would not tell more. The
`search` tool fills in between grid points.

Search tier (`atlas.SEARCH_TIER`): static n = 20, Bloch n = 10, 4 points per k-path leg, 24 eigenvalues. It
takes 0.92 s per cell at nu = 0.3 alone, and 1.57 s per cell at nu = 0.39 while gate searches ran at the same time.

Valid cells at nu = 0.3 (with a gap of relative width ≥ 2 %): gyroid 56 (0), schwarz_p 48 (11), diamond 54 (0),
iwp 54 (0), sc 465 (222), bcc 465 (192), octet 465 (0), cube_bars 554 (414), sphere_ligaments 549 (380).
Invalid means not connected or not percolating. Network TPMS do not percolate below density about 0.10 (Schwarz P
network below about 0.15). This holds at n = 48 too (section 3), so it is real and not a search-tier artefact.

Maps: `feasibility_map_nu0.3.png/.pdf`, `..._nu0.342...` and `..._nu0.39...`:
- (a) E100 vs solid fraction, with the Voigt bound and the isotropic Hashin–Shtrikman bound;
- (b) G vs solid fraction;
- (c) widest gap vs E100 (the stiffness–gap trade-off);
- (d) gap mid-frequency vs relative width.

## 2. Search-tier error model

References are the converged values:
- the 50 G2 cells (classification_v3 brackets);
- 11 held-out phase-ladder cells (static only);
- 12 usable new thin-end cells: static phase means at n = 48/64/80, gap edges by Lanczos at n = 30/40/50, with
  the trial frequency checked by inertia counts at every reference k.

Script: `extend_calibration.py`. 73 cells in total. A gap reference is skipped if its edges jump by more than
25 % of the mid-frequency between n = 30 and n = 40. One cell was skipped (cube_bars c 0.5 w 0.08: its lower edge moves from 0.16 to 0.43).

The error is **one-sided** for E100, G, bulk and both gap edges: the search tier is always higher (coarse voxels
are too stiff). The model is true = search / (1 + e), with e in [0, 1.25 × max seen]. Density and nu100 use a
symmetric range. There are two bins per family. A cell is "thin" when its smallest feature is below 0.15
(TPMS density), 0.06 (strut r) or 0.10 (resonator w).

| Family (regular bin) | E100 median / max e | G median / max e | n (static) |
|---|---|---|---|
| TPMS | 0.025 / 0.18 | 0.036 / 0.20 | 36 |
| Struts | 0.12 / 0.57 | 0.078 / 0.44 | 27 |
| Resonators | 0.042 / 0.10 | 0.18 / 0.50 | 37 |

Max e includes the 1.25 safety factor. Thin bins are wider (struts E100 to 0.92, resonator G to 1.39).

Gap edges: the search tier puts both edges about 10 % too high:
- lower edge: median e 0.10–0.11, range to 0.28;
- upper edge: median 0.11–0.17, range to 0.72 (1.22 thin).

These ranges are pooled over families, because only 1 TPMS and 1 strut gap reference exist in the regular bin.
**The gap ranges are wide and rest on few cells (13 regular, 19–32 with thin).** A pessimistic gap claim is
therefore rarely possible at the search tier, and the certificate must decide.

Domain: the verdicts are restricted to the calibrated range of each feature size: TPMS density ≥ 0.08, strut
r ≥ 0.04, resonator w ≥ 0.06 (`atlas.error_domain`). Atlas cells outside the domain are reported, not used.

## 3. Percolation at the thin end

Of the 16 thin specs, these do not percolate at n = 48:
- schwarz_p, diamond and iwp network at density 0.08;
- iwp network at 0.10 (fails at phase 0.5).

The search tier calls them invalid too, so the atlas has no false positives there.

## 4. Oracle and search

Slack for a minimum target is (q − t)/|t|, and for a maximum target (t − q)/|t|. Gap slack is the best over the
cell's gaps of min(f_lo − edge_lo, edge_hi − f_hi)/f_mid. An invalid cell, or one with no gap, scores −1. The
overall slack is the minimum over constraints. Cases:
- nominal: raw values;
- expected: corrected by the median e;
- pess: worst end of the e range;
- opt: best end of the e range.

Oracle verdicts (`atlas.oracle`):
- **FEASIBLE**: some cell has pess slack > 0.
- **NOT_FOUND_IN_FAMILIES**: every cell has opt slack ≤ 0, and the grid-interpolated opt slack is ≤ 0 too
  (linear in 1-D, bilinear on complete 2-D squares). The interpolation was added after the grid spacing alone
  produced a NOT_FOUND on a true claim (schwarz_p sheet 0.15).
- **BORDERLINE**: everything else.

NOT_FOUND means "not found in these families at this resolution". It is not a proof of impossibility.

Search (`search.search`):
- One arm per kind (TPMS: kind × mode). Atlas rows seed a SingleTaskGP per arm, and the 3 best arms by seed slack
  are searched.
- qLogEI over 1,024 Sobol candidates filtered by the validity rules, q = 8 per round, evaluated as one batch.
- The default objective is **expected**. The worst-case objective could not meet 5 %-margin claims at all,
  because the pess ranges are wider than the margin. With it, the search found 4 of 14 true claims; even the
  source cells score −9 % to −23 % that way.
- The pessimistic slack is still reported for every design (`found_pessimistic`).

## 5. Gate checks 1–4 (`gate.json`)

1. **Completeness:** 2,722/2,722 cells at each of nu = 0.3, 0.342 and 0.39. Valid counts are the same at all three;
   gap counts change by at most 12 per kind (sc 222 / 216 / 212, bcc 192 / 189 / 180).
2. **Oracle against G2 truth** (50 claims):

   | Truth | FEASIBLE | BORDERLINE | NOT_FOUND |
   |---|---|---|---|
   | true | 14 | 27 | 0 |
   | false | 0 | 4 | 0 |
   | undetermined | 0 | 5 | 0 |

   No true claim is called NOT_FOUND, and no false claim is called FEASIBLE. Most claims are BORDERLINE because
   they were built with a 5 % margin, which is inside the error ranges.

3. **Search on 14 true G2 claims** (all 4 gap claims and every 4th static claim; budget 32; expected objective):
   - found 13 of 14 (all 10 static claims, 3 of 4 gap claims);
   - the miss is schwarz_p network 0.25 with a gap: best expected slack −0.005 at density 0.2495, next to the
     source cell;
   - 5 of the 13 designs are from another kind than the source, for example a sphere-ligament resonator for a
     cube_bars claim, or gyroid sheet 0.14 for an octet claim;
   - only 1 design (sphere_ligaments c 0.21 w 0.18) also clears its claim pessimistically;
   - median time 64 s per search (39–116 s, plus one stalled run, below).

   **Caveat:** the median corrections come partly from the same 50 G2 cells, so this check is not held out.

4. **Beyond the envelope** (5 constructed targets):
   - E100 at 1.3 × the atlas maximum, at density caps 0.15 / 0.3 / 0.45;
   - a gap 1.3 × wider than any atlas gap at mid-frequency 0.75 and 0.85.

   The oracle calls all 5 NOT_FOUND_IN_FAMILIES. The search, with the optimistic objective, finds none of them
   either (best opt slack −0.02 to −0.16).

Timing incident: one search took 4,953 s instead of about 100 s. In the same window, the nu = 0.342 atlas ran at
154 s per cell. Windows logged Kernel-Power session events at 16:27 and 18:26, so the cause was most likely
standby while no turn was running. The cause is not proven. The app now keeps the PC awake across turns.

## 6. Search → certificate (gate step 5)

The first 2 gap designs and the first 3 static designs found in step 3 were put through the full certificate
(`certify.certify`, default ladders, as-built ±0.01). Targets are the G2 claims (5 % margin).

| Design (search result) | Claim source | Certificate | Static | Gap | Time |
|---|---|---|---|---|---|
| sphere_ligaments c 0.297 w 0.145 | sphere_ligaments c 0.3 w 0.15, with gap | **fails** | fails | fails | 753 s |
| cube_bars c 0.591 w 0.194 | cube_bars c 0.6 w 0.2, with gap | passes | passes | passes | 762 s |
| sphere_ligaments c 0.205 w 0.201 | sphere_ligaments c 0.2 w 0.2 | passes | passes | – | 104 s |
| schwarz_p sheet 0.252 | schwarz_p sheet 0.25 | passes | passes | – | 174 s |
| sphere_ligaments c 0.209 w 0.243 | cube_bars c 0.4 w 0.2 | passes | passes | – | 60 s |

**4 of 5 found designs certify**, including one gap design and one design from another kind than the claim's
source. No design is robust: the as-built check (±0.01 offset) fails on every one. A 5 % claim margin is smaller
than the effect of a 0.01 offset.

The failed design misses narrowly on both blocks:
- Static: the guarded lower E100 is 0.02759 against a target of 0.02798 (1.4 % short), and G is 10 % short.
  Its expected slack at the search tier was +1.6 %, inside the certificate's guard band.
- Gap (rerun with `scripts/atlas/bloch_diag.py`, saved in `certs/bloch_<hash>.json`):
  - Every resolution passes the inertia checks.
  - The upper edge converges from above: 0.670, 0.645, 0.633 at n = 20 / 30 / 40, extrapolated 0.604.
  - With safety factor 2, the certified upper edge is 0.544, below the claimed f_hi of 0.582. So the gap is
    probably real but cannot be certified at these resolutions.
  - This is the same kind of guard-band refusal as the G2 false alarms. The design is refused, not wrongly
    accepted.

Lesson for the benchmark: a search tool that aims at expected slack just above 0 hands the certificate designs
inside its guard band. Week 4/5 should ask for a margin (for example expected slack ≥ 3 %) before certifying.
From now on, `gate.py` step 5 saves every full certificate to `results/atlas/certs/`.

## 7. What is not done

- A held-out test of the expected objective (medians fitted on other cells).
- A margin option in `search` so that found designs clear the certificate's guard band.
- More gap references for TPMS and struts (one each in the regular bin).
- Calibration at nu = 0.342 and 0.39: the error model was fitted at nu = 0.3 only and is reused there.
