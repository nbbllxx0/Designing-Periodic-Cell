"""Tool contract description read from the source of amm/tools.py and amm/units.py with `ast` (no import).

The GUI needs the list of tools, their arguments and docs, and the material table in every mode. Importing `amm`
would initialise MKL and the solver stack, which mock mode must not do (the E4 runs share this machine), so the
contract is parsed from source. In live mode the server can cross-check it against `amm.tools.TOOLS`.
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_PY = ROOT / "amm" / "tools.py"
UNITS_PY = ROOT / "amm" / "units.py"


def _decorator_kwargs(fn: ast.FunctionDef) -> dict | None:
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and getattr(d.func, "id", None) == "tool":
            out = {}
            for kw in d.keywords:
                try:
                    out[kw.arg] = ast.literal_eval(kw.value)
                except ValueError:
                    out[kw.arg] = ast.unparse(kw.value)
            return out
    return None


@lru_cache(maxsize=1)
def tool_specs() -> list[dict]:
    """Tools of amm.tools.Session in source order: name, doc, params, mutates, profiles, replay, and `since` (the
    tool-contract schema that introduced the tool; "amm-tools/1" unless the decorator says otherwise)."""
    tree = ast.parse(TOOLS_PY.read_text(encoding="utf-8"))
    consts = {}
    for node in tree.body:  # module-level string constants such as SCHEMA_V1 / SCHEMA_VERSION
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            consts[node.targets[0].id] = node.value.value
    out = []
    for cls in tree.body:
        if not (isinstance(cls, ast.ClassDef) and cls.name == "Session"):
            continue
        for fn in cls.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            kw = _decorator_kwargs(fn)
            if kw is None:
                continue
            a = fn.args
            pos = a.args[1:]  # drop self
            defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
            params = []
            for p, d in zip(pos, defaults):
                params.append(dict(name=p.arg, type=ast.unparse(p.annotation) if p.annotation else "Any",
                                   default=(ast.unparse(d) if d is not None else None), required=d is None))
            out.append(dict(name=fn.name, doc=ast.get_docstring(fn) or "", params=params,
                            mutates=bool(kw.get("mutates", False)),
                            profiles=list(kw["profiles"]) if isinstance(kw.get("profiles"), (tuple, list)) else
                            ["B", "C"], replay=kw.get("replay", "run"),
                            since=consts.get(kw.get("since"), kw.get("since")) or consts.get("SCHEMA_V1", "amm-tools/1")))
    return out


ATLAS_PY = ROOT / "amm" / "atlas.py"
GEOMETRY_PY = ROOT / "amm" / "geometry.py"


def _module_constants(path: Path, names: tuple[str, ...]) -> dict:
    """Literal module-level constants (tuples, dicts, numbers) of a source file, by name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    env: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            n = node.targets[0].id
            if n in names or n in ("TPMS", "STRUTS", "RESONATORS"):
                try:
                    env[n] = ast.literal_eval(node.value)
                except ValueError:  # e.g. FAMILIES = {"tpms": TPMS, ...}: resolve names already seen
                    if isinstance(node.value, ast.Dict):
                        env[n] = {ast.literal_eval(k): env[v.id] for k, v in zip(node.value.keys, node.value.values)}
    return {k: env[k] for k in names if k in env}


@lru_cache(maxsize=1)
def families() -> dict:
    """Families, kinds, parameter boxes and validity rules, as amm.tools.list_families returns them (from source).
    {family: {kind: {params: {name: [lo, hi]}, modes}}}, plus rules and r_gap."""
    g = _module_constants(GEOMETRY_PY, ("FAMILIES",))["FAMILIES"]
    a = _module_constants(ATLAS_PY, ("BOX", "TPMS_MODES", "R_GAP"))
    box = a["BOX"]
    out = {}
    for fam, kinds in g.items():
        out[fam] = {k: dict(params={n: list(b) for n, b in (box[k] if k in box else box[fam]).items()},
                            modes=list(a["TPMS_MODES"]) if fam == "tpms" else None) for k in kinds}
    return dict(families=out, r_gap=a["R_GAP"], rules=dict(
        struts=f"R = 0 (no node sphere) or R >= r + {a['R_GAP']:g}",
        cube_bars="w <= c - 0.04", sphere_ligaments="w <= 2 c - 0.02",
        tpms="network TPMS do not percolate below density ~0.10 (Schwarz P ~0.15)"))


@lru_cache(maxsize=1)
def materials() -> dict:
    """MATERIALS of amm/units.py: name -> dict(E, nu, rho, process, min_feature, tolerance)."""
    tree = ast.parse(UNITS_PY.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "MATERIALS" for t in node.targets):
            res = {}
            for k, v in zip(node.value.keys, node.value.values):
                res[ast.literal_eval(k)] = {kw.arg: ast.literal_eval(kw.value) for kw in v.keywords}
            return res
    raise RuntimeError("MATERIALS not found in amm/units.py")
