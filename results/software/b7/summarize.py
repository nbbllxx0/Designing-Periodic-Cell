"""B7: copy the clean-install logs to results/software/b7/ and count the outcomes from them (no number typed by hand)."""
import json, re, shutil
from pathlib import Path
W = Path(r"C:\AI\AgenticMetamaterials_workspaces\b7")
OUT = Path(r"C:\AI\AgenticMetamaterials\results\software\b7")
OUT.mkdir(parents=True, exist_ok=True)
plat = {"windows": (W / "win", ["install_stdout.log", "pip_install.log", "pip_freeze.txt", "identity.json",
                                "01_evaluate_tensor_win.log", "pytest_win.log", "run_tests_stdout.log"]),
        "linux": (W / "linux_out", ["run_stdout.log", "pip_torch.log", "pip_amm.log", "pip_freeze.txt", "identity.json",
                                    "01_evaluate_tensor_linux.log", "pytest_linux.log"])}
summary = {}
for name, (d, files) in plat.items():
    o = OUT / name
    o.mkdir(exist_ok=True)
    for f in files:
        if (d / f).exists():
            shutil.copy2(d / f, o / f)
    log = next((d / f for f in files if f.startswith("pytest")), None)
    txt = log.read_text(encoding="utf-8", errors="replace") if log and log.exists() else ""
    last = [l for l in txt.splitlines() if re.search(r"\d+ passed|\d+ failed|no tests ran", l)]
    line = last[-1] if last else None
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|deselected|errors?|xfailed|xpassed|warnings?)", line or "")}
    skips = [l for l in txt.splitlines() if l.startswith("SKIPPED")]
    ident = json.loads((d / "identity.json").read_text(encoding="utf-8").strip().splitlines()[-1]) if (d / "identity.json").exists() else None
    freeze = (d / "pip_freeze.txt").read_text(encoding="utf-8").splitlines() if (d / "pip_freeze.txt").exists() else []
    pick = {p.split("==")[0].lower(): p for p in freeze if "==" in p}
    summary[name] = dict(pytest_summary_line=line, counts=counts, skipped_reasons=skips,
                         failed=[l for l in txt.splitlines() if l.startswith(("FAILED", "ERROR"))],
                         identity=ident, n_packages=len(freeze),
                         key_versions={k: pick.get(k) for k in ("torch", "numpy", "scipy", "mkl", "pypardiso", "pydantic", "pytest", "botorch", "mcp", "starlette", "scikit-image")},
                         amm_line=next((p for p in freeze if p.lower().startswith("amm")), None))
(OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print(json.dumps({k: dict(line=v["pytest_summary_line"], counts=v["counts"], ident=(v["identity"] or {}).get("code_hash"), chk=(v["identity"] or {}).get("checker_hash")) for k, v in summary.items()}, indent=1))

# run 1 (before the conftest fix), kept as evidence of the one failure it found
run1 = {}
for name, sub, log in (("windows", "win", "pytest_win.log"), ("linux", "linux", "pytest_linux.log")):
    txt = (W / "run1" / sub / log).read_text(encoding="utf-8", errors="replace")
    o = OUT / "run1" / name
    o.mkdir(parents=True, exist_ok=True)
    for f in (W / "run1" / sub).iterdir():
        if f.name in (log, "identity.json", "run_stdout.log", "run_tests_stdout.log"):
            shutil.copy2(f, o / f.name)
    line = [l for l in txt.splitlines() if re.search(r"\d+ passed", l)][-1]
    run1[name] = dict(line=line, failed=[l for l in txt.splitlines() if l.startswith("FAILED")] or
                      [l.strip("_ ") for l in txt.splitlines() if l.startswith("____") and "test_" in l])
summary["run1_before_conftest_fix"] = run1
(OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
import csv
with open(OUT / "T14_b7.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["platform", "python", "torch", "wheel_sha256", "code_hash", "checker_hash", "data_verify_ok",
                "passed", "failed", "skipped", "deselected", "seconds", "command"])
    for name in ("windows", "linux"):
        v = summary[name]; i = v["identity"] or {}
        secs = re.search(r"in ([\d.]+)s", v["pytest_summary_line"] or "")
        py = "3.11.5 (venv, Anaconda base)" if name == "windows" else "3.12.16 (python:3.12-slim, Debian 13, WSL2 kernel)"
        w.writerow([name, py, i.get("torch"), "69025768650ba2ed135c4a807171aeedaa23d54c77e43377b2de07e0ef107484",
                    i.get("code_hash"), i.get("checker_hash"), (i.get("data_verify") or {}).get("ok"),
                    v["counts"].get("passed", 0), v["counts"].get("failed", 0), v["counts"].get("skipped", 0),
                    v["counts"].get("deselected", 0), secs.group(1) if secs else "",
                    'pytest -q -m "not gpu" -rs (AMM_DATA_DIR = data bundle; Windows under gpulock_run.py b7, CUDA_VISIBLE_DEVICES=-1)'])
print(json.dumps(run1, indent=1))
