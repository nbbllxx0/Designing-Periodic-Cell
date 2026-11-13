#!/bin/bash
# V6 case 1 rerun under the current amm code identity (f1a6d625064a6d18; the first case-1 sessions were written by
# e0350cf7efa454b0 before V2's amm/tools.py fix): sessions + replays under the (fixed) shared lock, then the CPU
# checks that read the certificates (macro, recheck). Chains depend only on the spec and amm.geometry/fem (checker
# hash unchanged) and are kept.
cd /c/AI/AgenticMetamaterials
PY=python
export MKL_NUM_THREADS=16
L="$PY -B scripts/ops/gpulock_run.py v6 --"
V=results/verification/v6/case1
$L $PY -B scripts/verify/v6/run_session.py $V/config_design.json > $V/session_design.log 2>&1
$L $PY -B scripts/verify/v6/run_session.py $V/config_reference.json > $V/session_reference.log 2>&1
$PY -B scripts/verify/v6/macro.py design $V/session_design > $V/macro_design.log 2>&1 &
$PY -B scripts/verify/v6/macro.py reference $V/session_reference > $V/macro_reference.log 2>&1 &
$L $PY -B scripts/verify/v6/replay_session.py $V/session_design $V/replay_design.json > $V/replay_design.log 2>&1
$L $PY -B scripts/verify/v6/replay_session.py $V/session_reference $V/replay_reference.json > $V/replay_reference.log 2>&1
wait
MKL_NUM_THREADS=16 $PY -B scripts/verify/v6/recheck.py $V/recheck_design.json $V/session_design > $V/recheck_design.log 2>&1
MKL_NUM_THREADS=16 $PY -B scripts/verify/v6/recheck.py $V/recheck_reference.json $V/session_reference > $V/recheck_reference.log 2>&1
echo rerun done
