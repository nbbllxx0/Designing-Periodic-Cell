"""V13 (audit-loop round 3, 2026-11-09): discrimination of the checker on claims near the reference limit
(theory reviewer #1, editor #5).

The 50 verification cells set every claim 5 % inside a first-pass reference, so the checker had almost no chance
to certify a false claim. Here the stored guard bounds of each cell are re-scored against claims moved to a
distance d of the converged reference bracket, on both sides:
  true claim   minimum: t = bracket_lo (1 - d);  maximum: t = bracket_hi (1 + d)
  false claim  minimum: t = bracket_hi (1 + d);  maximum: t = bracket_lo (1 - d)
for d in {0.5, 1, 2, 3, 5} %. The bracket is the reference interval of results/g2/classification_v3.json (amm
at resolutions at least as fine as the certificate, extrapolated; its truth is relative to that reference).

Static (E100_min, G_min, density_max on every cell that carries the claim): the checker verdict is
amm.certify.static_verdict on the stored guard bounds of the rung the certificate used (results/g2/rerun_v3; the feature rule of 2026-11-09 changes none of\nthese static blocks);
a finer rung could decide more claims, so this undercounts the checker's certifications, not its errors.
The naive rule accepts a claim when the finest computed value (phase mean at the finest resolution of that
rung) meets it: one fine solve, no guard.

Gap (cells whose stored report has three-resolution edges): true claim [lo_hi (1 + d), up_lo (1 - d)];
false claims extend one end beyond the reference edge bracket by d. The checker certifies when the claim lies
inside the safe interval of the released edge guard, re-applied to the stored edges (the counts at the sampled wave vectors then hold by construction, since the
safe edges bound every computed edge). The naive rule accepts when the claim lies inside the edges at the finest
resolution over the same 37 wave vectors.

    python scripts/experiments/v13_near_threshold.py
Writes results/verification/v13/near_threshold.json. CPU only, seconds, no LLM.
"""
import collections
import glob
import json
from pathlib import Path

import amm  # noqa: F401
from amm import certify

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/verification/v13"
DS = (0.005, 0.01, 0.02, 0.03, 0.05)
STATIC = {"E100_min": ("E100", "min"), "G_min": ("G", "min"), "density_max": ("density", "max")}


def main():
    truth = {(r["kind"], json.dumps(r["params"], sort_keys=True)): r
             for r in json.loads((ROOT / "results/g2/classification_v3.json").read_text())}
    rows = []
    for f in sorted(glob.glob(str(ROOT / "results/g2/rerun_v3/*.json"))):
        r3 = json.loads(Path(f).read_text())
        spec = r3["spec"]
        t = truth.get((spec["kind"], json.dumps(spec["params"], sort_keys=True)))
        if t is None:
            continue
        st = r3["static"]
        conv = st.get("convergence")
        for key, (q, kind) in STATIC.items():
            cl = t["claims"].get(key)
            if cl is None or cl.get("bracket") is None:
                continue
            lo, hi = cl["bracket"]
            for d in DS:
                for tr in ("true", "false"):
                    if kind == "min":
                        tgt = lo * (1 - d) if tr == "true" else hi * (1 + d)
                    else:
                        tgt = hi * (1 + d) if tr == "true" else lo * (1 - d)
                    v = certify.static_verdict(conv, {key: tgt}, bool(st.get("numerics_ok")))["targets"][key]
                    finest = conv[q]["means"][-1] if conv else None
                    naive = None if finest is None else bool(finest >= tgt if kind == "min" else finest <= tgt)
                    rows.append(dict(cell=Path(f).stem, kind=spec["kind"], block="static", key=key, d=d, truth=tr,
                                     checker=v, naive_accept=naive))
        b = r3.get("bloch") or {}
        if b.get("convergence"):  # the released edge guard (round-3 rules), re-applied to the stored edges
            b = certify.rescore_bloch(b, spec)
        c = b.get("convergence") or {}
        g = t["claims"].get("gap")
        if c.get("mode") == "three-resolution" and g and c.get("safe_interval"):
            s_lo, s_hi = c["safe_interval"]
            n_fin = max(c["edges"], key=int)
            e_lo, e_hi = c["edges"][n_fin]
            L, U = g["lower_edge"], g["upper_edge"]
            for d in DS:
                for tr, (a, z) in (("true", (L["hi"] * (1 + d), U["lo"] * (1 - d))),
                                   ("false_lo", (L["lo"] * (1 - d), U["lo"] * (1 - d))),
                                   ("false_hi", (L["hi"] * (1 + d), U["hi"] * (1 + d)))):
                    if a >= z:
                        continue
                    cert = s_lo is not None and s_hi is not None and s_lo < s_hi and a >= s_lo and z <= s_hi
                    rows.append(dict(cell=Path(f).stem, kind=spec["kind"], block="gap", key="gap", d=d,
                                     truth="true" if tr == "true" else "false",
                                     checker="certified" if cert else "not certified",
                                     naive_accept=bool(a >= e_lo and z <= e_hi)))
    summ = {}
    for blk in ("static", "gap"):
        rs = [r for r in rows if r["block"] == blk]
        summ[blk] = dict(
            n_claims=len(rs), n_cells=len({r["cell"] for r in rs}),
            checker=dict(collections.Counter(f"{r['truth']}/{r['checker']}" for r in rs)),
            naive=dict(collections.Counter(f"{r['truth']}/{'accept' if r['naive_accept'] else 'reject'}"
                                           for r in rs if r["naive_accept"] is not None)),
            by_d={str(d): dict(
                false_n=sum(r["truth"] == "false" for r in rs if r["d"] == d),
                false_certified=sum(r["truth"] == "false" and r["checker"] == "certified" for r in rs if r["d"] == d),
                false_naive_accepted=sum(r["truth"] == "false" and r["naive_accept"] for r in rs if r["d"] == d),
                true_n=sum(r["truth"] == "true" for r in rs if r["d"] == d),
                true_certified=sum(r["truth"] == "true" and r["checker"] == "certified" for r in rs if r["d"] == d),
                true_naive_accepted=sum(r["truth"] == "true" and r["naive_accept"] for r in rs if r["d"] == d))
                for d in DS},
            by_key={k: dict(false_naive_accepted=sum(r["truth"] == "false" and bool(r["naive_accept"])
                                                     for r in rs if r["key"] == k),
                            false_n=sum(r["truth"] == "false" for r in rs if r["key"] == k))
                    for k in sorted({r["key"] for r in rs})})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "near_threshold.json").write_text(json.dumps(dict(summary=summ, rows=rows), indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()

