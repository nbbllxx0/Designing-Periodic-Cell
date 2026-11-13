#!/bin/bash
# V10 sets 2 and 1 (final-release regression, then frozen E4), each step under the shared solver lock.
# Run from the repo root with Git Bash. Holds a Windows idle-sleep block while this shell lives.
PY=python
O=results/verification/v10
L=$O/logs
export PYTHONUNBUFFERED=1
$PY scripts/ops/keep_awake.py $(cat /proc/$$/winpid) > /dev/null 2>&1 &
echo "queue shell winpid $(cat /proc/$$/winpid)"
date "+start %F %T"
$PY scripts/ops/gpulock_run.py v10 -- $PY scripts/software/b1b3_reference.py $O/b1b3_reference_v10.json > $L/release_reference.log 2>&1; echo "reference exit $?"
$PY scripts/software/b1b3_reference.py --compare results/software/b1b3_reference_final.json $O/b1b3_reference_v10.json > $L/release_reference_compare.txt 2>&1; echo "compare exit $?"
for s in release_tutorial release_gui release_v6 e4_frozen; do
  date "+$s %F %T"
  $PY scripts/ops/gpulock_run.py v10 -- $PY scripts/verify/v10/replay_set.py $s --list $O/lists/$s.txt > $L/$s.log 2>&1; echo "$s exit $?"
done
date "+end %F %T"
