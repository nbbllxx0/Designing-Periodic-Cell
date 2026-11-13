#!/bin/bash
# V6 GPU queue, part 2: case-2 sessions, then replays of the remaining sessions; each step under the shared lock.
cd /c/AI/AgenticMetamaterials
PY=python
export MKL_NUM_THREADS=16
L="$PY -B scripts/ops/gpulock_run.py v6 --"
V=results/verification/v6
for m in PA12 316L; do
  $L $PY -B scripts/verify/v6/run_session.py $V/case2/config_$m.json > $V/case2/session_$m.log 2>&1
done
$L $PY -B scripts/verify/v6/replay_session.py $V/case1/session_reference $V/case1/replay_reference.json > $V/case1/replay_reference.log 2>&1
for m in PA12 316L; do
  $L $PY -B scripts/verify/v6/replay_session.py $V/case2/session_$m $V/case2/replay_$m.json > $V/case2/replay_$m.log 2>&1
done
echo queue2 done
