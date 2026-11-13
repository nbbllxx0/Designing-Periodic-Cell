#!/bin/bash
# V1b job lanes (each lane runs its jobs in sequence with 6 MKL threads). Usage: lanes.sh A|B
cd /c/AI/AgenticMetamaterials
PY=python
export MKL_NUM_THREADS=6 OMP_NUM_THREADS=6
L=results/verification/v1b
wait_file() { while [ ! -f "$1" ]; do sleep 30; done; }
if [ "$1" = A ]; then
  wait_file $L/q2/tpms_schwarzp_d0.25_nu0.3_bloch.json
  $PY scripts/verify/v1b/amm_side.py tpms_schwarzp_d0.25_nu0.3 > $L/amm_k_tpms_schwarzp_d0.25_nu0.3.log 2>&1
  for c in strut_bcc_R0.27_r0.06_nu0.342 thin_sl_c0.402_w0.061_nu0.3; do
    $PY scripts/verify/v1b/run_q2_bloch.py $c > $L/q2_bloch_$c.log 2>&1
    $PY scripts/verify/v1b/amm_side.py $c > $L/amm_k_$c.log 2>&1
  done
fi
if [ "$1" = B ]; then
  wait_file $L/thin_sl_c0.357_w0.109_nu0.3_amm.json
  $PY scripts/verify/v1b/run_q2_static.py 40 --cells strut_bcc_R0.27_r0.06_nu0.342,strut_octet_r0.06_nu0.3,thin_sl_c0.402_w0.061_nu0.3,thin_sl_c0.357_w0.109_nu0.3 >> $L/q2_static.log 2>&1
  $PY scripts/verify/v1b/skfem_cells.py 12 16 > $L/skfem.log 2>&1
  for c in strut_octet_r0.06_nu0.3 tpms_schwarzp_sheet_d0.2895_nu0.342 thin_sl_c0.357_w0.109_nu0.3; do
    $PY scripts/verify/v1b/run_q2_bloch.py $c > $L/q2_bloch_$c.log 2>&1
    $PY scripts/verify/v1b/amm_side.py $c > $L/amm_k_$c.log 2>&1
  done
fi
echo lane $1 done
