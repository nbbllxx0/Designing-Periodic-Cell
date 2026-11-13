"""V4 item 2 (+ item 3 fresh certificates): wall time per tool call through amm.tools.Session.call, the entry point
the agent harness and the MCP server use (mcp_server.py calls session.call(name, args, actor="agent")).

    python scripts/ops/gpulock_run.py v4 -- python scripts/verify/v4/latency.py

One fresh process, one session (profile C, schema amm-tools/2) in results/verification/v4/latency_session/.
Call 1 of each tool in the process is labelled cold (first CUDA use, first atlas load, first BoTorch import fall
into it). Per call: wall time around session.call and the dt_s the session log records.
- spec tools: set_material / set_constraints / set_target (cheap reference);
- check_bounds x6 and atlas_suggest x6 on the M05 spec (PA12, 10 mm cell, combined target);
- evaluate x6 with 1 design (6 designs over the 3 families) and x3 with 16 designs;
- screen_manufacturing x6 and export x6 (defaults: tiles 3, resolution 64) on the same 6 designs;
- search x6 at its default budget (32), one call per V3 primary target in V3 processing order (M13, S14, G06,
  S11, G07, S20), each with its material and normalized targets;
- certify x3 (tool defaults, as-built flag on): V3 certificates repeated on the current code (S20 / M4 schwarz_p
  sheet, static; G15 / M5 sphere_ligaments, gap; M05 / M4 sphere_ligaments, combined).
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

from amm import tools  # noqa: E402

V3 = common.ROOT / "results" / "verification" / "v3"
SESS = common.OUT / "latency_session"
RAWF = common.RAW / "latency_calls.jsonl"

DESIGNS = [dict(kind="gyroid", params=dict(density=0.25, mode="network")),
           dict(kind="schwarz_p", params=dict(density=0.276607, mode="sheet")),
           dict(kind="bcc", params=dict(r=0.08, R=0.0)),
           dict(kind="octet", params=dict(r=0.06, R=0.0)),
           dict(kind="cube_bars", params=dict(c=0.6, w=0.2)),
           dict(kind="sphere_ligaments", params=dict(c=0.345576, w=0.12838))]
SEARCH_TARGETS = ("M13", "S14", "G06", "S11", "G07", "S20")
CERTS = (("S20", "40162d320e841dc8"), ("G15", "00f03a71387fee8a"), ("M05", "8dc9a1fe3ba79ec2"))


def target_args(t: dict) -> dict:
    a = dict(clear=True)
    for k, v in t.items():
        if k == "gap":
            a["gap"] = dict(f_lo=v["f_lo"], f_hi=v["f_hi"], unit="f*")
        elif k.startswith("density") or k.startswith("nu100"):
            a[k] = v
        else:
            a[k] = dict(value=v, unit="E_s")
    return a


def batch16() -> list[dict]:
    out = []
    for i in range(6):
        out.append(dict(kind="gyroid", params=dict(density=round(0.15 + 0.05 * i, 3), mode="network")))
    for i in range(5):
        out.append(dict(kind="bcc", params=dict(r=round(0.05 + 0.015 * i, 3), R=0.0)))
    for i in range(5):
        out.append(dict(kind="cube_bars", params=dict(c=round(0.45 + 0.08 * i, 3), w=round(0.1 + 0.04 * i, 3))))
    return out


def main():
    if SESS.exists():
        shutil.rmtree(SESS)
    if RAWF.exists():
        RAWF.unlink()
    tg = {t["target_id"]: t for t in json.loads((V3 / "targets.json").read_text(encoding="utf-8"))["targets"]}
    t = time.perf_counter()
    s = tools.Session(SESS, profile="C")
    common.append_jsonl(RAWF, dict(tool="Session()", i=0, label="cold", wall_s=round(time.perf_counter() - t, 4),
                                   ok=True, env=common.env_record()))
    count: dict[str, int] = {}

    def call(name, args=None, note="", **extra):
        t0 = time.perf_counter()
        out = s.call(name, args or {}, actor="agent")
        wall = time.perf_counter() - t0
        i = count[name] = count.get(name, 0) + 1
        rec = dict(tool=name, i=i, label="cold" if i == 1 else "warm", wall_s=round(wall, 4), ok=out["ok"],
                   seq=out.get("seq"), note=note, error=None if out["ok"] else out["error"], **extra)
        r = out.get("result") or {}
        if name == "search":
            rec.update(found=r.get("found"), n_evaluations=r.get("n_evaluations"), arms=r.get("arms"))
        if name == "certify":
            rec.update(verdict=r.get("verdict"), spec_hash=r.get("spec_hash"), robust=r.get("robust"))
        if name in ("check_bounds",):
            rec.update(verdict=r.get("verdict"))
        if name in ("screen_manufacturing", "export"):
            rec.update(verdict=(r.get("screening") or r).get("verdict"))
        common.append_jsonl(RAWF, dict(rec, **common.mem()))
        print(f"{name:22s} #{i} {wall:8.2f} s ok={out['ok']} {note} {rec.get('error') or ''}", flush=True)
        return out

    m05 = tg["M05"]
    call("set_material", dict(name=m05["material"]), note="first atlas load (nu 0.39)")
    call("set_constraints", dict(cell_size=10.0, cell_size_unit="mm"))
    call("set_target", target_args(m05["targets"]), note="M05")
    for i in range(6):
        call("check_bounds", note="M05")
    for i in range(6):
        call("atlas_suggest", dict(top=5), note="M05")
    for d in DESIGNS:
        call("evaluate", dict(designs=[d]), note=f"1 design {d['kind']}", n_designs=1)
    for i in range(3):
        call("evaluate", dict(designs=batch16()), note="16 designs", n_designs=16)
    for d in DESIGNS:
        call("screen_manufacturing", dict(design=d), note=d["kind"])
    for d in DESIGNS:
        call("export", dict(design=d), note=d["kind"])
    for tid in SEARCH_TARGETS:
        t = tg[tid]
        call("set_material", dict(name=t["material"]), note=tid)
        o = call("set_target", target_args(t["targets"]), note=tid)
        norm = o["result"]["normalized"]
        same = json.dumps(norm, sort_keys=True) == json.dumps(t["targets"], sort_keys=True)
        call("search", {}, note=f"{tid} ({t['target_type']}, nu {t['nu']})", target_id=tid,
             target_type=t["target_type"], normalized_equal_v3=same)
    for tid, h in CERTS:
        t = tg[tid]
        v3c = json.loads((V3 / "certs" / f"{tid}_{h}.json").read_text(encoding="utf-8"))
        sp = v3c["spec"]
        call("set_material", dict(name=t["material"]), note=tid)
        o = call("set_target", target_args(t["targets"]), note=tid)
        same = json.dumps(o["result"]["normalized"], sort_keys=True) == json.dumps(t["targets"], sort_keys=True)
        call("certify", dict(design=dict(kind=sp["kind"], params=sp["params"])), note=f"{tid} repeat of V3 {h}",
             target_id=tid, v3_hash=h, normalized_equal_v3=same, v3_verdict=v3c["verdict"],
             v3_seconds=v3c["seconds"], v3_timing=v3c["timing"])
    # dt_s as logged by the session (time inside Session.call, includes validation and logging)
    logs = [json.loads(x) for x in (SESS / "session.jsonl").read_text(encoding="utf-8").splitlines()]
    dt = {r["seq"]: r["dt_s"] for r in logs if r.get("type") == "call"}
    recs = common.read_jsonl(RAWF)
    for r in recs:
        if r.get("seq") is not None:
            r["log_dt_s"] = dt.get(r["seq"])
    RAWF.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


if __name__ == "__main__":
    main()
