"""Do computed cubic cells respect the (isotropic) Hashin-Shtrikman upper bounds? Advisory audit, not a proof."""
import json
import amm
from amm import bounds, fem, geometry as G, homog

specs = [dict(family="tpms", kind=k, params=dict(density=d, mode=m)) for k in G.TPMS for d in (0.1, 0.2, 0.35, 0.5)
         for m in ("network", "sheet")]
specs += [dict(family="struts", kind=k, params=dict(r=r, R=0.0)) for k in G.STRUTS for r in (0.06, 0.1, 0.14)]
specs += [dict(family="resonator", kind="cube_bars", params=dict(c=c, w=w)) for c in (0.4, 0.6) for w in (0.15, 0.3)]
rows = []
for s in specs:
    cov, sub, info = G.design_cell(s, 24)
    if not all(info["percolates"]):
        continue
    r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub))
    hs = bounds.hashin_shtrikman_porous(r["density"], 0.3)
    rows.append(dict(spec=s, rho=r["density"], bulk_over_HS=r["bulk"] / hs["K"], C44_over_HSmu=r["G"] / hs["mu"],
                     shear_cubic2_over_HSmu=0.5 * (r["C11"] - r["C12"]) / hs["mu"], E100_over_HSE=r["E100"] / hs["E"]))
    x = rows[-1]
    print(f"{s['family']:9s} {s['kind']:10s} {json.dumps(s['params']):40s} rho={x['rho']:.3f} K/K_HS={x['bulk_over_HS']:.3f} "
          f"C44/mu_HS={x['C44_over_HSmu']:.3f} (C11-C12)/2/mu_HS={x['shear_cubic2_over_HSmu']:.3f} E100/E_HS={x['E100_over_HSE']:.3f}", flush=True)
mx = {k: max(r[k] for r in rows) for k in ("bulk_over_HS", "C44_over_HSmu", "shear_cubic2_over_HSmu", "E100_over_HSE")}
print("MAX", json.dumps(mx))
json.dump(dict(rows=rows, max=mx), open("results/verification/hs_audit.json", "w"), indent=1)
