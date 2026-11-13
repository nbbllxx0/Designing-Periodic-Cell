"""V10: collect the replay results into results/verification/v10/replays.json, replays.csv and T15_v10.csv.

    python scripts/verify/v10/build_tables.py

Inputs (all written by V10): raw/<set>/*.json (replay_set.py, Windows), linux_out raw/xenv_linux/*.json (copied
into raw/xenv_linux by the operator), b1b3_reference_v10.json (smoke replays and the 132-entry bit identity),
logs/release_reference_compare.txt; cited, not rerun: results/verification/v2/replays.csv.
CAUSES: causes of non-exact replays, filled in after inspection (NOTES section 4), keyed by set and log.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v10lib as L  # noqa: E402

OUT = L.OUT
GROUP = {"e4_frozen": "1 frozen E4", "e4_targeted": "1b frozen E4 (targeted)", "release_v6": "2 final release",
         "release_tutorial": "2 final release", "release_gui": "2 final release", "release_smoke": "2 final release",
         "probe_old": "2b older-code probes (optional)", "xenv_linux": "3 cross-environment"}
ENVS = {"xenv_linux": "Linux container (python:3.12-slim, WSL2), CPU only"}
CAUSES: dict[tuple[str, str], str] = {}
OVERRIDE: dict[tuple[str, str], str] = {}  # classification after a recorded diagnostic (NOTES section 5)
CAUSES_FILE = OUT / "causes.json"
if CAUSES_FILE.is_file():
    for c in json.loads(CAUSES_FILE.read_text(encoding="utf-8")):
        CAUSES[(c["set"], c["log"])] = c["cause"]
        if c.get("classification"):
            OVERRIDE[(c["set"], c["log"])] = c["classification"]


def classify(set_name, rep, tol, err, log=None):
    if (set_name, log) in OVERRIDE:
        return OVERRIDE[(set_name, log)]
    if err or rep is None:
        return "differing"
    if rep["exact"] and not rep.get("decision_changes"):
        return "exact"
    if set_name == "xenv_linux" and tol and tol.get("within_tolerance"):
        return "within tolerance"
    return "differing"


def rows_from_raw():
    rows, full = [], []
    for f in sorted((OUT / "raw").glob("*/*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        rep, tol, h = d.get("replay"), d.get("tolerance"), d.get("header", {})
        s = d["set"]
        log = d["log"]
        cls = classify(s, rep, tol, d.get("error"), log)
        mm = rep["mismatches"] if rep else []
        row = dict(group=GROUP.get(s, s), set=s, log=log, environment=ENVS.get(s, "Windows 11, amm env, RTX 4090"),
                   code_log=h.get("code"), schema_log=h.get("schema_version") or h.get("schema"),
                   profile=h.get("profile"), code_now=d["env"].get("code"), checker_now=d["env"].get("checker"),
                   n_calls=d["n_calls"], n_compared=rep["n_compared"] if rep else None,
                   n_certify=d["n_certify"], n_search=d["n_search"], n_export=d["n_export"],
                   exact=bool(rep and rep["exact"]), n_mismatches=len(mm),
                   mismatches=";".join(f"{m['seq']}:{m['tool']}:{m['field']}" for m in mm),
                   decision_changes=len(rep.get("decision_changes", [])) if rep else None,
                   code_aliased=rep["identity"]["code_aliased"] if rep else None,
                   checker_aliased=rep["identity"]["checker_aliased"] if rep else None,
                   within_tolerance=tol.get("within_tolerance") if tol else None,
                   max_rel_T64=tol.get("max_rel_by_tier", {}).get("T64") if tol else None,
                   max_rel_T32=tol.get("max_rel_by_tier", {}).get("T32") if tol else None,
                   n_numeric_differences=tol.get("n_numeric_differences") if tol else None,
                   classification=cls, cause=CAUSES.get((s, log), "" if cls == "exact" else "(not yet assigned)"),
                   seconds=d["seconds"], logged_tool_seconds=d["logged_tool_seconds"], error=(d.get("error") or "")[:200])
        rows.append(row)
        full.append(dict(row, replay=rep, tolerance=tol, env=d["env"], log_sha256=d["log_sha256"]))
    return rows, full


def rows_from_reference():
    p = OUT / "b1b3_reference_v10.json"
    if not p.is_file():
        return [], [], None
    ref = json.loads(p.read_text(encoding="utf-8"))
    rows, full = [], []
    for job, r in sorted(ref.get("replay", {}).items()):
        log = f"results/bench/smoke/jobs/{job}/session/session.jsonl"
        hd = next(json.loads(l) for l in (L.ROOT / log).read_text(encoding="utf-8").splitlines() if l.strip())
        ex = r.get("extra", {})
        cls = "exact" if r["exact"] and not ex.get("decision_changes") else "differing"
        row = dict(group=GROUP["release_smoke"], set="release_smoke", log=log, environment="Windows 11, amm env, RTX 4090",
                   code_log=hd.get("code"), schema_log=hd.get("schema_version") or hd.get("schema"),
                   profile=hd.get("profile"), code_now=ref["identity"]["code"], checker_now=ref["identity"]["checker"],
                   n_calls=r["n_calls"], n_compared=r["n_compared"], n_certify=None, n_search=None, n_export=None,
                   exact=r["exact"], n_mismatches=len(r["mismatches"]),
                   mismatches=";".join(f"{m['seq']}:{m['tool']}:{m['field']}" for m in r["mismatches"]),
                   decision_changes=len(ex.get("decision_changes", [])),
                   code_aliased=ex.get("identity", {}).get("code_aliased"),
                   checker_aliased=ex.get("identity", {}).get("checker_aliased"), within_tolerance=None,
                   max_rel_T64=None, max_rel_T32=None, n_numeric_differences=None, classification=cls,
                   cause=CAUSES.get(("release_smoke", log), ""), seconds=r["seconds"], logged_tool_seconds=None,
                   error="")
        rows.append(row)
        full.append(dict(row, replay=r))
    return rows, full, ref


def main():
    rows, full = rows_from_raw()
    r2, f2, ref = rows_from_reference()
    rows += r2
    full += f2
    order = list(GROUP)
    rows.sort(key=lambda r: (order.index(r["set"]) if r["set"] in order else 99, r["log"]))
    L.jdump(full, OUT / "replays.json")
    with open(OUT / "replays.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    # T15: one row per set, plus the bit-identity reference and the cited V2 replays
    t15 = []
    for s in order:
        rs = [r for r in rows if r["set"] == s]
        if not rs:
            continue
        codes = sorted({r["code_log"] or "-" for r in rs})
        n_ex = sum(r["classification"] == "exact" for r in rs)
        n_tol = sum(r["classification"] == "within tolerance" for r in rs)
        dif = [r for r in rs if r["classification"] == "differing"]
        t15.append(dict(group=GROUP[s], set=s, source_code=" ".join(codes),
                        schemas=" ".join(sorted({r["schema_log"] or "-" for r in rs})),
                        replay_code=rs[0]["code_now"], data="amm-data/1 (de79a79e98e88731)",
                        environment=rs[0]["environment"], criterion="tolerance (NOTES 1.4)" if s == "xenv_linux" else "exact",
                        sessions=len(rs), calls=sum(r["n_compared"] or 0 for r in rs), exact=n_ex, within_tolerance=n_tol,
                        differing=len(dif),
                        differing_causes="; ".join(f"{Path(r['log']).parts[-3] if r['log'].endswith('session/session.jsonl') else Path(r['log']).parent.name}: {r['cause']}" for r in dif),
                        max_rel_T64=max([r["max_rel_T64"] or 0 for r in rs]) if s == "xenv_linux" else "",
                        max_rel_T32=max([r["max_rel_T32"] or 0 for r in rs]) if s == "xenv_linux" else "",
                        replay_seconds=round(sum(r["seconds"] or 0 for r in rs), 1), note=""))
    if ref is not None:
        cmp_txt = (OUT / "logs" / "release_reference_compare.txt").read_text(encoding="utf-8")
        m = re.search(r"arrays/dicts compared: (\d+)", cmp_txt)
        d = re.search(r"DIFFERENT: (.*)", cmp_txt)
        t15.append(dict(group="2 final release", set="release_reference (bit identity)", source_code="5970bf55108f1584 (b1b3_reference_final.json)",
                        schemas="-", replay_code=ref["identity"]["code"], data="amm-data/1 (de79a79e98e88731)",
                        environment="Windows 11, amm env, RTX 4090", criterion="exact",
                        sessions="", calls="", exact=int(m.group(1)) if m and d and d.group(1).strip() == "none" else "",
                        within_tolerance="", differing=0 if d and d.group(1).strip() == "none" else d.group(1) if d else "",
                        differing_causes="", max_rel_T64="", max_rel_T32="", replay_seconds="",
                        note=f"{m.group(1) if m else '?'} entries compared; DIFFERENT: {d.group(1).strip() if d else '?'}; checker field and timing excluded"))
    v2 = list(csv.DictReader(open(L.ROOT / "results/verification/v2/replays.csv", encoding="utf-8")))
    t15.append(dict(group="2 final release (cited)", set="V2 acceptance matrix", source_code="f1a6d625064a6d18",
                    schemas="amm-tools/2 amm-tools/3", replay_code="f1a6d625064a6d18", data="amm-data/1 (de79a79e98e88731)",
                    environment="Windows 11, amm env, RTX 4090", criterion="exact", sessions=len(v2),
                    calls=sum(int(x["n_compared"] or 0) for x in v2), exact=sum(x["exact"] == "True" for x in v2),
                    within_tolerance=0, differing=sum(x["exact"] != "True" for x in v2),
                    differing_causes="probe logs written before fixes V2-2..V2-4 (results/software/NOTES_V2_fixes.md)",
                    max_rel_T64="", max_rel_T32="", replay_seconds=round(sum(float(x["seconds"] or 0) for x in v2), 1),
                    note="results/verification/v2/replays.csv; not rerun by V10"))
    with open(OUT / "T15_v10.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(t15[0]))
        w.writeheader()
        w.writerows(t15)
    for r in t15:
        print(r["set"], r["sessions"], r["exact"], r["within_tolerance"], r["differing"], r["replay_seconds"], r["differing_causes"][:150])
    return 0


if __name__ == "__main__":
    sys.exit(main())
