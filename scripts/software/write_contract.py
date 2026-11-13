"""Write the versioned tool contract (amm.tools.contract) for schemas 1 and 2 to results/software/."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from amm import tools  # noqa: E402

for sch in tools.SCHEMAS:
    p = ROOT / "results" / "software" / f"contract_{sch.replace('/', '-')}.json"
    p.write_text(json.dumps(tools.contract(sch), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", p, len(tools.contract(sch)["tools"]), "tools")
