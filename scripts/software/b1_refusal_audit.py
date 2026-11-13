"""Static audit of every recorded session under the B1 refusal-evidence rule (read only; no solver runs).

    python scripts/software/b1_refusal_audit.py

Reads the logs of the smoke, pilot, probe and E4 sessions (results/ is not written except the output file) and
applies amm.outcomes.audit_log to each submitted refusal. Output: results/software/b1_refusal_audit.json with the
counts per source and profile and every profile-C refusal the rule rejects, with the evidence the session held.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from amm import outcomes  # noqa: E402

SOURCES = {"smoke": "results/bench/smoke/jobs/*/session/session.jsonl",
           "pilot": "results/bench/pilot/*/*/session/session.jsonl",
           "probe": "results/probe/C/*/session/session.jsonl",
           "e4": "results/bench/e4/jobs/*/session/session.jsonl"}


def main():
    counts, changed = collections.Counter(), []
    for src, pat in SOURCES.items():
        for p in sorted(ROOT.glob(pat)):
            recs = []
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            a = outcomes.audit_log(recs)
            sub = a.get("submitted") or {}
            if sub.get("decision") != "refuse":
                continue
            key = f"{src} profile {a['profile']}"
            if not a["rule_applies"]:
                counts[key + " (rule not applied)"] += 1
                continue
            counts[key + (" accepted" if a["accepted"] else " REJECTED")] += 1
            if not a["accepted"]:
                changed.append(dict(session=str(p.parent.parent.relative_to(ROOT)).replace("\\", "/"),
                                    submitted=sub, held=a["held"]))
    out = dict(rule="amm.outcomes (B1, 2026-11-07)", counts=dict(sorted(counts.items())), changed=changed)
    dst = ROOT / "results" / "software" / "b1_refusal_audit.json"
    dst.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
