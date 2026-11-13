### Static (Q2-FCM reference from the three finest levels; delta = (amm estimate - R)/R)

| cell | Q | R +- 2u | amm est. | delta | amm [lower, upper] | lower | upper | consistent | scikit-fem n16 (per.) | KUBC >= lower |
|---|---|---|---|---|---|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | E100 | 0.070962 +- 7.4e-05 | 0.07082 | -0.20 % | [0.069995, 0.071741] | sound | sound | True | +0.21 % DIFF | True |
| tpms_schwarzp_d0.25_nu0.3 | G | 0.010152 +- 3.2e-05 | 0.0101 | -0.51 % | [0.0098313, 0.010416] | sound | sound | True | +0.45 % ok | True |
| tpms_schwarzp_d0.25_nu0.3 | bulk | 0.026629 +- 3.1e-05 | 0.026567 | -0.23 % | [0.026211, 0.026964] | sound | sound | True | +0.23 % DIFF | True |
| tpms_schwarzp_d0.25_nu0.3 | density | 0.24993 +- 0.0001 | 0.25 | +0.03 % | [0.24995, 0.25001] | marginal | marginal | True | n/a | n/a |
| tpms_schwarzp_d0.25_nu0.3 | nu100 | 0.055863 +- 5.6e-05 | 0.055714 | -0.01 % | [0.054945, 0.05657] | sound | sound | True | +0.01 % ok | n/a |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | E100 | 0.082722 +- 5.2e-05 | 0.082209 | -0.62 % | [0.080499, 0.083943] | sound | sound | True | -0.30 % ok | True |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | G | 0.061002 +- 2.4e-05 | 0.06091 | -0.15 % | [0.060582, 0.061285] | sound | sound | True | -0.30 % ok | True |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | bulk | 0.10638 +- 4.3e-05 | 0.10627 | -0.10 % | [0.10598, 0.10663] | sound | sound | True | -0.29 % ok | True |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | density | 0.28944 +- 0.00012 | 0.2895 | +0.02 % | [0.28941, 0.28953] | marginal | marginal | True | n/a | n/a |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | nu100 | 0.37039 +- 0.00015 | 0.37153 | +0.11 % | [0.36829, 0.37477] | sound | sound | True | +0.00 % ok | n/a |
| strut_bcc_R0.27_r0.06_nu0.342 | E100 | 0.0049819 +- 0.00024 | 0.0047324 | -5.01 % | [0.003647, 0.0058398] | sound | sound | True | +8.82 % ok | True |
| strut_bcc_R0.27_r0.06_nu0.342 | G | 0.01605 +- 0.00029 | 0.015865 | -1.16 % | [0.014942, 0.016787] | sound | sound | True | +1.34 % ok | True |
| strut_bcc_R0.27_r0.06_nu0.342 | bulk | 0.01705 +- 0.00031 | 0.01687 | -1.05 % | [0.015937, 0.017804] | sound | sound | True | +1.16 % ok | True |
| strut_bcc_R0.27_r0.06_nu0.342 | density | 0.19501 +- 7.8e-05 | 0.19511 | +0.05 % | [0.19503, 0.19514] | marginal | sound | False | n/a | n/a |
| strut_bcc_R0.27_r0.06_nu0.342 | nu100 | 0.45134 +- 0.0015 | 0.45343 | +0.21 % | [0.44509, 0.4617] | sound | sound | True | -0.37 % DIFF | n/a |
| strut_octet_r0.06_nu0.3 | E100 | 0.02762 +- 0.00052 | 0.027266 | -1.28 % | [0.026089, 0.028442] | sound | sound | True | +6.88 % ok | True |
| strut_octet_r0.06_nu0.3 | G | 0.018753 +- 0.00025 | 0.018412 | -1.82 % | [0.017571, 0.019253] | sound | sound | True | +6.00 % ok | True |
| strut_octet_r0.06_nu0.3 | bulk | 0.026898 +- 0.00062 | 0.026399 | -1.86 % | [0.025005, 0.027793] | sound | sound | True | +7.09 % ok | True |
| strut_octet_r0.06_nu0.3 | density | 0.15853 +- 0.00014 | 0.15819 | -0.21 % | [0.15755, 0.15884] | sound | sound | True | n/a | n/a |
| strut_octet_r0.06_nu0.3 | nu100 | 0.3288 +- 0.00085 | 0.32867 | -0.01 % | [0.32819, 0.32915] | marginal | marginal | True | +0.04 % ok | n/a |
| thin_sl_c0.402_w0.061_nu0.3 | E100 | 0.010727 +- 0.00026 | 0.010931 | +1.90 % | [0.010332, 0.012055] | sound | sound | True | -2.08 % ok | True |
| thin_sl_c0.402_w0.061_nu0.3 | G | 0.00032667 +- 3.2e-05 | 0.00022997 | -29.60 % | [-4.0909e-05, 0.00058171] | sound | sound | True | +16.00 % ok | True |
| thin_sl_c0.402_w0.061_nu0.3 | bulk | 0.0036377 +- 8.9e-05 | 0.0037083 | +1.94 % | [0.0035016, 0.0040968] | sound | sound | True | -2.12 % ok | True |
| thin_sl_c0.402_w0.061_nu0.3 | density | 0.27391 +- 0.00011 | 0.27392 | +0.01 % | [0.27388, 0.27395] | marginal | marginal | True | n/a | n/a |
| thin_sl_c0.402_w0.061_nu0.3 | nu100 | 0.0085455 +- 0.00019 | 0.00871 | +0.02 % | [0.0082437, 0.009573] | sound | sound | True | -0.02 % ok | n/a |
| thin_sl_c0.357_w0.109_nu0.3 | E100 | 0.021755 +- 0.00011 | 0.021817 | +0.28 % | [0.021097, 0.022945] | sound | sound | True | +1.24 % ok | True |
| thin_sl_c0.357_w0.109_nu0.3 | G | 0.00083741 +- 1.5e-05 | 0.00080904 | -3.39 % | [0.00062394, 0.0010614] | sound | sound | True | +12.09 % ok | True |
| thin_sl_c0.357_w0.109_nu0.3 | bulk | 0.0075429 +- 4.1e-05 | 0.0075648 | +0.29 % | [0.007305, 0.0079721] | sound | sound | True | +1.26 % ok | True |
| thin_sl_c0.357_w0.109_nu0.3 | density | 0.19793 +- 7.9e-05 | 0.19796 | +0.02 % | [0.19788, 0.19802] | marginal | sound | True | n/a | n/a |
| thin_sl_c0.357_w0.109_nu0.3 | nu100 | 0.019297 +- 9e-05 | 0.019345 | +0.00 % | [0.018724, 0.020302] | sound | sound | True | +0.01 % ok | n/a |

### Gap edges (Q2-FCM reference over the refinement k subset; amm safe interval from the certificate)

| cell | nb | Q2 levels | R_lo +- 2u | R_hi +- 2u | amm ext (lo, hi) | delta ext | safe [s_lo, s_hi] | lo | hi | conservatism (lo, hi) | k coverage (dlo, dhi) | extreme k set (lo, hi) | band-index mismatch | earlier reference (levels: lo, hi) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | 6 | [12, 16, 20] | 0.46410 +- 4.9e-04 | 0.83183 +- 3.3e-04 | (0.46435, 0.83157) | (+0.05 %, -0.03 %) | (0.47988, 0.82789) | sound | sound | (+3.4 %, +0.5 %) | (0.0e+00, 0.0e+00) | amm_path, own_adversarial | 0 | - |
| strut_bcc_R0.27_r0.06_nu0.342 | 12 | [12, 16, 20] | 0.34182 +- 1.9e-02 | 0.75964 +- 3.0e-02 | (0.33882, 0.72279) | (-0.88 %, -4.85 %) | (0.36772, 0.60146) | sound | sound | (+7.6 %, +20.8 %) | (5.0e-16, 1.1e-16) | own_adversarial, own_adversarial | 0 | - |
| thin_sl_c0.402_w0.061_nu0.3 | 6 | [24, 28, 32] | 0.10599 +- 6.3e-03 | 0.96465 +- 1.4e-02 | (0.11068, 0.96621) | (+4.43 %, +0.16 %) | (0.12058, 0.95117) | sound | marginal | (+13.8 %, +1.4 %) | (5.6e-15, 2.4e-15) | amm_path, own_adversarial | 0 | [16, 20, 24]: marginal, sound |
| thin_sl_c0.357_w0.109_nu0.3 | 6 | [16, 20, 24] | 0.19185 +- 7.6e-03 | 0.88119 +- 4.2e-02 | (0.19112, 0.88129) | (-0.38 %, +0.01 %) | (0.20247, 0.82270) | sound | sound | (+5.5 %, +6.6 %) | (1.1e-15, 0.0e+00) | own_adversarial, own_adversarial | 0 | - |

### Per-k (gap cells)

| cell | sampled: amm n20 - Q2 n1, lo (% , min..max) | hi | extrapolated per-k max abs delta (lo, hi) | consistent |
|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | +1.09..+2.97 (45 k) | +0.32..+1.27 | (0.15 %, 0.02 %) | 9/9 |
| strut_bcc_R0.27_r0.06_nu0.342 | +1.21..+4.20 (45 k) | +4.26..+5.20 | (1.56 %, 5.15 %) | 8/8 |
| thin_sl_c0.402_w0.061_nu0.3 | -0.02..+6.14 (45 k) | +0.14..+0.57 | (30.62 %, 0.71 %) | 8/8 |
| thin_sl_c0.357_w0.109_nu0.3 | +0.38..+3.18 (45 k) | +2.60..+4.69 | (0.39 %, 0.06 %) | 8/8 |

### Claims (nominal and marginal)

| cell | claim | key | target | independent status | amm margin |
|---|---|---|---|---|---|
| tpms_schwarzp_d0.25_nu0.3 | nominal | density_max | 0.26249 | agrees | +4.75 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | E100_min | 0.0673345 | agrees | +3.95 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | G_min | 0.0096245 | agrees | +2.15 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | nu100_min | 0.0329762 | agrees | +66.62 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | nu100_max | 0.0785527 | agrees | +27.98 % |
| tpms_schwarzp_d0.25_nu0.3 | nominal | gap | 0.48215-0.78766 | agrees | lo +0.47 %, hi +4.86 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | nominal | G_min | 0.0572056 | agrees | +5.90 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | nominal | density_max | 0.29 | agrees | +0.16 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | marginal | G_min | 0.0605782 | agrees | +0.01 % |
| tpms_schwarzp_sheet_d0.2895_nu0.342 | marginal | density_max | 0.289526 | inconclusive | +0.00 % |
| strut_bcc_R0.27_r0.06_nu0.342 | nominal | G_min | 0.00407733 | agrees | +266.48 % |
| strut_bcc_R0.27_r0.06_nu0.342 | nominal | density_max | 0.21 | agrees | +7.08 % |
| strut_bcc_R0.27_r0.06_nu0.342 | marginal | G_min | 0.0149332 | agrees | +0.06 % |
| strut_bcc_R0.27_r0.06_nu0.342 | marginal | density_max | 0.195142 | agrees | +0.00 % |
| strut_bcc_R0.27_r0.06_nu0.342 | nominal | gap | 0.48874-0.55855 | agrees | lo +32.91 %, hi +7.13 % |
| strut_bcc_R0.27_r0.06_nu0.342 | marginal | gap | 0.37006-0.59912 | agrees | lo +0.64 %, hi +0.39 % |
| strut_octet_r0.06_nu0.3 | nominal | density_max | 0.165433 | agrees | +3.98 % |
| strut_octet_r0.06_nu0.3 | nominal | E100_min | 0.0256881 | agrees | +1.56 % |
| strut_octet_r0.06_nu0.3 | nominal | G_min | 0.0173976 | agrees | +0.99 % |
| strut_octet_r0.06_nu0.3 | nominal | nu100_min | 0.292097 | agrees | +12.36 % |
| strut_octet_r0.06_nu0.3 | nominal | nu100_max | 0.364949 | agrees | +9.81 % |
| thin_sl_c0.402_w0.061_nu0.3 | nominal | gap | 0.23144-0.63031 | agrees | lo +91.94 %, hi +33.73 % |
| thin_sl_c0.357_w0.109_nu0.3 | nominal | gap | 0.39158-0.44516 | agrees | lo +93.40 %, hi +45.89 % |
| thin_sl_c0.357_w0.109_nu0.3 | marginal | gap | 0.20867-0.81650 | agrees | lo +3.06 %, hi +0.75 % |

### Band comparison (no-gap cells; bands 4-15 at G, X, M, R + 4 interior k; 1-15 off Gamma)

| cell | max abs delta (extrapolated, all) | consistent | rows with mode crossing | max abs delta (no crossing) | consistent (no crossing) | finest levels amm n40 vs Q2 n3, rel range | sampled amm n20 vs Q2 n1, rel range |
|---|---|---|---|---|---|---|---|
| tpms_schwarzp_sheet_d0.2895_nu0.342 | +26.79 % | 115/117 | 18 | +1.72 % | 99/99 | -26.83 %..+20.07 % | +0.41 %..+41.84 % |
| strut_octet_r0.06_nu0.3 | +17.45 % | 117/117 | 25 | +12.16 % | 92/92 | +0.57 %..+2.53 % | -0.78 %..+41.76 % |

### Eigensolver-free band counts (PARDISO inertia at probe frequencies between clusters; deviation 8)

| cell | k checked | probes | Q2 Lanczos != inertia | amm-model Lanczos != inertia | count Q2 n3 != amm n40 |
|---|---|---|---|---|---|
| tpms_schwarzp_sheet_d0.2895_nu0.342 | flagged: amm_path:4, amm_path:16 | 7 | n12: 4 probes, Lanczos -3..-1 copies; n16: 4 probes, Lanczos -3..-1 copies; n20: 2 probes, Lanczos -3..-1 copies | n20: 3 probes, Lanczos -5..-1 copies; n30: 4 probes, Lanczos -3..-1 copies; n40: 3 probes, Lanczos -1..-1 copies | 0 |
| strut_octet_r0.06_nu0.3 | all 8 | 47 | 0 | n20: 2 probes, Lanczos -1..-1 copies | 21 probes (amm fewer modes below the probe in 21) |

### Worst two-sided discrepancies (|delta|)

| cell | quantity | delta | consistent within 2 sqrt(u^2 + e^2) |
|---|---|---|---|
| thin_sl_c0.402_w0.061_nu0.3 | per-k lo at amm_path [0.0, 0.0, 0.0] | -30.62 % | True |
| thin_sl_c0.402_w0.061_nu0.3 | static G | -29.60 % | True |
| thin_sl_c0.402_w0.061_nu0.3 | per-k lo at own_adversarial [0.9982544674878416, 0.9980270866461951, 0.9978957956051929] | -13.75 % | True |
| thin_sl_c0.402_w0.061_nu0.3 | per-k lo at amm_path [1.0, 1.0, 1.0] | -13.75 % | True |
| thin_sl_c0.402_w0.061_nu0.3 | per-k lo at amm_path [1.0, 1.0, 0.0] | -11.51 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | per-k hi at amm_path [1.0, 1.0, 1.0] | -5.15 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | static E100 | -5.01 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | per-k hi at amm_path [1.0, 0.0, 0.0] | -4.88 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | gap hi edge (extrapolated) | -4.85 % | True |
| strut_bcc_R0.27_r0.06_nu0.342 | per-k hi at amm_path [0.0, 0.0, 0.0] | -4.85 % | True |

Bound/edge statuses: {'sound': 57, 'marginal': 11, 'unsound': 0}. Claim statuses: {'agrees': 23, 'inconclusive': 1, 'disagrees': 0}.
