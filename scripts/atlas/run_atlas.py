"""Week 3, E2: run the family atlas at the search tier (amm.atlas.grid_specs, amm.atlas.SEARCH_TIER).
Usage: run_atlas.py [nu]   -> results/atlas/atlas_nu<nu>.jsonl (resumable), log on stdout."""
import sys
import amm  # noqa: F401
from amm import atlas

nu = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
atlas.run(atlas.grid_specs(), f"results/atlas/atlas_nu{nu:g}.jsonl", nu=nu, log=lambda s: print(s, flush=True))
