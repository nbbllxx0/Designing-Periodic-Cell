"""Timing pilot target (development partition, NOT a V3 target): results/verification/v3/pilot/targets_pilot.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NU = {"316L": 0.3, "Ti6Al4V": 0.342, "PA12": 0.39}
bid = sys.argv[1] if len(sys.argv) > 1 else "M02"
b = json.loads((ROOT / "bench" / "v1" / "briefs" / f"{bid}.json").read_text(encoding="utf-8"))
assert b.get("pilot"), "pilot target must come from the development partition"
t = dict(target_id=bid, set="primary", order=0, material=b["intended"]["material"], nu=NU[b["intended"]["material"]],
         targets=b["truth"]["normalized"], target_type="combined" if b["cls"] == "feasible_combined" else b["cls"],
         witness_family=b["truth"]["witness"]["family"], witness=b["truth"]["witness"],
         difficulty=b["truth"]["difficulty"], intended=b["intended"], partition="development")
out = ROOT / "results" / "verification" / "v3" / "pilot"
out.mkdir(parents=True, exist_ok=True)
(out / "targets_pilot.json").write_text(json.dumps(dict(note="timing pilot, development spec", targets=[t]), indent=1),
                                        encoding="utf-8")
print(json.dumps(t)[:600])
