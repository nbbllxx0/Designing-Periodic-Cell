#!/bin/bash
# V6 GPU queue, part 3 (after part 2): tolerance replay of the design session, optional scaling check (case 2).
cd /c/AI/AgenticMetamaterials
PY=python
export MKL_NUM_THREADS=16
L="$PY -B scripts/ops/gpulock_run.py v6 --"
V=results/verification/v6
until grep -q "queue2 done" $V/queue_gpu.log; do sleep 20; done
$L $PY -B scripts/verify/v6/run_session.py $V/case2/config_scaling_316L.json > $V/case2/session_scaling_316L.log 2>&1
$L $PY -B scripts/verify/v6/replay_session.py $V/case1/session_design $V/case1/replay_design.json > $V/case1/replay_design.log 2>&1
echo queue3 done
