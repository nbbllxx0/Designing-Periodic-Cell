"""V10 (reproducibility) helpers: paths, a replay that also keeps the re-executed outputs, and the tolerance
comparison written down in results/verification/v10/NOTES.md section 1 (protocol) before any run.

No amm file is changed. amm.tools.replay does the bit-exact comparison (ok flag, state hash, result hash, error
text per call). On the same re-executed calls this module compares every field of the logged and replayed result
with the stated tolerances, so a replay outside the recorded environment can be classified.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(os.environ["V10_ROOT"]) if os.environ.get("V10_ROOT") else Path(__file__).resolve().parents[3]
OUT = Path(os.environ["V10_OUT"]) if os.environ.get("V10_OUT") else ROOT / "results" / "verification" / "v10"

# ---- tolerances (protocol section 1.4; fixed before any run)
T64 = 1e-8   # relative, every float64 quantity (static homogenization, certificates, bounds, atlas, geometry)
T32 = 1e-3   # relative, search-tier Bloch quantities (complex64 eigen-solves; GPU vs CPU)
FLOOR = 1e-6  # absolute floor of the denominator: |a-b| / max(|a|, |b|, FLOOR)
SEARCH_TIER_KEYS = {"gaps", "gaps_Hz", "best_rel_gap", "bands", "band_edges", "f_lo_Hz", "f_hi_Hz"}
SEARCH_TIER_TOOLS = {"search"}  # whole result is search tier (a BO trajectory)
DERIVED = {"sha256", "bytes", "result_hash", "state_hash", "spec_hash", "key", "cert_key", "file", "path"}
ENV_FIELDS = {"bloch_device"}  # fields that name the environment (present only off the GPU)


def tol_for(tool: str, path: str) -> float:
    if tool in SEARCH_TIER_TOOLS:
        return T32
    parts = {p.split("[")[0] for p in path.split(".") if p}
    return T32 if parts & SEARCH_TIER_KEYS else T64


def _key(path: str) -> str:
    return path.rsplit(".", 1)[-1].split("[")[0]


def walk(tool, a, b, path, acc, volatile):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in volatile:
                continue
            if k not in a or k not in b:
                (acc["env"] if k in ENV_FIELDS else acc["other"]).append(
                    dict(path=f"{path}.{k}", log=str(a.get(k))[:80], replay=str(b.get(k))[:80]))
            else:
                walk(tool, a[k], b[k], f"{path}.{k}", acc, volatile)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            acc["other"].append(dict(path=path, log=f"len {len(a)}", replay=f"len {len(b)}"))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(tool, x, y, f"{path}[{i}]", acc, volatile)
    elif (isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool)
          and not isinstance(b, bool)):
        if a != b:
            if _key(path) in DERIVED:
                acc["derived"].append(path)
                return
            r = abs(a - b) / max(abs(a), abs(b), FLOOR)
            t = tol_for(tool, path)
            acc["n_numeric_diff"] += 1
            if r > acc["max_rel"]:
                acc["max_rel"], acc["max_rel_path"] = r, path
            if r > t:
                acc["over_tol"].append(dict(path=path, log=a, replay=b, rel=r, tol=t))
    elif a != b:
        if isinstance(a, str) and isinstance(b, str) and a.replace("\\", "/") == b.replace("\\", "/"):
            acc["env"].append(dict(path=path, log=a[:80], replay=b[:80], note="path separator only"))
        elif _key(path) in DERIVED:
            acc["derived"].append(path)
        elif _key(path) in ENV_FIELDS:
            acc["env"].append(dict(path=path, log=str(a)[:80], replay=str(b)[:80]))
        else:
            acc["other"].append(dict(path=path, log=str(a)[:120], replay=str(b)[:120]))


def replay_with_outputs(log_path):
    """amm.tools.replay(log) plus the re-executed top-level call outputs (Session.call wrapped, depth-counted)."""
    from amm import tools
    rec, depth = [], [0]
    orig = tools.Session.call

    def call(self, name, args=None, actor="script", progress=None, cancel=None):
        depth[0] += 1
        try:
            out = orig(self, name, args, actor, progress, cancel)
        finally:
            depth[0] -= 1
        if depth[0] == 0:
            rec.append(dict(tool=name, out=out))
        return out

    tools.Session.call = call
    try:
        t0 = time.perf_counter()
        recs = tools.read_log(log_path)
        rep = tools.replay(recs)
        secs = time.perf_counter() - t0
    finally:
        tools.Session.call = orig
    return recs, rep, rec, secs


def tolerance_report(recs, rec):
    from amm import tools
    vol = set(tools.VOLATILE)
    calls = [e for e in recs if e.get("type") == "call"]
    per = []
    if len(calls) != len(rec):
        return dict(aligned=False, n_logged=len(calls), n_replayed=len(rec))
    for e, o in zip(calls, rec):
        out = o["out"]
        acc = dict(max_rel=0.0, max_rel_path=None, n_numeric_diff=0, over_tol=[], other=[], derived=[], env=[])
        if e["tool"] != o["tool"]:
            acc["other"].append(dict(path="tool", log=e["tool"], replay=o["tool"]))
        elif e["ok"] != out["ok"]:
            acc["other"].append(dict(path="ok", log=e["ok"], replay=out["ok"], error=str(out.get("error"))[:300]))
        elif e["ok"]:
            walk(e["tool"], tools.strip_volatile(e["result"]), tools.strip_volatile(tools._plain(out["result"])), "",
                 acc, vol)
        elif e.get("error") != out.get("error"):
            acc["other"].append(dict(path="error", log=str(e.get("error"))[:200], replay=str(out.get("error"))[:200]))
        if out.get("state_hash") != e.get("state_hash"):
            acc["derived"].append("state_hash")
        per.append(dict(seq=e["seq"], tool=e["tool"], **acc))
    over = [(p["seq"], p["tool"], p["over_tol"][:4]) for p in per if p["over_tol"]]
    other = [(p["seq"], p["tool"], p["other"][:4]) for p in per if p["other"]]
    # a derived-hash difference in a call with no numeric, non-numeric or environment difference is unexplained
    unexplained = [(p["seq"], p["tool"], p["derived"][:4]) for p in per if p["derived"] and not
                   (p["n_numeric_diff"] or p["other"] or p["env"])]
    within = not over and not other and not unexplained
    return dict(aligned=True, within_tolerance=within, max_rel_numeric=max([p["max_rel"] for p in per] or [0.0]),
                max_rel_by_tier=dict(
                    T64=max([0.0] + [p["max_rel"] for p in per if p["max_rel_path"] and
                                     tol_for(p["tool"], p["max_rel_path"]) == T64]),
                    T32=max([0.0] + [p["max_rel"] for p in per if p["max_rel_path"] and
                                     tol_for(p["tool"], p["max_rel_path"]) == T32])),
                n_numeric_differences=sum(p["n_numeric_diff"] for p in per),
                calls_with_numeric_differences=[(p["seq"], p["tool"], p["max_rel"], p["max_rel_path"])
                                                for p in per if p["n_numeric_diff"]],
                over_tolerance=over, non_numeric_differences=other,
                environment_fields=[(p["seq"], p["tool"], p["env"][:2]) for p in per if p["env"]],
                derived_differences=[(p["seq"], p["tool"], p["derived"][:4]) for p in per if p["derived"]],
                unexplained_derived=unexplained)


def header(recs):
    return next((r for r in recs if r.get("type") == "session"), {})


def file_sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def env_brief() -> dict:
    d = dict(python=sys.version.split()[0], platform=platform.platform(), machine=platform.machine())
    try:
        import torch
        d.update(torch=torch.__version__, cuda=torch.cuda.is_available(),
                 device=torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu")
    except Exception as ex:  # noqa: BLE001
        d["torch"] = f"unavailable: {ex}"
    try:
        import amm
        from amm import certify, tools
        d.update(code=tools.code_hash(), checker=certify.checker_hash(), mkl_cbwr=amm.MKL_CBWR_STATUS)
    except Exception as ex:  # noqa: BLE001
        d["amm"] = f"error: {ex}"
    return d


def jdump(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
