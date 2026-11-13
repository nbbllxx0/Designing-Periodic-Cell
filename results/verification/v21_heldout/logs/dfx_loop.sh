#!/bin/bash
# waits for each claim-B certificate, exports the DOLFINx case and runs its levels (V21 protocol)
cd /c/AI/AgenticMetamaterials
PY=/c/Users/nbbll/anaconda3/envs/amm/python.exe
names=$($PY -c "import json;print(' '.join(c['name'] for c in json.load(open('results/verification/v21_heldout/cells.json'))['cells']))")
for n in $names; do
  until [ -f results/verification/v21_heldout/certs/${n}_B.json ]; do sleep 30; done
  $PY scripts/experiments/v21_heldout.py export
  echo "=== $n $(date -u +%H:%M:%S)"
  $PY scripts/experiments/v21_heldout.py run $n
done
echo "=== all done $(date -u +%H:%M:%S)"
