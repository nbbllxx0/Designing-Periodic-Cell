# Quick start

Install ([install.md](install.md)), then run this in Python. It is the same tool contract an agent uses through
MCP.

```python
import amm                      # import amm before torch
from amm import tools

s = tools.Session("my_session", profile="C")   # writes my_session/session.jsonl; Session(None) logs nothing
s.call("set_material", {"name": "PA12"})       # or {"E_Pa": ..., "nu": ..., "rho_kg_m3": ...}
s.call("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"})
s.call("set_target", {"E100_min": {"value": 25, "unit": "MPa"}, "density_max": 0.25})

print(s.call("check_bounds")["result"]["verdict"])            # FEASIBLE (bounds + atlas; needs the data files)
best = s.call("atlas_suggest", {"top": 3})["result"]["best"]  # closest atlas cells, search tier
ev = s.call("evaluate", {"designs": [b["design"] for b in best]})["result"]   # search tier, about 1-2 s per cell
cert = s.call("certify", {"design": best[0]["design"]})["result"]             # acceptance tier
print(cert["verdict"], cert["outcome"])                       # certified certified_candidate
out = s.call("submit", {"decision": "release", "design": best[0]["design"]})
print(out["result"]["outcome_card"]["outcome"])               # certified_candidate
```

Every `s.call(name, args)` returns `{"ok": ..., "seq": ..., "result": ...}`, or `"error"` instead of `"result"`.
Invalid arguments, unknown keys and values outside a family's box are rejected with a message. They do not
raise. The argument types are listed in [tool_contract.md](tool_contract.md).

This is tutorial 02. Run it as a script with:

```
python examples/02_atlas_to_certificate.py
```

The recorded run (`examples/outputs/02_atlas_to_certificate.log`) took 24 s in total, 20 s of it for the
certificate. It found and certified `sphere_ligaments c = 0.12, w = 0.18`: guarded E100 lower bound 45.9 MPa
against the 25 MPa target, density 0.069, robust under +-0.1 mm offsets.

## Tutorials

| Script | What it shows | Needs | Recorded runtime |
|---|---|---|---|
| `examples/01_evaluate_tensor.py` | evaluate one cell; read the full 6x6 tensor C*, C in MPa, Zener ratio, E100/E110/E111, eigenvalues | core | 4.6 s (GPU), 15.3 s (CPU-only clean install) |
| `examples/02_atlas_to_certificate.py` | stiffness target, then bounds and atlas, then evaluate, certify (static) and release | core + data | 24 s (certify 20 s) |
| `examples/03_export_and_screening.py` | manufacturing screening (pass at 10 mm, fail at 4 mm against PA12's 0.8 mm) and STL + report.json export | core (+ `export` for marching cubes) | 20 s |
| `examples/04_mcp_client_probe.py` | start the MCP server as a client would, list the tools, make three calls (no LLM) | `mcp` | 2 s |

Their outputs are in `examples/outputs/*.log`. The session directories `examples/outputs/02_session/` and
`03_session/` hold the replayable `session.jsonl` logs, the certificate JSON and the exported report; the STL
files are not kept in version control.

## Command line

The `amm` command (installed with the package; from a source checkout without installing, run
`python -m amm.cli`) wraps the same tool calls. Each subcommand sets the spec with `set_material`,
`set_constraints` and `set_target`, then runs one tool, and prints one JSON object with every call and its result.
The CLI adds no logic: the values go to `Session.call` unchanged, so the results and refusal messages are the
library's.

```
amm check-bounds  --material PA12 --cell-size 10 --target '{"E100_min": {"value": 25, "unit": "MPa"}, "density_max": 0.25}'
amm atlas-suggest --material PA12 --target '{"density_max": 0.25}' --top 3
amm evaluate      --material PA12 --design '{"kind": "bcc", "params": {"r": 0.08, "R": 0.0}}' [--bands]
amm certify       --session my_cli_session --material PA12 --cell-size 10                   --target '{"E100_min": {"value": 25, "unit": "MPa"}, "density_max": 0.25}'                   --design '{"kind": "sphere_ligaments", "params": {"c": 0.12, "w": 0.181739}}' --release --export
amm export        --session my_export --material PA12 --cell-size 10 --design '{"kind": "bcc", "params": {"r": 0.08, "R": 0.0}}'                   [--tiles 3] [--resolution 64] [--tile-resolution 32] [--printer-min-feature-mm 0.8]
amm replay        my_cli_session/session.jsonl
```

| Option | Meaning |
|---|---|
| `--spec FILE` | JSON `{"material": {set_material args}, "constraints": {set_constraints args}, "targets": {set_target args}}`, each part optional |
| `--material`, `--cell-size`, `--cell-size-unit`, `--families`, `--target` | the same parts as flags (`--families tpms,struts`; `--target` is set_target JSON). They override the file |
| `--session DIR` | write `session.jsonl`, `certificates/` and `exports/` to a new directory. Without it nothing is written, and `export` is refused because it writes files. A directory that already holds a log is refused: a session is never resumed |
| `--profile C\|B` | C (default) is the full system; B is the benchmark ablation arm, with no `check_bounds` or `certify` |
| `certify --release --export` | after the certificate, `submit(decision="release")` and `export` in the same session, so the report references the certificate |

Output: `{"cli": "amm-cli/1", "command", "session", "profile", "schema_version", "ok", "calls": [{tool, args, ok, seq,
result | error}], "result", "error"}`. The calls stop at the first refused one. Exit status 0 means every call was ok
(for replay: exact), 1 means a call was refused (replay: not exact), and 2 means a usage error, such as malformed
JSON in an option. Each CLI run is a separate session, and `amm replay` re-runs it exactly like a library log.

## Replay a session

```python
from amm import tools
rep = tools.replay("examples/outputs/02_session/session.jsonl")   # root=None: the replay writes no files
print(rep["exact"], rep["n_compared"])                              # True 12
```

Replay re-runs every call, including the certificate, with no LLM, and compares every result and state hash. It
is exact on the code and machine that wrote the log.

## Next

- [concepts.md](concepts.md): search tier and acceptance tier, outcomes, what a certificate does and does not
  guarantee.
- [mcp.md](mcp.md): connect Claude Code, Codex or another MCP client.
- [gui.md](gui.md): the browser GUI.
- The command line: section "Command line" above.
- [limitations.md](limitations.md).
