#!/bin/bash
# B7 Linux clean-install test (inside python:3.12-slim, --rm). /in and /data are read-only; logs go to /out.
set -u
t() { date +%s; }
mkdir -p /work && cd /work && cp -r /in/tests /in/pyproject.toml /in/examples /work/
echo "== system"; python --version; uname -a; nproc; head -2 /etc/os-release
echo "== wheel sha256 $(sha256sum /in/amm-0.2.0-py3-none-any.whl | cut -c1-64)"
T0=$(t)
echo "== pip install torch (CPU build, PyTorch CPU index)"; s=$(t)
python -m pip install --no-cache-dir --root-user-action=ignore torch --index-url https://download.pytorch.org/whl/cpu > /out/pip_torch.log 2>&1; echo "exit $? $(( $(t)-s )) s"; tail -1 /out/pip_torch.log
echo "== pip install wheel[all] + pytest (PyPI)"; s=$(t)
python -m pip install --no-cache-dir --root-user-action=ignore "/in/amm-0.2.0-py3-none-any.whl[all]" "pytest>=9.0" > /out/pip_amm.log 2>&1; echo "exit $? $(( $(t)-s )) s"; tail -1 /out/pip_amm.log
python -m pip freeze > /out/pip_freeze.txt
echo "== identity inside the install"
python -c "import json, amm, amm.tools as t, amm.certify as c, amm.data as d, torch; print(json.dumps(dict(amm=amm.__version__, file=amm.__file__, code_hash=t.code_hash(), checker_hash=c.checker_hash(), torch=torch.__version__, cuda=torch.cuda.is_available(), mkl_cbwr=str(amm.MKL_CBWR_STATUS), data_dir=str(d.data_dir()), data_verify=d.verify(roles=('runtime','provenance','documentation')))))" | tee /out/identity.json
export MKL_NUM_THREADS=8
echo "== tutorial (a)"; s=$(t); python examples/01_evaluate_tensor.py > /out/01_evaluate_tensor_linux.log 2>&1; echo "exit $? $(( $(t)-s )) s"; tail -2 /out/01_evaluate_tensor_linux.log
echo "== pytest CPU subset (-m 'not gpu')"; s=$(t); python -m pytest -q -m "not gpu" -rs --durations=10 -p no:cacheprovider tests > /out/pytest_linux.log 2>&1; echo "exit $? $(( $(t)-s )) s"; grep -E "passed|failed|^FAILED|^ERROR" /out/pytest_linux.log | tail -12
echo "== total $(( $(t)-T0 )) s"
