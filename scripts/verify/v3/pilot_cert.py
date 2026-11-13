"""Time one certificate early (NOTES.md section 7): the development witness of the pilot target, as_built off."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from amm import certify  # noqa: E402

out = common.OUT / "pilot"
tgt = common.load_targets(out / "targets_pilot.json")[0]
t = time.perf_counter()
c = certify.certify(tgt["witness"], tgt["targets"], nu=tgt["nu"], as_built=False)
w = time.perf_counter() - t
s = common.cert_summary(c, tgt["targets"])
s.update(wall_seconds=round(w, 1), target_id=tgt["target_id"], spec=tgt["witness"])
common.dump(out / "witness_cert_timing.json", s)
print(json.dumps(dict(verdict=s["verdict"], seconds=s["seconds"], timing=s["timing"], wall=round(w, 1))))
