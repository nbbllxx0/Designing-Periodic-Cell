#!/bin/bash
# V1c: all cases, container steps first (one container at a time, 8 cores), then the amm-side evaluations.
cd /c/AI/AgenticMetamaterials
CASES="cb_c0.5_w0.2_nu0.3 cb_c0.6_w0.2_nu0.342 cb_c0.6_w0.3_nu0.3 cb_c0.7_w0.3_nu0.3 cb_c0.8_w0.3_nu0.3 tpms_schwarzp_d0.25_nu0.3 strut_bcc_R0.27_r0.06_nu0.342 thin_sl_c0.402_w0.061_nu0.3"
STEPS=${1:-search,l1,l2,l3,id}
for c in $CASES; do
  echo "=== $c $(date)"
  python -u scripts/verify/dolfinx/run_case.py $c --steps $STEPS || echo "FAILED $c"
done
echo "ALL DONE $(date)"
