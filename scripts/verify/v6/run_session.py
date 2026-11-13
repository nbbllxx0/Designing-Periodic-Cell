"""Run one V6 design session through the library Session (the calls the GUI and the agent make), profile C.

    python scripts/verify/v6/run_session.py <config.json>

config keys: root (session dir, overwritten), material, cell_size_mm, targets (set_target arguments), gap_type,
note, top (atlas_suggest top, default 5), certify_max (default 3), candidates (optional explicit design list: then
atlas_suggest is still called for the record, but the candidates are evaluated and certified instead),
export (dict: tiles, resolution, tile_resolution).

Rule (NOTES.md 1.4): certify the designs in order until one is certified, at most certify_max calls; release the
certified one; otherwise refuse with the certificates as evidence. Then screen_manufacturing and export of the
released design (or of the first certified-for-nothing candidate, reported as not certified).
Writes <root>/summary.json.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import amm  # noqa: F401  (amm before torch)
from amm import tools


def main(cfg_path: str) -> int:
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    root = Path(cfg["root"])
    if root.exists():
        shutil.rmtree(root)
    t0 = time.perf_counter()
    s = tools.Session(root, profile="C")
    summ = dict(config=cfg, calls={}, certify=[], t_start=time.strftime("%Y-%m-%d %H:%M:%S"))

    def call(name, args=None, key=None):
        t = time.perf_counter()
        out = s.call(name, args or {})
        dt = round(time.perf_counter() - t, 2)
        print(f"[{out['seq']}] {name} ok={out['ok']} {dt:.1f}s"
              + ("" if out["ok"] else f" ERROR {out['error']}"), flush=True)
        if key:
            summ["calls"][key] = dict(ok=out["ok"], seq=out["seq"], seconds=dt,
                                      **(dict(result=out["result"]) if out["ok"] else dict(error=out["error"])))
        return out

    call("set_material", {"name": cfg["material"]}, "set_material")
    call("set_constraints", {"cell_size": cfg["cell_size_mm"], "cell_size_unit": "mm"}, "set_constraints")
    tg = dict(cfg["targets"])
    if cfg.get("gap_type"):
        tg["gap_type"] = cfg["gap_type"]
    assert call("set_target", tg, "set_target")["ok"]
    for k in ["material", "cell_size"] + [k for k in cfg["targets"] if k not in ("gap_type", "clear")]:
        call("set_source", {"key": k, "source": "stated", "note": cfg.get("note", "V6 requirement")})
    call("check_bounds", {}, "check_bounds")
    sug = call("atlas_suggest", {"top": cfg.get("top", 5)}, "atlas_suggest")
    designs = cfg.get("candidates") or [x["design"] for x in sug["result"]["best"]]
    ev = call("evaluate", {"designs": designs, "bands": True}, "evaluate")
    chosen, cert = None, None
    for d in designs[:cfg.get("certify_max", 3)]:
        t = time.perf_counter()
        c = s.call("certify", {"design": d})
        dt = round(time.perf_counter() - t, 1)
        r = c.get("result") or {}
        print(f"[{c['seq']}] certify {d}: {r.get('verdict')} robust={r.get('robust')} {dt}s"
              + ("" if c["ok"] else f" ERROR {c['error']}"), flush=True)
        summ["certify"].append(dict(design=d, ok=c["ok"], seq=c["seq"], seconds=dt,
                                    **(dict(result=r) if c["ok"] else dict(error=c["error"]))))
        if c["ok"] and r.get("verdict") == "certified":
            chosen, cert = d, r
            break
    if chosen is not None:
        call("submit", {"decision": "release", "design": chosen, "note": cfg.get("note", "")}, "submit")
        target = chosen
    else:
        verdicts = [x.get("result", {}).get("verdict") for x in summ["certify"]]
        v = "UNDETERMINED" if "undetermined" in verdicts else "OTHER"
        call("submit", {"decision": "refuse", "verdict": v, "note": "no candidate certified within the rule"},
             "submit")
        target = designs[0]
    ex = cfg.get("export", {})
    call("screen_manufacturing", {"design": target, "tiles": ex.get("tiles", 3),
                                  "resolution": ex.get("resolution", 64)}, "screen_manufacturing")
    call("export", {"design": target, "tiles": ex.get("tiles", 3), "resolution": ex.get("resolution", 64),
                    "tile_resolution": ex.get("tile_resolution", 32)}, "export")
    call("get_session", {}, "get_session")
    summ["released"] = chosen
    summ["certificate_summary"] = cert
    summ["seconds_total"] = round(time.perf_counter() - t0, 1)
    summ["t_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (root / "summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    print(f"released {chosen}; total {summ['seconds_total']} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
