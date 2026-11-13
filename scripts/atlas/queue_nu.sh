#!/bin/sh
# run the atlas at the other materials' Poisson ratios once the nu = 0.3 run has finished (one GPU job at a time)
cd /c/AI/AgenticMetamaterials
while [ "$(grep -c '' results/atlas/atlas_nu0.3.jsonl 2>/dev/null)" -lt 2722 ]; do sleep 60; done
for nu in 0.39 0.342; do
  MKL_NUM_THREADS=16 python scripts/atlas/run_atlas.py $nu > results/atlas/run_nu$nu.log 2>&1
done
