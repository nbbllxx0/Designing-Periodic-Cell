#!/bin/bash
# V3 timing pilot (development spec M02, not a V3 target). Run under the GPU lock.
cd /c/AI/AgenticMetamaterials
PY=python
P=results/verification/v3/pilot
echo "pilot start $(date '+%F %T')"
MKL_NUM_THREADS=16 OMP_NUM_THREADS=16 $PY scripts/verify/v3/pilot_cert.py
echo "witness cert done $(date '+%F %T')"
MKL_NUM_THREADS=16 OMP_NUM_THREADS=16 $PY scripts/verify/v3/driver.py --out $P --targets $P/targets_pilot.json --cap-hours 1000
echo "pilot end $(date '+%F %T')"
