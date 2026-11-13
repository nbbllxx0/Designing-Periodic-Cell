#!/bin/bash
# B7 Windows clean install: fresh venv (Anaconda base Python), wheel from release/dist, PyPI only (PIP_CONFIG_FILE=nul).
set -u
W=/c/AI/AgenticMetamaterials_workspaces/b7/win
WHL=C:/AI/AgenticMetamaterials/release/dist/amm-0.2.0-py3-none-any.whl
export PIP_CONFIG_FILE=nul PIP_DISABLE_PIP_VERSION_CHECK=1
t() { date +%s; }
cd $W
echo "== wheel sha256: $(sha256sum $WHL | cut -c1-64)"
s=$(t); /c/Users/nbbll/anaconda3/python.exe -m venv $W/venv; echo "venv exit $? $(( $(t)-s )) s"; $W/venv/Scripts/python.exe --version
s=$(t); $W/venv/Scripts/python.exe -m pip install "$WHL[all]" "pytest>=9.0" > $W/pip_install.log 2>&1; echo "pip install exit $? $(( $(t)-s )) s"; tail -1 $W/pip_install.log
$W/venv/Scripts/python.exe -m pip freeze > $W/pip_freeze.txt
du -sh $W/venv
