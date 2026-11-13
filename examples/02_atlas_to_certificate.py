"""Tutorial (b): find a design for a stiffness target from the search atlas, then certify it and release it.

    python examples/02_atlas_to_certificate.py [--out DIR]

Steps (profile C, the full system):
  1. state the request in physical units: PA12 (SLS), 10 mm cell, E100 >= 25 MPa, solid fraction <= 0.25;
  2. `check_bounds`: rigorous bounds (Voigt, cubic stability) and the atlas verdict (search tier, not a proof);
  3. `atlas_suggest`: the precomputed atlas cells closest to the targets (no solve);
  4. `evaluate`: search-tier check of the suggestions (fast, NOT a certificate);
  5. `certify`: the acceptance tier for the best suggestion (static targets only, so no Bloch block; about
     1-3 min on CPU);
  6. `submit(release)`: accepted only because a certificate with verdict "certified" is held for this design and
     these targets.
The session log (session.jsonl) and the full certificate are written to --out, so the run can be replayed without
any LLM: `amm.tools.replay(<out>/session.jsonl)`.

Needs the search atlas and error-model files (results/atlas in a source checkout; see docs/data.md).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import amm  # noqa: F401  (import amm before torch)
from amm import tools

HERE = Path(__file__).resolve().parent


def show(label, out, keys=None):
    if not out["ok"]:
        print(f"[{out.get('seq')}] {label}: ERROR {out['error']}")
        return out
    r = out["result"]
    body = {k: r[k] for k in keys if k in r} if keys else r
    print(f"[{out['seq']}] {label}: {json.dumps(body, default=str)[:900]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "outputs" / "02_session"), help="session directory (overwritten)")
    a = ap.parse_args()
    out_dir = Path(a.out)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    t0 = time.perf_counter()
    s = tools.Session(out_dir, profile="C")
    c = s.call

    show("set_material", c("set_material", {"name": "PA12"}), ["material", "E_Pa", "nu", "atlas_available"])
    show("set_constraints", c("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"}))
    show("set_target", c("set_target", {"E100_min": {"value": 25, "unit": "MPa"}, "density_max": 0.25}),
         ["targets", "normalized"])
    for k in ("material", "cell_size", "E100_min", "density_max"):
        c("set_source", {"key": k, "source": "stated", "note": "tutorial request"})

    b = show("check_bounds", c("check_bounds"), ["verdict", "bounds_verdict", "violated"])
    if b["ok"]:
        at = b["result"]["atlas"]
        print(f"     atlas: {at['verdict']}, {at['n_clear']} of {at['n_cells']} cells clear the targets at the "
              "pessimistic end of the calibrated error range")

    sug = show("atlas_suggest", c("atlas_suggest", {"top": 3}), ["tier"])
    if not sug["ok"]:
        print("the atlas is not available: see docs/data.md (AMM_DATA_DIR)")
        return 1
    best = sug["result"]["best"]
    for i, x in enumerate(best):
        print(f"     #{i + 1} {x['design']}  slack nominal {x['slack_nominal']:+.3f}, pessimistic {x['slack_pess']:+.3f}")

    ev = c("evaluate", {"designs": [x["design"] for x in best]})
    assert ev["ok"], ev
    print(f"[{ev['seq']}] evaluate ({ev['result']['tier']}):")
    for x in ev["result"]["results"]:
        print(f"     {x['design']}: density {x['density']:.4f}, E100 {x['E100_MPa']:.1f} MPa, "
              f"G {x['G_MPa']:.1f} MPa, Zener {x['derived']['zener']:.3f}")

    design = best[0]["design"]
    t1 = time.perf_counter()
    cert = c("certify", {"design": design})
    t_cert = time.perf_counter() - t1
    assert cert["ok"], cert
    cr = cert["result"]
    print(f"[{cert['seq']}] certify {design}: verdict {cr['verdict']} (outcome {cr['outcome']}), robust "
          f"{cr['robust']}, {t_cert:.0f} s")
    print(f"     static rung {cr['static']['rung']}, guarded bounds (normalized by E_s):")
    for q, v in cr["static"]["bounds"].items():
        print(f"       {q:8s} [{v['lower']:.5g}, {v['upper']:.5g}]")
    print(f"     E100 lower bound {cr.get('E100_MPa', float('nan')):.1f} MPa vs target 25 MPa; as-built "
          f"(+-0.01 a = 0.1 mm): {cr.get('as_built')}")

    sub = c("submit", {"decision": "release", "design": design, "note": "tutorial 02"})
    if sub["ok"]:
        card = sub["result"]["outcome_card"]
        print(f"[{sub['seq']}] submit release: outcome {card['outcome']} ({card['title']})")
    else:
        print(f"[{sub['seq']}] submit release rejected: {sub['error']}")
        ref = c("submit", {"decision": "refuse", "verdict": "OTHER", "note": "certificate did not accept"})
        show("submit refuse", ref, ["outcome_card"])

    print(f"\nsession log: {out_dir / 'session.jsonl'}")
    print(f"certificates: {sorted(p.name for p in (out_dir / 'certificates').glob('*.json'))}")
    print(f"total {time.perf_counter() - t0:.0f} s (certify {t_cert:.0f} s)")
    print("summary:", json.dumps(dict(design=design, verdict=cr["verdict"], robust=cr["robust"],
                                      outcome=(sub["result"]["outcome_card"]["outcome"] if sub["ok"] else None),
                                      seconds_certify=round(t_cert), seconds_total=round(time.perf_counter() - t0))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
