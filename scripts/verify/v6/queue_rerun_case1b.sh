#!/bin/bash
# Continuation of queue_rerun_case1.sh, run strictly one job at a time so total MKL threads stay <= 16 (the first
# queue would have run two macro jobs next to a replay). Waits for the running reference session (PID given) first.
cd /c/AI/AgenticMetamaterials
PY=python
export MKL_NUM_THREADS=16
L="$PY -B scripts/ops/gpulock_run.py v6 --"
V=results/verification/v6/case1
while kill -0 "$1" 2>/dev/null; do sleep 10; done
echo "session_reference finished $(date)"
$PY -B scripts/verify/v6/macro.py design $V/session_design > $V/macro_design.log 2>&1
$PY -B scripts/verify/v6/macro.py reference $V/session_reference > $V/macro_reference.log 2>&1
echo "macro done $(date)"
$L $PY -B scripts/verify/v6/replay_session.py $V/session_design $V/replay_design.json > $V/replay_design.log 2>&1
$L $PY -B scripts/verify/v6/replay_session.py $V/session_reference $V/replay_reference.json > $V/replay_reference.log 2>&1
echo "replays done $(date)"
$PY -B scripts/verify/v6/recheck.py $V/recheck_design.json $V/session_design > $V/recheck_design.log 2>&1
$PY -B scripts/verify/v6/recheck.py $V/recheck_reference.json $V/session_reference > $V/recheck_reference.log 2>&1
echo "rerun done $(date)"
