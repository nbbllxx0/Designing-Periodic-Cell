# Forward-solver comparison: amm against DOLFINx-MPC (V1c) and the V1b two-sided checks

Built by `scripts/verify/v3/forward_table.py` from existing files only (`results/verification/dolfinx/`,
`results/verification/v1b/`); nothing was rerun. Protocols, deviations and caveats: the NOTES.md of each
folder. DOLFINx 0.11.0 + dolfinx_mpc 0.11.0 (complex PETSc, MUMPS, 8 MPI ranks in a container) is the
third-party code; V1b's Q2-FCM is the author's own second code and scikit-fem 12.0.2 shares its geometry
evaluator (semi-independent).

## A. Bloch band edges (8 cells, 16 edges; third party)

Accuracy. ref = DOLFINx extrapolated edge +- 2u (three finest levels). amm safe = the certificate's
guarded edge. c = amm's margin (safe edge inside the reference gap; positive = conservative). raw n40 =
amm's finest raw edge relative to the reference (positive = above). Identity = largest relative frequency
difference between DOLFINx Q1 midpoint-rule and amm's same discrete model (n = 20, 6 k, bands 1..nb+4).

| Case | model | ref lo +- 2u | amm safe lo | c_lo (/2u) | ref hi +- 2u | amm safe hi | c_hi (/2u) | verdict lo/hi | raw n40 lo/hi | identity |
|---|---|---|---|---|---|---|---|---|---|---|
| cb_c0.6_w0.2_nu0.342 | exact | 0.3191 +- 0.0034 | 0.3324 | 0.0133 (3.9) | 0.6995 +- 0.0068 | 0.68 | 0.0195 (2.9) | sound / sound | +1.1 % / +1.5 % | 2.6e-12 |
| cb_c0.8_w0.3_nu0.3 | exact | 0.4156 +- 0.0036 | 0.4383 | 0.0228 (6.4) | 0.602 +- 0.0013 | 0.5988 | 0.00325 (2.5) | sound / sound | +1.0 % / +0.3 % | 3.4e-13 |
| cb_c0.5_w0.2_nu0.3 | exact | 0.3584 +- 0.00069 | 0.3796 | 0.0212 (30.7) | 0.5653 +- 0.0064 | 0.5531 | 0.0123 (1.9) | sound / sound | +0.8 % / +1.8 % | 1.4e-12 |
| cb_c0.6_w0.3_nu0.3 | exact | 0.5262 +- 0.0045 | 0.5543 | 0.0282 (6.2) | 0.6827 +- 0.0029 | 0.6772 | 0.00554 (1.9) | sound / sound | +1.3 % / +0.9 % | 4.1e-13 |
| cb_c0.7_w0.3_nu0.3 | exact | 0.4543 +- 0.0062 | 0.4984 | 0.0441 (7.1) | 0.6959 +- 0.0025 | 0.6824 | 0.0134 (5.3) | sound / sound | +1.7 % / +0.6 % | 3.4e-13 |
| tpms_schwarzp_d0.25_nu0.3 | fcm | 0.4646 +- 0.0019 | 0.4799 | 0.0153 (8.1) | 0.8315 +- 0.0017 | 0.8279 | 0.00365 (2.1) | sound / sound | +0.8 % / +0.2 % | 1.6e-12 |
| strut_bcc_R0.27_r0.06_nu0.342 | fcm | 0.3497 +- 0.0042 | 0.3677 | 0.018 (4.2) | 0.7712 +- 0.021 | 0.6015 | 0.17 (8.2) | sound / sound | +1.0 % / +1.6 % | 1.9e-09 |
| thin_sl_c0.402_w0.061_nu0.3 | fcm | 0.1091 +- 0.015 | 0.1206 | 0.0115 (0.8) | 0.9707 +- 0.00032 | 0.9512 | 0.0195 (61.4) | marginal / sound | +1.5 % / +0.3 % | 1.0e-10 |

Edges: 15 sound, 1 marginal, 0 unsound (of 16).

Runtime. DOLFINx: Q2 at n = 20 (8 ranks; seconds for the level's k-set and per k), and the Q1 identity
model (6 k). amm: the same identity model (6 k; host-side block subspace iteration of the V1c harness, CPU,
not amm's production eigen path), amm's certificate model at DOLFINx's k (n = 20, CPU), and the wall time
of the whole certificate Bloch block (n = 20, 30, edge level 40, 2 grid phases, adversarial k search;
GPU + CPU) from the source certificate.

| Case | DOLFINx Q2 n20: dof, k, s (s/k) | DOLFINx Q1-id n20: dof, s / 6 k | amm id n20: dof, s / 6 k | amm cert model n20 at S_dfx: dof, k, s | amm certificate Bloch block s | DOLFINx k search s |
|---|---|---|---|---|---|---|
| cb_c0.6_w0.2_nu0.342 | 57810, 6, 97 (16.2) | 8166, 5.6 | 8166, 101.8 | 8166, 6, 176 | 265.4 | 427 |
| cb_c0.8_w0.3_nu0.3 | 118458, 6, 537 (89.5) | 16062, 21.8 | 16062, 783.7 | 16062, 6, 489 | 621.5 | 605 |
| cb_c0.5_w0.2_nu0.3 | 41634, 7, 57 (8.2) | 6018, 4.3 | 6018, 49.1 | 6018, 6, 73 | 144.4 | 244 |
| cb_c0.6_w0.3_nu0.3 | 69690, 6, 166 (27.8) | 9678, 6.4 | 9678, 186.1 | 9678, 6, 389 | 291 | 685 |
| cb_c0.7_w0.3_nu0.3 | 89898, 6, 190 (31.7) | 12330, 9.9 | 12330, 359.8 | 12330, 6, 369 | 467.7 | 866 |
| tpms_schwarzp_d0.25_nu0.3 | 70098, 43, 842 (19.6) | 9918, 6.2 | 9918, 264.1 | 9918, 6, 347 | 330.9 | 1311 |
| strut_bcc_R0.27_r0.06_nu0.342 | 66846, 43, 956 (22.2) | 9798, 8.5 | 9798, 430.6 | 9798, 6, 466 | 318 | 2637 |
| thin_sl_c0.402_w0.061_nu0.3 | 74250, 41, 1005 (24.5) | 10446, 21.2 | 10446, 313.4 | 10446, 4, 152 | 392.4 | 533 |

Sums over the 8 cells: DOLFINx Q2 n20 3850 s, DOLFINx Q1-id 84 s, amm id 2489 s, amm cert model at S_dfx 2461 s, amm certificate Bloch blocks 2831 s, DOLFINx k searches 7308 s. V1c totals (its NOTES.md): DOLFINx about 5.7 h of container compute (8 cores), amm side about 3.6 h.

Reading the runtime columns: the DOLFINx and amm timings are not a like-for-like speed test. DOLFINx runs
Q2 (about 7x the unknowns of amm's hex8i at the same n) on 8 MPI ranks; the amm identity timing uses the V1c
harness's eigen solver; amm's production paths are the GPU dense search tier (about 1 s per cell for static
+ bands, V3 runs.csv) and the certificate's inertia-count Lanczos. The table states what each run cost, not
a speed ratio of the two codes.

## B. Homogenized stiffness (V1b; own Q2-FCM reference and scikit-fem, semi-independent)

delta = amm's extrapolated estimate relative to the Q2-FCM reference; bounds = soundness of amm's guarded
lower / upper bound against the reference +- 2u; scikit-fem = its n = 16 value relative to the reference.

| Cell | quantity | ref | amm est. | delta | lower / upper | scikit-fem delta |
|---|---|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | E100 | 0.07096 | 0.07082 | -0.20 % | sound / sound | +0.21 % |
| tpms_schwarzp_d0.25_nu0.3 | G | 0.01015 | 0.0101 | -0.51 % | sound / sound | +0.45 % |
| tpms_schwarzp_d0.25_nu0.3 | bulk | 0.02663 | 0.02657 | -0.23 % | sound / sound | +0.23 % |
| tpms_schwarzp_d0.25_nu0.3 | nu100 | 0.05586 | 0.05571 | -0.01 % | sound / sound | +0.01 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | E100 | 0.08272 | 0.08221 | -0.62 % | sound / sound | -0.30 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | G | 0.061 | 0.06091 | -0.15 % | sound / sound | -0.30 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | bulk | 0.1064 | 0.1063 | -0.10 % | sound / sound | -0.29 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | nu100 | 0.3704 | 0.3715 | +0.11 % | sound / sound | +0.00 % |
| strut_bcc_R0.27_r0.06_nu0.342 | E100 | 0.004982 | 0.004732 | -5.01 % | sound / sound | +8.82 % |
| strut_bcc_R0.27_r0.06_nu0.342 | G | 0.01605 | 0.01586 | -1.16 % | sound / sound | +1.34 % |
| strut_bcc_R0.27_r0.06_nu0.342 | bulk | 0.01705 | 0.01687 | -1.05 % | sound / sound | +1.16 % |
| strut_bcc_R0.27_r0.06_nu0.342 | nu100 | 0.4513 | 0.4534 | +0.21 % | sound / sound | -0.37 % |
| strut_octet_r0.06_nu0.3 | E100 | 0.02762 | 0.02727 | -1.28 % | sound / sound | +6.88 % |
| strut_octet_r0.06_nu0.3 | G | 0.01875 | 0.01841 | -1.82 % | sound / sound | +6.00 % |
| strut_octet_r0.06_nu0.3 | bulk | 0.0269 | 0.0264 | -1.86 % | sound / sound | +7.09 % |
| strut_octet_r0.06_nu0.3 | nu100 | 0.3288 | 0.3287 | -0.01 % | marginal / marginal | +0.04 % |
| thin_sl_c0.402_w0.061_nu0.3 | E100 | 0.01073 | 0.01093 | +1.90 % | sound / sound | -2.08 % |
| thin_sl_c0.402_w0.061_nu0.3 | G | 0.0003267 | 0.00023 | -29.60 % | sound / sound | +16.00 % |
| thin_sl_c0.402_w0.061_nu0.3 | bulk | 0.003638 | 0.003708 | +1.94 % | sound / sound | -2.12 % |
| thin_sl_c0.402_w0.061_nu0.3 | nu100 | 0.008545 | 0.00871 | +0.02 % | sound / sound | -0.02 % |
| thin_sl_c0.357_w0.109_nu0.3 | E100 | 0.02176 | 0.02182 | +0.28 % | sound / sound | +1.24 % |
| thin_sl_c0.357_w0.109_nu0.3 | G | 0.0008374 | 0.000809 | -3.39 % | sound / sound | +12.09 % |
| thin_sl_c0.357_w0.109_nu0.3 | bulk | 0.007543 | 0.007565 | +0.29 % | sound / sound | +1.26 % |
| thin_sl_c0.357_w0.109_nu0.3 | nu100 | 0.0193 | 0.01934 | +0.00 % | sound / sound | +0.01 % |

Static bounds: 46 sound, 2 marginal, 0 unsound (of 48); |delta| median 0.51 %, max 29.60 %. V1b compute: 8.4 solver-hours (its NOTES.md).
