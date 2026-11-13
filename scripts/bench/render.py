"""Render benchmark briefs (bench/v1/briefs/<id>.json) from plan.json and the truth work files (build.py).

The text states exactly the intended request (values as rounded for the certificate). Ambiguous briefs reuse the
paired brief's intended spec and drop or blur one item; the oracle states that item when the agent asks.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from build import AMBIG, CANARY, MAT_TEXT  # noqa: E402  (same directory)

QNAME = {"E100_min": "Young's modulus along the cube axes", "G_min": "shear modulus (C44)",
         "bulk_min": "bulk modulus"}
STIFF_TXT = {"E100_min": ["a Young's modulus along the cube axes of at least {v}",
                          "an axial Young's modulus (x, y and z) of at least {v}",
                          "E along [100] of at least {v}"],
             "G_min": ["a shear modulus C44 of at least {v}", "a cubic shear stiffness (C44) of at least {v}"],
             "bulk_min": ["a bulk modulus of at least {v}", "a bulk modulus K of no less than {v}"]}
GAP_TXT = ["a complete elastic band gap (all directions and polarizations) from {lo} to {hi}",
           "a full 3D band gap that blocks every elastic wave between {lo} and {hi}",
           "a complete band gap covering {lo} to {hi}"]
GAP_VAGUE = ["to stop vibrations between {lo} and {hi}", "a band gap between {lo} and {hi}",
             "to suppress elastic waves from {lo} to {hi}"]
OPEN = ["I need a periodic lattice unit cell{mat}{cell} with {reqs}.",
        "Please design a periodic unit cell{mat}{cell}. Requirements: {reqs}.",
        "We are designing a lattice core{mat}{cell}. It needs {reqs}.",
        "Design a metamaterial unit cell{mat}{cell} that has {reqs}."]


def _num(v) -> str:
    return f"{v:g}"


def _q(v, drop_unit=False) -> str:
    return _num(v[0]) if drop_unit else f"{_num(v[0])} {v[1]}"


def _pct(x) -> str:
    return _num(round(100 * x, 2)) + " %"


def text_of(intended: dict, seed: int, omit: str | None = None) -> str:
    rng = random.Random(seed)
    t = intended["targets"]
    reqs = []
    if "density_min" in t:
        reqs.append(f"a solid fraction of at least {_pct(t['density_min'])}")
    if "density_max" in t:
        reqs.append(rng.choice([f"a solid fraction of at most {_pct(t['density_max'])}",
                                f"a relative density of no more than {_pct(t['density_max'])}",
                                f"at most {_pct(t['density_max'])} solid by volume"]))
    for k in ("E100_min", "G_min", "bulk_min"):
        if k in t:
            v = _q(t[k], drop_unit=omit == "unit")
            reqs.append(f"a stiffness of at least {v}" if omit == "quantity" else rng.choice(STIFF_TXT[k]).format(v=v))
    if "nu100_max" in t:
        reqs.append(f"a Poisson ratio along the cube axes of at most {_num(t['nu100_max'])}")
    if "nu100_min" in t:
        reqs.append(f"a Poisson ratio along the cube axes of at least {_num(t['nu100_min'])}")
    if "gap" in t:
        g = t["gap"]
        hi = _q(g["f_hi"], drop_unit=omit == "unit")
        if g["f_lo"][0] == 0:
            reqs.append(f"a complete band gap that blocks all elastic waves below {hi}")
        else:
            lo = _q(g["f_lo"], drop_unit=omit == "unit")
            reqs.append(rng.choice(GAP_VAGUE if omit == "gap_type" else GAP_TXT).format(lo=lo, hi=hi))
    reqs_s = reqs[0] if len(reqs) == 1 else ", ".join(reqs[:-1]) + " and " + reqs[-1]
    mat = "" if omit == "material" else " in " + rng.choice(MAT_TEXT[intended["material"]])
    cs = intended.get("cell_size")
    cell = "" if (cs is None or omit == "cell_size") else rng.choice(
        [f" with a {_num(cs[0])} {cs[1]} cell", f" (cell size {_num(cs[0])} {cs[1]})", f", {_num(cs[0])} {cs[1]} cells"])
    return rng.choice(OPEN).format(mat=mat, cell=cell, reqs=reqs_s)


def facts_of(intended: dict, omit: str | None) -> str:
    t = intended["targets"]
    if omit == "material":
        return f"It will be printed in {MAT_TEXT[intended['material']][0]}."
    if omit == "cell_size":
        cs = intended["cell_size"]
        return f"The unit cell is {_num(cs[0])} {cs[1]}."
    if omit == "quantity":
        k = next(k for k in QNAME if k in t)
        return f"I mean the {QNAME[k]}."
    if omit == "unit":
        u = t["gap"]["f_lo"][1] if "gap" in t else next(t[k][1] for k in QNAME if k in t)
        return f"The values are in {u}."
    if omit == "gap_type":
        return "It must be a complete gap: all directions and all polarizations."
    return "Everything I need is in the request."


def render(out: Path):
    P = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    bdir = out / "briefs"
    bdir.mkdir(parents=True, exist_ok=True)
    done, missing = {}, []
    for bid, b in P["briefs"].items():
        if bid[0] in "SGM":
            wf = out / "work" / f"{bid}.json"
            w = json.loads(wf.read_text(encoding="utf-8")) if wf.exists() else None
            if not w or not w["final"]:
                missing.append(bid)
                continue
            f = w["final"]
            intended = dict(material=b["material"], cell_size=b["cell_size"], targets=f["request"])
            if b["gap"]:
                intended["gap_type"] = "complete"
            truth = dict(decision="release", witness=f["spec"], normalized=f["normalized"], certificate="certified",
                         passes=f["passes"], difficulty=b["difficulty"])
            src = (f"witness {f['spec']['kind']} {json.dumps(f['spec']['params'])} certified against the stated "
                   f"request (bench/v1/work/{bid}.json, pass {f['passes']})")
        elif bid[0] in "XN":
            intended, truth = b["intended"], b["truth"]
            src = ("rigorous bound violated: " + "; ".join(v["statement"] for v in truth["violated"])
                   if bid[0] == "X" else "atlas oracle NOT_FOUND_IN_FAMILIES for targets relaxed by 10 %; "
                                         "bounds not violated (not a proof)")
        else:
            continue
        done[bid] = dict(id=bid, cls=b["cls"], canary=CANARY, text=text_of(intended, b["text_seed"]),
                         intended=intended, oracle=dict(facts=facts_of(intended, None)),
                         expected=dict(decision=truth["decision"], **({"verdict": truth["verdict"]}
                                                                      if "verdict" in truth else {})),
                         truth=truth, truth_source=src, pilot=bid in P["pilot"])
    for wf in sorted((out / "work").glob("R*.json")):  # near-miss briefs (nearmiss.py)
        w = json.loads(wf.read_text(encoding="utf-8"))
        bid = w["id"]
        src = (f"near miss: the nominal search value of the best cell clears the target by {100 * w['nominal_slack']:.1f} % "
               f"(median-corrected: {100 * w['expected_slack']:+.1f} %), "
               f"but all {len(w['proof'])} candidates (atlas cells whose search value reaches it, and the top 3 of a "
               f"nominal search) are refuted at the certificate's top rung (64, 80, 96) (bench/v1/work/{bid}.json); designs "
               f"between grid points not visited by the search are not covered")
        feasible = w["truth"]["decision"] == "release"  # corrected label: a certified design was found later
        if feasible:
            src = w["truth"]["correction"]
        done[bid] = dict(id=bid, cls="nearmiss_feasible" if feasible else "infeasible_nearmiss", canary=CANARY,
                         text=text_of(w["intended"], int(bid[1:]) * 7919), intended=w["intended"],
                         oracle=dict(facts=facts_of(w["intended"], None)),
                         expected=dict(decision="release") if feasible else
                         dict(decision="refuse", verdict="NOT_FOUND_IN_FAMILIES"), truth=w["truth"],
                         truth_source=src, pilot=False)
    for bid, (base, what) in AMBIG.items():
        if base not in done:
            missing.append(bid)
            continue
        bb = done[base]
        intended = json.loads(json.dumps(bb["intended"]))
        done[bid] = dict(id=bid, cls=f"ambiguous_{what}", canary=CANARY,
                         text=text_of(intended, P["briefs"][bid]["text_seed"], omit=what), intended=intended,
                         oracle=dict(facts=facts_of(intended, what), missing=what), missing=what, pair_of=base,
                         expected=dict(decision="ask_then_" + bb["expected"]["decision"],
                                       **({"verdict": bb["expected"]["verdict"]} if "verdict" in bb["expected"] else {})),
                         truth=bb["truth"], truth_source=f"paired with {base}: " + bb["truth_source"],
                         pilot=bid in P["pilot"])
    for bid, d in done.items():
        (bdir / f"{bid}.json").write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    man = dict(canary=CANARY, n=len(done), ids=sorted(done), missing=sorted(missing), pilot=P["pilot"])
    (out / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    print("rendered", len(done), "briefs; missing truth:", sorted(missing))
