#!/bin/bash
set -u
mkdir -p /work && cp -r /in/src /work/src
python -m pip install -q --no-cache-dir --root-user-action=ignore torch --index-url https://download.pytorch.org/whl/cpu > /out/diag_pip.log 2>&1
python -m pip install -q --no-cache-dir --root-user-action=ignore "/work/src[all]" >> /out/diag_pip.log 2>&1
export AMM_DATA_DIR=/data MKL_NUM_THREADS=8 PYTHONUNBUFFERED=1
cd /tmp && python /in/diag03.py
