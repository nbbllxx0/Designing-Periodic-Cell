#!/bin/bash
# V1c: amm identity-model bands (frozen code, solver lock) at the 6 identity k of every case.
cd /c/AI/AgenticMetamaterials
PY=python
for f in results/verification/dolfinx/inputs/*.json; do
  c=$(basename $f .json)
  [ -f results/verification/dolfinx/amm/${c}_id_n20_ks_id.json ] || $PY -u scripts/verify/dolfinx/amm_bands.py $c id 20 results/verification/dolfinx/raw/$c/ks_id.json
done
echo AMM_ID_DONE
