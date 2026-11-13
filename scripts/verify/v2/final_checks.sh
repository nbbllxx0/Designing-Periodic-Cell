#!/usr/bin/env bash
# V2 final checks, run as ONE job under the solver lock:
#   python scripts/verify/v2/lockwait.py v2 -- bash scripts/verify/v2/final_checks.sh
# 1. replay every V2 session log; 2. bit-identity reference vs results/software/b1b3_reference_final.json;
# 3. the full test suite.
set -u
cd /c/AI/AgenticMetamaterials
PY=python
WS=/c/AI/AgenticMetamaterials_workspaces/v2
LOG=results/verification/v2/logs
date "+start %F %T"
t0=$(date +%s)
$PY -B -u scripts/verify/v2/replay_all.py --tag all > $LOG/replay_all.log 2>&1; echo "replay exit $?"
t1=$(date +%s); echo "replay seconds $((t1-t0))"
$PY -B -u scripts/software/b1b3_reference.py $WS/v2_reference_post.json > $WS/v2_reference_post.log 2>&1; echo "reference exit $?"
$PY -B scripts/software/b1b3_reference.py --compare results/software/b1b3_reference_final.json $WS/v2_reference_post.json > $WS/v2_compare.txt 2>&1; echo "compare exit $?"
t2=$(date +%s); echo "reference seconds $((t2-t1))"
$PY -B -m pytest -q -rs -p no:cacheprovider > $LOG/full_tests.log 2>&1; echo "pytest exit $?"
t3=$(date +%s); echo "pytest seconds $((t3-t2))"
date "+end %F %T"
