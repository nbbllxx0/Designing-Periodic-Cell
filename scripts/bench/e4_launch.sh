#!/usr/bin/env bash
# E4 launch (2026-11-06): phases 1-4 in order (plan/E4_PREREG.md section 4), then interim scoring of the primary
# phases. Phase 5 (Claude, user's claude.ai quota) is started separately. A phase that stops (refusal, GPU state
# unreadable, crash) stops the chain; rerunning this script resumes: finished jobs are skipped, interrupted ones
# recovered or archived.
set -u
cd /c/AI/AgenticMetamaterials
export MKL_CBWR=AUTO,STRICT
P=C:/Users/nbbll/anaconda3/envs/amm/python.exe
E="$P -u -B scripts/bench/e4.py"
for k in 1 2; do
  $E run --tag e4 --phase $k || { echo "phase $k stopped"; exit 1; }
done
$E score --tag e4 --done-only
for k in 3 4; do
  $E run --tag e4 --phase $k || { echo "phase $k stopped"; exit 1; }
done
echo E4_PHASES_1_4_DONE
