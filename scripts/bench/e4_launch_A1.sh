#!/usr/bin/env bash
# E4 under amendment A1 (2026-11-07; plan/E4_PREREG.md section 9): phases 1 and 3 only, then full scoring with the
# frozen checker, the amended analysis and the symmetric quota check. A stop (quota interruption = exit 3, refusal,
# GPU state unreadable) stops the chain; rerunning this script resumes without rerunning finished jobs.
set -u
cd /c/AI/AgenticMetamaterials
export MKL_CBWR=AUTO,STRICT
P=C:/Users/nbbll/anaconda3/envs/amm/python.exe
E="$P -u -B scripts/bench/e4.py"
for k in 1 3; do
  $E run --tag e4 --phase $k --amendment A1 || { echo "phase $k stopped (rc $?)"; exit 1; }
done
$E quota-check --tag e4
$E score --tag e4 --done-only || { echo "score stopped"; exit 1; }
$E analyze --tag e4 --amended A1 || { echo "analyze stopped"; exit 1; }
echo E4_A1_DONE
