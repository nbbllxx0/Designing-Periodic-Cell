#!/bin/bash
# V10 set 3: cross-environment replay inside python:3.12-slim, CPU only. /in read-only, logs/results to /out.
set -u
t() { date +%s; }
echo "== system"; python --version; uname -a; nproc; head -2 /etc/os-release; date -u
T0=$(t)
mkdir -p /work && cp -r /in/src /work/src
echo "== pip install torch (CPU build, PyTorch CPU index)"; s=$(t)
python -m pip install --no-cache-dir --root-user-action=ignore torch --index-url https://download.pytorch.org/whl/cpu > /out/pip_torch.log 2>&1; echo "exit $? $(( $(t)-s )) s"; tail -1 /out/pip_torch.log
echo "== pip install amm[all] from the source copy (PyPI)"; s=$(t)
python -m pip install --no-cache-dir --root-user-action=ignore "/work/src[all]" > /out/pip_amm.log 2>&1; echo "exit $? $(( $(t)-s )) s"; tail -1 /out/pip_amm.log
python -m pip freeze > /out/pip_freeze.txt
export AMM_DATA_DIR=/data MKL_NUM_THREADS=8 PYTHONUNBUFFERED=1 V10_ROOT=/in/repo V10_OUT=/out
cd /tmp
echo "== smoke"; python -I -c "import amm, torch; from amm import tools, certify, data; print(amm.__version__, amm.__file__); print('torch', torch.__version__, 'cuda', torch.cuda.is_available()); print('MKL CBWR', amm.MKL_CBWR_STATUS); print('code', tools.code_hash(), 'checker', certify.checker_hash()); print('data', data.verify()['ok'])"
echo "== replays"; s=$(t)
python /in/v10/replay_set.py xenv_linux /in/repo/examples/outputs/02_session/session.jsonl /in/repo/examples/outputs/03_session/session.jsonl /in/repo/results/bench/smoke/jobs/codex-C-r1-N02/session/session.jsonl > /out/replays_linux.log 2>&1; echo "exit $? $(( $(t)-s )) s"; tail -5 /out/replays_linux.log
echo "== total $(( $(t)-T0 )) s"
