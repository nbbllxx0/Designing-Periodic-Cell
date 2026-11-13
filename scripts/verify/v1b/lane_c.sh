#!/bin/bash
# V1b lane C (replaces the rest of lane B, reordered for priority): skfem -> marginal resonator Bloch -> octet bands.
cd /c/AI/AgenticMetamaterials
PY=python
export MKL_NUM_THREADS=6 OMP_NUM_THREADS=6
L=results/verification/v1b
while tasklist //FI "PID eq $1" | grep -q python; do sleep 20; done
$PY scripts/verify/v1b/skfem_cells.py 12 16 > $L/skfem.log 2>&1
for c in thin_sl_c0.357_w0.109_nu0.3 strut_octet_r0.06_nu0.3; do
  $PY scripts/verify/v1b/run_q2_bloch.py $c > $L/q2_bloch_$c.log 2>&1
  $PY scripts/verify/v1b/amm_side.py $c > $L/amm_k_$c.log 2>&1
done
echo lane C done
