"""V10: environment identity of this machine's amm env, compared with the E4 snapshot (no GPU work).

    python scripts/verify/v10/env_identity.py [out.json]

Records python, every installed distribution with its version (and the sha256 of the sorted list), torch/CUDA,
GPU and driver (nvidia-smi), MKL CBWR status, code/checker identity and the data files checked against
amm/data_manifest.json; then the package differences against results/bench/e4/snapshot/environment.txt.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v10lib as L  # noqa: E402


def freeze():
    pk = {}
    for d in md.distributions():
        n = d.metadata["Name"]
        if n:
            pk[n.lower().replace("_", "-")] = d.version
    return dict(sorted(pk.items()))


def snapshot_packages(p: Path):
    pk = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s]+)$", line.strip())
        if m:
            pk[m.group(1).lower().replace("_", "-")] = m.group(2)
        m = re.match(r"^([A-Za-z0-9_.\-]+) @ ", line.strip())
        if m:
            pk[m.group(1).lower().replace("_", "-")] = "(local build)"
    return pk


def main(argv):
    out = Path(argv[0]) if argv else L.OUT / "env_windows.json"
    import amm
    from amm import data
    pk = freeze()
    lines = [f"{k}=={v}" for k, v in pk.items()]
    d = dict(env=L.env_brief(), packages=pk, packages_sha256=hashlib.sha256("\n".join(lines).encode()).hexdigest(),
             executable=sys.executable, data_dir=str(data.data_dir()), data_verify=data.verify(),
             data_identity=data.manifest().get("identity"))
    try:
        d["nvidia_smi"] = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                          "--format=csv,noheader"], capture_output=True, text=True,
                                         timeout=60).stdout.strip()
    except Exception as ex:  # noqa: BLE001
        d["nvidia_smi"] = f"unavailable: {ex}"
    snap = L.ROOT / "results/bench/e4/snapshot/environment.txt"
    if snap.is_file():
        s = snapshot_packages(snap)
        first = snap.read_text(encoding="utf-8").splitlines()[0]
        diff = {k: dict(e4=s.get(k), now=pk.get(k)) for k in sorted(set(s) | set(pk)) if s.get(k) != pk.get(k)}
        d["vs_e4_snapshot"] = dict(e4_python=first, n_e4=len(s), n_now=len(pk), differences=diff,
                                   e4_nvidia=re.findall(r"KMD version\s*:\s*([0-9.]+)", snap.read_text(encoding="utf-8")))
    L.jdump(d, out)
    print(json.dumps(d["env"]), d["packages_sha256"][:16], d["nvidia_smi"], "data ok", d["data_verify"].get("ok"))
    if "vs_e4_snapshot" in d:
        print("differences vs E4 snapshot:", json.dumps(d["vs_e4_snapshot"]["differences"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
