#!/bin/bash
# V1c pass 2: finest levels that were killed by the joint-rank memory growth (now one container per k), the extra
# edge-k level on the exact cells, the SLEPc cross-check (exact cells and the thin resonator; skipped on the TPMS and
# strut cells for the compute budget), and the amm-side runs for the thin resonator.
cd /c/AI/AgenticMetamaterials
until grep -q "ALL DONE" results/verification/dolfinx/logs/run_all.log; do sleep 20; done
for c in cb_c0.8_w0.3_nu0.3 tpms_schwarzp_d0.25_nu0.3; do
  echo "=== $c l3 $(date)"; python -u scripts/verify/dolfinx/run_case.py $c --steps l3,id || echo "FAILED $c"
done
for c in cb_c0.5_w0.2_nu0.3 cb_c0.6_w0.2_nu0.342 cb_c0.6_w0.3_nu0.3 cb_c0.7_w0.3_nu0.3 cb_c0.8_w0.3_nu0.3; do
  echo "=== $c l4 $(date)"; python -u scripts/verify/dolfinx/run_case.py $c --steps l4 || echo "FAILED $c"
done
for c in cb_c0.5_w0.2_nu0.3 cb_c0.6_w0.2_nu0.342 cb_c0.6_w0.3_nu0.3 cb_c0.7_w0.3_nu0.3 cb_c0.8_w0.3_nu0.3 thin_sl_c0.402_w0.061_nu0.3; do
  echo "=== $c slepc $(date)"; python -u scripts/verify/dolfinx/run_case.py $c --steps slepc || echo "FAILED $c"
done
echo "PASS2 DONE $(date)"
