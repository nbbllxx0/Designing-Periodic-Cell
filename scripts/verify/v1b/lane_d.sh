#!/bin/bash
# V1b lane D: the TPMS sheet band comparison after lane A ends (lowest priority).
cd /c/AI/AgenticMetamaterials
PY=python
export MKL_NUM_THREADS=6 OMP_NUM_THREADS=6
L=results/verification/v1b
while [ ! -f $L/thin_sl_c0.402_w0.061_nu0.3_amm_k.json ]; do sleep 30; done
c=tpms_schwarzp_sheet_d0.2895_nu0.342
$PY scripts/verify/v1b/run_q2_bloch.py $c > $L/q2_bloch_$c.log 2>&1
$PY scripts/verify/v1b/amm_side.py $c > $L/amm_k_$c.log 2>&1
echo lane D done
