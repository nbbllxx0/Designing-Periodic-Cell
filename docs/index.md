# amm documentation

amm (AgenticMetamaterials) designs periodic metamaterial unit cells for stiffness and elastic-wave band-gap
targets. Its tools can be driven by a script, from the command line (`amm`), by an LLM agent over MCP, or by a browser GUI. Every release is
backed by a solver certificate that the agent cannot write. A refusal must cite evidence: a violated physics
bound, a bounded search that found nothing, or an undetermined certificate.

| Page | Contents |
|---|---|
| [install.md](install.md) | core install, extras, CPU-only and CUDA, environment variables, tests, the clean-install records (Windows venv and Linux container, both run) |
| [quickstart.md](quickstart.md) | a first session in 15 lines, the command line (`amm`), the tutorials, replay |
| [concepts.md](concepts.md) | units and targets; search tier and acceptance tier; the five outcomes plus "information needed"; what a certificate guarantees and does not |
| [tool_contract.md](tool_contract.md) | the 17 tools, their arguments and profiles (generated from `amm.tools.contract()`) |
| [mcp.md](mcp.md) | the MCP server and how to connect an agent |
| [gui.md](gui.md) | the browser GUI (source checkout) and how to launch it |
| [extending.md](extending.md) | custom geometry, adding a cell family, adding a target type |
| [data.md](data.md) | the search atlas and error-model files, `AMM_DATA_DIR`, the data manifest |
| [limitations.md](limitations.md) | scope, certificate caveats, platform and packaging limits, open bugs |

To regenerate the tool reference after a contract change, run `python docs/gen_tool_reference.py`. CI checks it
with `--check`.
