#!/usr/bin/env bash
# Resume of the smoke run after the self-wait fix in e4.gpu_busy (2026-11-06). --allow-drift: the smoke manifest
# predates the fix (the drift is logged in results/bench/smoke/run_log.txt). Not used for E4, which is planned after.
set -u
cd /c/AI/AgenticMetamaterials
export MKL_CBWR=AUTO,STRICT
P=C:/Users/nbbll/anaconda3/envs/amm/python.exe
E="$P -u -B scripts/bench/e4.py"
$E run --tag smoke --smoke --allow-drift --provider none --arms O --ids X01,S01
$E run --tag smoke --smoke --allow-drift --provider claude --arms D,B,C --reps 1 --ids S01
$E run --tag smoke --smoke --allow-drift --provider codex --arms C --reps 1 --ids N02 --timeout 60
$E score --tag smoke --done-only
echo SMOKE_DONE
