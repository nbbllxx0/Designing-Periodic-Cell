"""Command line for the tool contract: each subcommand is a thin wrapper over amm.tools.Session calls, with JSON
output. The CLI adds no logic of its own: every value is passed to a logged tool call unchanged, and every check,
conversion and refusal is amm's (the same messages as the library, the MCP server and the GUI).

    amm check-bounds  [spec options]
    amm atlas-suggest [spec options] [--top N]
    amm evaluate      [spec options] --design JSON [--design JSON ...] [--bands]
    amm certify       [spec options] --design JSON [--release] [--export [export options]]
    amm export        [spec options] --design JSON [export options]
    amm replay        LOG [--root DIR]

Spec options (every subcommand but replay): the spec is set by up to three calls, in this order, before the tool
runs: set_material, set_constraints, set_target.
    --spec FILE        JSON {"material": {set_material args}, "constraints": {set_constraints args},
                              "targets": {set_target args}} (each part optional)
    --material NAME    set_material name (overrides the file's material)
    --cell-size V [--cell-size-unit mm]   set_constraints cell_size, cell_size_unit
    --families LIST    set_constraints families, comma separated (tpms,struts,resonator)
    --target JSON      set_target args (keys override the file's targets)
    --session DIR      write the session log (session.jsonl, certificates/, exports/) to DIR, which must not hold a
                       session log yet (a session is never resumed; `amm replay` re-runs one). Without it nothing is
                       written (export needs it: amm refuses an export without a session directory).
    --profile C|B      C (default) is the full system; B the benchmark ablation arm (no check_bounds, certify)

A design is JSON {"kind": ..., "params": {...}} as in the tool contract (docs/tool_contract.md).

Output: one JSON object on stdout {"cli", "command", "session", "profile", "schema_version", "ok", "calls": [one
entry per tool call: tool, args, ok, seq, result | error], "result" (of the last call), "error" (of the first failed
call)}. The calls stop at the first failed one. Exit status: 0 every call ok (replay: exact), 1 a call was refused
or failed (replay: not exact), 2 a usage error (bad option, malformed JSON, a session directory already in use).
Installed as the `amm` console script ([project.scripts]); from a checkout: `python -m amm.cli`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CLI_SCHEMA = "amm-cli/1"


class UsageError(Exception):
    pass


def _json_arg(text: str, what: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError as ex:
        raise UsageError(f"{what} is not valid JSON ({ex.msg} at position {ex.pos}): {text[:80]!r}") from None


def _spec_parts(a) -> tuple[dict | None, dict | None, dict | None]:
    """(set_material args, set_constraints args, set_target args) from --spec and the flags; None = no call."""
    base = {}
    if a.spec:
        try:
            text = Path(a.spec).read_text(encoding="utf-8")
        except OSError as ex:
            raise UsageError(f"cannot read --spec {a.spec}: {ex.strerror}") from None
        base = _json_arg(text, f"--spec {a.spec}")
        if not isinstance(base, dict) or set(base) - {"material", "constraints", "targets"}:
            raise UsageError('--spec must be a JSON object with the keys "material", "constraints", "targets" '
                             "(each optional)")
    mat, con, tgt = base.get("material"), base.get("constraints"), base.get("targets")
    if a.material is not None:
        mat = dict(name=a.material)
    if a.cell_size is not None or a.families is not None:
        con = dict(con or {})
        if a.cell_size is not None:
            con.update(cell_size=a.cell_size, cell_size_unit=a.cell_size_unit)
        if a.families is not None:
            con["families"] = [f.strip() for f in a.families.split(",") if f.strip()]
    if a.target is not None:
        t = _json_arg(a.target, "--target")
        if not isinstance(t, dict):
            raise UsageError("--target must be a JSON object of set_target arguments")
        tgt = dict(tgt or {}, **t)
    return mat, con, tgt


def _designs(a) -> list:
    return [_json_arg(d, "--design") for d in (a.design or [])]


def _export_args(a, design) -> dict:
    out = dict(design=design)
    for k in ("tiles", "resolution", "tile_resolution", "printer_min_feature_mm"):
        if getattr(a, k) is not None:
            out[k] = getattr(a, k)
    return out


def _plan(a) -> list[tuple[str, dict]]:
    """The tool calls of one subcommand, in order."""
    mat, con, tgt = _spec_parts(a)
    calls = []
    if mat is not None:
        calls.append(("set_material", mat))
    if con is not None:
        calls.append(("set_constraints", con))
    if tgt is not None:
        calls.append(("set_target", tgt))
    cmd = a.command
    if cmd == "check-bounds":
        calls.append(("check_bounds", {}))
    elif cmd == "atlas-suggest":
        calls.append(("atlas_suggest", {} if a.top is None else dict(top=a.top)))
    elif cmd == "evaluate":
        args = dict(designs=_designs(a))
        if a.bands:
            args["bands"] = True
        calls.append(("evaluate", args))
    elif cmd in ("certify", "export"):
        ds = _designs(a)
        if len(ds) != 1:
            raise UsageError(f"{cmd} takes exactly one --design")
        if cmd == "certify":
            calls.append(("certify", dict(design=ds[0])))
            if a.release:
                calls.append(("submit", dict(decision="release", design=ds[0])))
            if a.export:
                calls.append(("export", _export_args(a, ds[0])))
        else:
            calls.append(("export", _export_args(a, ds[0])))
    return calls


def _session(a):
    from . import tools
    root = None
    if a.session:
        root = Path(a.session)
        if (root / "session.jsonl").exists():
            raise UsageError(f"{root} already holds a session log: use a new directory (a session is not resumed; "
                             "`amm replay` re-runs one)")
    return tools.Session(root, profile=a.profile)


def run(a) -> tuple[dict, int]:
    from . import tools
    if a.command == "replay":
        rep = tools.replay(a.log, root=a.root)
        return dict(cli=CLI_SCHEMA, command="replay", log=a.log, ok=bool(rep["exact"]), result=rep), \
            (0 if rep["exact"] else 1)
    plan = _plan(a)
    s = _session(a)
    out = dict(cli=CLI_SCHEMA, command=a.command, session=str(s.root) if s.root is not None else None,
               profile=s.profile, schema_version=s.schema, ok=True, calls=[], result=None, error=None)
    for name, args in plan:
        r = s.call(name, args, actor="cli")
        out["calls"].append(dict(tool=name, args=args, ok=r["ok"], seq=r.get("seq"),
                                 **({"result": r["result"]} if r["ok"] else {"error": r["error"]})))
        if not r["ok"]:
            out.update(ok=False, error=dict(tool=name, error=r["error"]))
            break
        out["result"] = r["result"]
    return out, (0 if out["ok"] else 1)


def parser() -> argparse.ArgumentParser:
    from . import __version__
    ap = argparse.ArgumentParser(prog="amm", description="amm tool contract from the command line (JSON output)")
    ap.add_argument("--version", action="version", version=f"amm {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    def spec_opts(p):
        p.add_argument("--session", help="new session directory for the log (default: nothing is written)")
        p.add_argument("--profile", default="C", choices=["C", "B"])
        p.add_argument("--spec", help='JSON file {"material", "constraints", "targets"}')
        p.add_argument("--material", help="set_material name (PA12, Ti6Al4V, 316L, AlSi10Mg)")
        p.add_argument("--cell-size", type=float, dest="cell_size")
        p.add_argument("--cell-size-unit", default="mm", dest="cell_size_unit")
        p.add_argument("--families", help="comma-separated families, e.g. tpms,struts")
        p.add_argument("--target", help="set_target arguments as JSON")

    def export_opts(p):
        p.add_argument("--tiles", type=int)
        p.add_argument("--resolution", type=int)
        p.add_argument("--tile-resolution", type=int, dest="tile_resolution")
        p.add_argument("--printer-min-feature-mm", type=float, dest="printer_min_feature_mm")

    p = sub.add_parser("check-bounds", help="bounds and family-atlas verdict for the spec")
    spec_opts(p)
    p = sub.add_parser("atlas-suggest", help="closest atlas cells (search tier)")
    spec_opts(p)
    p.add_argument("--top", type=int)
    p = sub.add_parser("evaluate", help="search-tier properties of 1-16 designs")
    spec_opts(p)
    p.add_argument("--design", action="append", required=True, help="design JSON (repeat for several)")
    p.add_argument("--bands", action="store_true", help="also return the band structure (schema amm-tools/3)")
    p = sub.add_parser("certify", help="certificate of one design for the spec")
    spec_opts(p)
    export_opts(p)
    p.add_argument("--design", action="append", required=True)
    p.add_argument("--release", action="store_true", help="then submit(decision=release) for the design")
    p.add_argument("--export", action="store_true", help="then export the design (needs --session)")
    p = sub.add_parser("export", help="STL + report.json export with manufacturing screening")
    spec_opts(p)
    export_opts(p)
    p.add_argument("--design", action="append", required=True)
    p = sub.add_parser("replay", help="re-run a session log without any LLM and compare every result")
    p.add_argument("log")
    p.add_argument("--root", help="session directory for the replay (default: none, or a temporary one for exports)")
    return ap


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):  # JSON is UTF-8; Windows consoles default to cp1252
        if hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8")
    a = parser().parse_args(argv)
    try:
        out, code = run(a)
    except UsageError as ex:
        print(json.dumps(dict(cli=CLI_SCHEMA, command=a.command, ok=False, usage_error=str(ex))))
        print(f"amm: {ex}", file=sys.stderr)
        return 2
    from .tools import canon
    print(json.dumps(json.loads(canon(out)), indent=1, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
