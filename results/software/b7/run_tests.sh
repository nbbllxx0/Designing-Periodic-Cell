#!/bin/bash
# B7 Windows: identity and CPU test subset against the installed wheel, under the shared solver lock (gpulock_run.py b7).
set -u
W=/c/AI/AgenticMetamaterials_workspaces/b7/win
S=/c/AI/AgenticMetamaterials/release/staging/amm-0.2.0
LOCK="C:/Users/nbbll/anaconda3/envs/amm/python.exe C:/AI/AgenticMetamaterials/scripts/ops/gpulock_run.py b7 --"
VPY=C:/AI/AgenticMetamaterials_workspaces/b7/win/venv/Scripts/python.exe
export AMM_DATA_DIR='C:\AI\AgenticMetamaterials\release\data_bundle\amm-data-1' CUDA_VISIBLE_DEVICES=-1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
t() { date +%s; }
rm -rf $W/t && mkdir -p $W/t && cp -r $S/tests $S/pyproject.toml $W/t/ && mkdir -p $W/t/examples && cp $S/examples/*.py $W/t/examples/
cd $W/t
echo "== identity inside the install"
$LOCK $VPY -c "import json, amm, amm.tools as t, amm.certify as c, amm.data as d, torch; print(json.dumps(dict(amm=amm.__version__, file=amm.__file__, code_hash=t.code_hash(), checker_hash=c.checker_hash(), torch=torch.__version__, cuda=torch.cuda.is_available(), mkl_cbwr=str(amm.MKL_CBWR_STATUS), data_dir=str(d.data_dir()), data_verify=d.verify(roles=('runtime','provenance','documentation')))))" | tee $W/identity.json
echo "== tutorial (a)"; s=$(t); $LOCK $VPY examples/01_evaluate_tensor.py > $W/01_evaluate_tensor_win.log 2>&1; echo "exit $? $(( $(t)-s )) s"; tail -2 $W/01_evaluate_tensor_win.log
echo "== pytest CPU subset (-m 'not gpu')"; s=$(t); $LOCK $VPY -m pytest -q -m "not gpu" -rs --durations=10 -p no:cacheprovider tests > $W/pytest_win.log 2>&1; echo "exit $? $(( $(t)-s )) s"; grep -E "passed|failed|^FAILED|^ERROR" $W/pytest_win.log | tail -12
