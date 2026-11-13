"""B9 wheel check: installed amm (not the checkout) finds the atlas through AMM_DATA_DIR."""
import json
import os
import sys

import amm
from amm import data, tools

print("amm", amm.__version__, amm.__file__)
print("AMM_DATA_DIR", os.environ.get("AMM_DATA_DIR"))
print("atlas_dir", tools.atlas_dir(), "verify", json.dumps(data.verify()))
s = tools.Session(None)
for name, args in (("set_material", {"name": "PA12"}), ("set_constraints", {"cell_size": 10, "cell_size_unit": "mm"}),
                   ("set_target", {"E100_min": {"value": 25, "unit": "MPa"}, "density_max": 0.25})):
    assert s.call(name, args)["ok"]
cb = s.call("check_bounds")
print("check_bounds", cb["ok"], cb["result"]["bounds_verdict"], cb["result"]["atlas"]["verdict"], cb["result"]["verdict"],
      cb["result"]["atlas"].get("n_clear"), "of", cb["result"]["atlas"].get("n_cells"), "|", cb["result"]["atlas"].get("note"))
sg = s.call("atlas_suggest", {"top": 2})
print("atlas_suggest", sg["ok"], json.dumps(sg.get("result", {}).get("best", [None])[0]) if sg["ok"] else sg["error"])
if "--search" in sys.argv:
    sr = s.call("search", {"budget": 8})
    print("search", sr["ok"], sr.get("error", "")[:400])
