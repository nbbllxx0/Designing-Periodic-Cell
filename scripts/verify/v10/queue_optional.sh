#!/bin/bash
# V10 optional set probe_old (NOTES 1.6), started after queue_release.sh ends; under the solver lock.
PY=python
O=results/verification/v10
L=$O/logs
export PYTHONUNBUFFERED=1
until grep -q "^end " $L/queue_release.log; do sleep 20; done
$PY scripts/ops/keep_awake.py $(cat /proc/$$/winpid) > /dev/null 2>&1 &
date "+probe_old %F %T"
$PY scripts/ops/gpulock_run.py v10 -- $PY scripts/verify/v10/replay_set.py probe_old --list $O/lists/probe_old.txt > $L/probe_old.log 2>&1; echo "probe_old exit $?"
date "+end %F %T"
