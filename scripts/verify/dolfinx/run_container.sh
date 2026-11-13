#!/bin/bash
# Run a command inside the DOLFINx-MPC complex container with at most 8 CPU cores (V1c).
# Usage: scripts/verify/dolfinx/run_container.sh <name> <command...>   (project mounted at /work, inputs at /inputs)
NAME="$1"; shift
MSYS_NO_PATHCONV=1 docker run --rm --name "v1c_${NAME}" --cpus 8 --memory 40g \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -v "C:\AI\AgenticMetamaterials:/work" \
  -v "C:\AI\AgenticMetamaterials_workspaces\v1c_frozen\inputs:/inputs:ro" \
  -w /work amm/dolfinx-mpc:0.11.0-complex \
  bash -c "source /usr/local/bin/dolfinx-complex-mode && $*"
