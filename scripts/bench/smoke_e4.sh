#!/usr/bin/env bash
# Harness smoke run before E4 (2026-11-06): development briefs only, tag "smoke" (not reported as E4 data).
# Covers: Codex D/B/C, Claude D/B/C, arm O, an injected timeout and an injected crash (stale workspace).
set -u
cd /c/AI/AgenticMetamaterials
export MKL_CBWR=AUTO,STRICT
P=C:/Users/nbbll/anaconda3/envs/amm/python.exe
E="$P -u -B scripts/bench/e4.py"
WS=/c/AI/AgenticMetamaterials_workspaces/smoke
# injected crash: a stale workspace without run.json for codex-D-r1-X01 (must be moved to attempts/ and rerun)
H=$($P -c "import hashlib;print(hashlib.sha256(b'smoke/codex-D-r1-X01').hexdigest()[:12])")
mkdir -p "$WS/$H" && echo "injected crash residue" > "$WS/$H/partial.txt"
# (done)$E run --tag smoke --smoke --provider codex --arms D,B,C --reps 1 --ids X01,S01,N01,A04
$E run --tag smoke --smoke --provider none --arms O --ids X01,S01
$E run --tag smoke --smoke --provider claude --arms D,B,C --reps 1 --ids S01
# injected timeout: 60 s on C/N02
$E run --tag smoke --smoke --provider codex --arms C --reps 1 --ids N02 --timeout 60
$E score --tag smoke --done-only
echo SMOKE_DONE
