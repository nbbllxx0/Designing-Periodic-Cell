"""Recorded data served in mock mode: development session logs, their certificates, and the search atlas.

Only development data are indexed (smoke jobs, pilot B/C, probe C). The confirmatory E4 run (results/bench/e4) is
deliberately not read: its outcomes are scored blind by the frozen checker.

Nothing here imports amm; the current amm code hash is recomputed from the source bytes exactly as
amm.tools.code_hash does, so the GUI can tell whether a recorded session was written by the current code.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
ATLAS_DIR = RESULTS / "atlas"
SESSION_GLOBS = (
    ("smoke", "bench/smoke/jobs/*/session/session.jsonl"),
    ("pilot", "bench/pilot/*/*/session/session.jsonl"),
    ("probe", "probe/C/*/session/session.jsonl"),
)
NOT_HASHED = ("bench.py", "llm.py", "mcp_server.py", "cli.py")  # keep equal to amm.tools.NOT_HASHED
# The amm code that wrote E4 and the 18 smoke sessions (pre-B1, tool schema amm-tools/1). The current amm replays
# its logs exactly through the schema-1 projection (amm.tools.replay; results/software/NOTES_B1B3.md), so the mirror
# checks itself against them too ("replay_compatible").
V1_CONTRACT_CODES = ("90f3823f15cbeff4",)


def code_hash() -> str:
    """Same bytes and order as amm.tools.code_hash (reads amm/*.py, imports nothing)."""
    h = hashlib.sha256()
    for f in sorted((ROOT / "amm").glob("*.py")):
        if f.name in NOT_HASHED:
            continue
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def read_log(path: Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def _session_id(kind: str, p: Path) -> str:
    job = p.parent.parent  # .../<job>/session/session.jsonl
    if kind == "pilot":
        return f"pilot/{job.parent.name}/{job.name}"
    if kind == "probe":
        return f"probe/C/{job.name}"
    return f"smoke/{job.name}"


@lru_cache(maxsize=1)
def sessions() -> dict[str, dict]:
    """{id: meta} of every recorded development session (meta: path, profile, code, calls, decision, verdict,
    brief path, number of certificates)."""
    out = {}
    current = code_hash()
    for kind, pat in SESSION_GLOBS:
        for p in sorted(RESULTS.glob(pat)):
            try:
                recs = read_log(p)
            except (OSError, json.JSONDecodeError):
                continue
            head = next((r for r in recs if r.get("type") == "session"), {})
            calls = [r for r in recs if r.get("type") == "call"]
            sub = next((r for r in reversed(calls) if r["tool"] == "submit" and r["ok"]), None)
            job = p.parent.parent
            certs = sorted((p.parent / "certificates").glob("*.json"))
            sid = _session_id(kind, p)
            same = head.get("code") == current
            out[sid] = dict(id=sid, source=kind, path=str(p.relative_to(ROOT)).replace("\\", "/"),
                            profile=head.get("profile"), code=head.get("code"), same_code=same,
                            schema=head.get("schema_version") or head.get("schema") or "amm-tools/1",
                            replay_compatible=bool(same or head.get("code") in V1_CONTRACT_CODES),
                            n_calls=len(calls), tools=sorted({c["tool"] for c in calls}),
                            decision=(sub or {}).get("args", {}).get("decision"),
                            verdict=(sub or {}).get("args", {}).get("verdict"),
                            n_certificates=len(certs),
                            brief=str((job / "prompt.txt").relative_to(ROOT)).replace("\\", "/")
                            if (job / "prompt.txt").is_file() else None)
    return out


def session_path(sid: str) -> Path:
    meta = sessions().get(sid)
    if meta is None:
        raise KeyError(sid)
    return ROOT / meta["path"]


def brief_text(sid: str) -> str | None:
    """The user request of a recorded session (the 'Request:' part of prompt.txt), if there is one."""
    meta = sessions().get(sid)
    if not meta or not meta["brief"]:
        return None
    txt = (ROOT / meta["brief"]).read_text(encoding="utf-8")
    return txt.split("Request:", 1)[1].strip() if "Request:" in txt else txt.strip()


@lru_cache(maxsize=1)
def certificate_files() -> dict[str, Path]:
    """{cert_key: path} of every recorded certificate (file name <spec_hash>_<cert_key>.json)."""
    out = {}
    for _, pat in SESSION_GLOBS:
        for p in RESULTS.glob(pat):
            for c in sorted((p.parent / "certificates").glob("*_*.json")):
                out.setdefault(c.stem.split("_", 1)[1], c)
    return out


def certificate(cert_key: str) -> dict | None:
    p = certificate_files().get(cert_key)
    return json.loads(p.read_text(encoding="utf-8")) if p else None


# ---- atlas -----------------------------------------------------------------------------------------------------
KEEP = ("spec", "density", "C11", "C12", "C44", "E100", "nu100", "G", "bulk", "zener", "cubic_deviation", "min_eig",
        "valid", "gaps", "best_rel_gap", "bands", "bloch_valid", "percolates", "nu")


@lru_cache(maxsize=4)
def atlas(nu: float) -> list[dict] | None:
    """Atlas rows at this Poisson ratio (results/atlas/atlas_nu<nu>.jsonl), or None. ~16 MB per file, loaded once."""
    p = ATLAS_DIR / f"atlas_nu{nu:g}.jsonl"
    if not p.is_file():
        return None
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                rows.append({k: r.get(k) for k in KEEP})
    return rows


def atlas_rows_exist(nu: float) -> bool:
    """What amm.tools.atlas_rows(nu) is not None tests: the atlas file for this Poisson ratio exists."""
    return (ATLAS_DIR / f"atlas_nu{nu:g}.jsonl").is_file()


def atlas_nus() -> list[float]:
    out = []
    for p in sorted(ATLAS_DIR.glob("atlas_nu*.jsonl")):
        try:
            out.append(float(p.stem[len("atlas_nu"):]))
        except ValueError:
            pass
    return out


def nearest_atlas_row(kind: str, params: dict, nu: float) -> tuple[dict, float] | None:
    """The atlas row of the same kind (and TPMS mode) nearest in parameters, with the max-abs parameter distance."""
    rows = atlas(nu)
    if rows is None:
        return None
    mode = params.get("mode")
    num = {k: float(v) for k, v in params.items() if k != "mode"}
    best, bd = None, float("inf")
    for r in rows:
        sp = r["spec"]
        if sp["kind"] != kind or sp["params"].get("mode") != mode:
            continue
        d = max((abs(float(sp["params"][k]) - v) for k, v in num.items() if k in sp["params"]), default=0.0)
        if d < bd:
            best, bd = r, d
    return (best, bd) if best is not None else None


def atlas_points(nu: float, limit: int | None = None) -> list[dict]:
    """Compact atlas map data: kind, family, params, density, E100, best relative gap (search tier)."""
    rows = atlas(nu) or []
    out = [dict(kind=r["spec"]["kind"], family=r["spec"]["family"], params=r["spec"]["params"],
                density=r["density"], E100=r["E100"], best_rel_gap=r.get("best_rel_gap") or 0.0)
           for r in rows if r.get("valid")]
    return out[:limit] if limit else out
