"""Reference outputs of existing call paths, for the bit-identity check of plan items B1-B3.

    python scripts/software/b1b3_reference.py <out.json> [--no-replay]
    python scripts/software/b1b3_reference.py --compare <pre.json> <post.json>

Records, on small grids: geometry voxelizations (every kind, grid phases, offsets, multi-resolution), homogenized
C*, search-tier evaluation (GPU bands), bounds and atlas verdicts, two small certificates, and the replay of five
recorded smoke sessions. Arrays are stored as sha256 of their bytes (dtype and shape included); dicts as canonical
JSON with timing fields removed. The certificate's code identity (`checker`) is stored apart: it must change when
the checker code changes and is not a numerical result.
Run GPU parts under the solver lock (scripts/ops/gpulock_run.py).
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VOLATILE = {"seconds", "timing", "dt_s", "batch_seconds_per_cell", "static_s", "bloch_s", "t", "edge_extra_seconds"}
SMOKE = ["codex-C-r1-X01", "codex-C-r1-N01", "codex-C-r1-N02", "codex-B-r1-S01", "codex-C-r1-S01"]


def ahash(a) -> str:
    a = np.ascontiguousarray(a)
    return f"{a.dtype}{a.shape}:" + hashlib.sha256(a.tobytes()).hexdigest()[:20]


def plain(x):
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items() if k not in VOLATILE}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return dict(__array__=ahash(x))
    if isinstance(x, np.generic):
        return x.item()
    return x


def jhash(x) -> str:
    return hashlib.sha256(json.dumps(plain(x), sort_keys=True, default=str).encode()).hexdigest()[:20]


SPECS = [
    dict(family="tpms", kind="gyroid", params=dict(density=0.25, mode="network")),
    dict(family="tpms", kind="iwp", params=dict(density=0.3, mode="sheet")),
    dict(family="tpms", kind="schwarz_p", params=dict(t=0.4, mode="network")),
    dict(family="tpms", kind="diamond", params=dict(density=0.2, mode="sheet")),
    dict(family="struts", kind="sc", params=dict(r=0.12, R=0.0)),
    dict(family="struts", kind="bcc", params=dict(r=0.08, R=0.15)),
    dict(family="struts", kind="octet", params=dict(r=0.06, R=0.0)),
    dict(family="resonator", kind="cube_bars", params=dict(c=0.6, w=0.2)),
    dict(family="resonator", kind="sphere_ligaments", params=dict(c=0.3, w=0.1)),
]


def geometry_refs() -> dict:
    from amm import geometry as G
    out = {}
    for s in SPECS:
        k = s["kind"] + "/" + s["params"].get("mode", "")
        for n in (12, 16):
            for ph in (0.0, 0.125, 0.25, 0.5):
                cov, sub, info = G.design_cell(s, n, phase=ph)
                out[f"design_cell {k} n{n} ph{ph}"] = [ahash(cov), ahash(sub), plain(info)]
        cov, sub, info = G.design_cell(s, 16, offset_voxels=-0.16, phase=0.25)
        out[f"design_cell {k} n16 erode ph0.25"] = [ahash(cov), ahash(sub), plain(info)]
        cells = G.design_cells(s, (10, 20), 60)
        out[f"design_cells {k}"] = {n: [ahash(c[0]), ahash(c[1]), plain(c[2])] for n, c in cells.items()}
        out[f"make {k} binary"] = ahash(G.make(s["family"], s["kind"], 14, coverage=False, **s["params"]))
        out[f"make {k} coverage dilate"] = ahash(G.make(s["family"], s["kind"], 14, offset_voxels=0.14, **s["params"]))
        out[f"field {k}"] = [ahash(G.field(s["family"], s["kind"], 18, **s["params"])[0])]
    out["tpms_field gyroid"] = ahash(G.tpms_field("gyroid", 20))
    out["grid 7"] = [ahash(g) for g in G.grid(7)]
    return out


def homog_refs() -> dict:
    from amm import fem, geometry as G, homog
    out = {}
    for s in SPECS[::2]:
        cov, sub, info = G.design_cell(s, 14)
        r = homog.homogenize(mesh=fem.build_mesh(cov, sub=sub, nu=0.3))
        out[s["kind"]] = [ahash(r["C"]), jhash({k: v for k, v in r.items() if k != "C"})]
    return out


def evaluate_refs() -> dict:
    from amm import atlas, evaluate
    specs = [SPECS[0], SPECS[5], SPECS[7]]
    rows = evaluate.evaluate_batch(specs, nu=0.342, keep_bands=True, **atlas.SEARCH_TIER)
    return {r["spec"]["kind"]: [jhash(r), ahash(np.asarray(r["bands"]))] for r in rows}


def bounds_refs() -> dict:
    from amm import atlas, bounds, tools
    t = dict(density_max=0.3, E100_min=0.02, gap=dict(f_lo=0.3, f_hi=0.36))
    rows = tools.atlas_rows(0.3)
    o = atlas.oracle(rows, t, top=5)
    return dict(bounds=jhash(bounds.check(t, nu_s=0.3)), bounds_bad=jhash(bounds.check(dict(E100_min=0.5,
                density_max=0.2), nu_s=0.3)), oracle=jhash(o))


CERT_KW = dict(res_bloch=(8, 10), static_ladder=((8, 10, 12),), edge_res=(12,), bloch_phases=(0.5,), adversarial_n=6,
               n_path=2, n_interior=3, nu=0.3)


def certify_refs() -> dict:
    from amm import certify
    out = {}
    for name, spec, t in (("static", SPECS[4], dict(E100_min=0.01, density_max=0.2)),
                          ("gap", SPECS[7], dict(gap=dict(f_lo=0.30, f_hi=0.33), G_min=0.001))):
        c = certify.certify(spec, t, **CERT_KW)
        out[name] = dict(hash=jhash({k: v for k, v in c.items() if k != "checker"}), verdict=c["verdict"],
                         robust=c["robust"], checker=c["checker"], full=plain({k: v for k, v in c.items()
                                                                               if k != "checker"}))
    return out


def replay_refs() -> dict:
    from amm import tools
    out = {}
    for job in SMOKE:
        p = ROOT / "results" / "bench" / "smoke" / "jobs" / job / "session" / "session.jsonl"
        t0 = time.perf_counter()
        r = tools.replay(p)
        out[job] = dict(exact=r["exact"], n_calls=r["n_calls"], n_compared=r["n_compared"],
                        mismatches=r["mismatches"], same_code=r["same_code"],
                        extra={k: v for k, v in r.items() if k not in ("exact", "n_calls", "n_compared",
                                                                        "mismatches", "same_code")},
                        seconds=round(time.perf_counter() - t0, 1))
        print(job, out[job]["exact"], out[job]["seconds"], flush=True)
    return out


def main(argv):
    if argv[0] == "--compare":
        a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in argv[1:3])
        bad = []
        for sec in ("geometry", "homog", "evaluate", "bounds"):
            for k in a[sec]:
                if a[sec][k] != b[sec].get(k):
                    bad.append((sec, k))
        for k in a["certify"]:
            if a["certify"][k]["hash"] != b["certify"][k]["hash"]:
                bad.append(("certify", k))
        print("arrays/dicts compared:", sum(len(a[s]) for s in ("geometry", "homog", "evaluate", "bounds", "certify")))
        print("checker identity:", {k: (a["certify"][k]["checker"], b["certify"][k]["checker"]) for k in a["certify"]})
        for k in a.get("replay", {}):
            print("replay", k, "pre exact", a["replay"][k]["exact"], "post exact", b.get("replay", {}).get(k, {}).get("exact"))
        print("DIFFERENT:", bad if bad else "none")
        return 1 if bad else 0
    out_path = Path(argv[0])
    import amm
    res = dict(created=time.strftime("%Y-%m-%d %H:%M:%S"), mkl_cbwr=amm.MKL_CBWR_STATUS)
    for name, fn in (("geometry", geometry_refs), ("homog", homog_refs), ("bounds", bounds_refs),
                     ("evaluate", evaluate_refs), ("certify", certify_refs)):
        t0 = time.perf_counter()
        res[name] = fn()
        print(name, len(res[name]), round(time.perf_counter() - t0, 1), "s", flush=True)
    if "--no-replay" not in argv:
        res["replay"] = replay_refs()
    from amm import certify, tools
    res["identity"] = dict(code=tools.code_hash(), checker=certify.checker_hash())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=1, sort_keys=True, default=str), encoding="utf-8")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
