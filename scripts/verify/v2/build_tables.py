"""V2 tables: matrix.csv (one row per capability x interface) and T12_v2.csv (the paper table) from the
observations (results/verification/v2/observations/main/) and the replay results (replays.csv).

    python scripts/verify/v2/build_tables.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2lib  # noqa: E402
from matrix_spec import SCENARIOS  # noqa: E402

GROUPS = ["Target types (feasible / infeasible) and combinations", "Families (each alone, all together)",
          "Materials and physical units", "Invalid requests", "Stale certificates and evidence",
          "Certificates, as-built, evaluate", "Export and screening", "Outcomes and profiles (B vs C)",
          "Tool lists and server state", "Browser pass (headless Edge)", "Replay of every V2 session"]
IFACES = ["lib", "mcp", "gui", "gui-edge", "cli"]
INVALID = ("contradictory", "negative", "unknown", "zener", "wrong_type", "out_of_box", "validity_rule", "tpms_no_mode",
           "too_many", "top_range", "neg_cell", "no_spend", "budget", "malformed", "fam_empty", "material_bad_nu",
           "release_no_design", "already_submitted", "wrong_verdict", "gap_contains_zero", "mcp_args", "mcp_wrong",
           "gui_json", "gui_wrong", "gui_foreign", "gui_bad", "release_refuted", "export_no_session")
OUTCOME = ("proven_infeasible", "not_found_in_families", "refuted_candidate", "numerically_undetermined", "need_info",
           "pa12_release", "combo_release", "B_", "C_", "cli_profile_B")


def group_of(r: dict) -> str:
    c, sc = r["check"], r["scenario"]
    if sc == "X_replay" or c == "cli_replay":
        return GROUPS[10]
    if sc == "X_edge":
        return GROUPS[9]
    if c.startswith(("stale", "combo_stale", "undet_stale")) or c.startswith("nf_holds"):
        return GROUPS[4]
    if any(k in c for k in INVALID):
        return GROUPS[3]
    if c.startswith(OUTCOME):
        return GROUPS[7]
    if "export" in c or "screen" in c:
        return GROUPS[6]
    if any(k in c for k in ("certify", "cert", "as_built", "eval")):
        return GROUPS[5]
    if c.startswith(("fam_", "nf_bounds")) or c == "cli_atlas_suggest":
        return GROUPS[1]
    if c.startswith(("material", "units_", "bounds_", "matchange", "gpa_", "hz_", "combo_units", "E100_Es")):
        return GROUPS[2]
    if c.startswith(("mcp_tools", "gui_tools", "gui_health")):
        return GROUPS[8]
    return GROUPS[0]


def main():
    obs = v2lib.OUT / "observations" / "main"
    exp = {}
    for fn in ("expectations.csv", "expectations_addendum.csv"):
        for r in csv.DictReader(open(v2lib.OUT / fn, encoding="utf-8")):
            exp[(r["scenario"], r["check"], r["interface"])] = r["expected"]
    causes = json.loads((v2lib.OUT / "failure_causes.json").read_text(encoding="utf-8"))         if (v2lib.OUT / "failure_causes.json").exists() else {}
    rows = []
    for p in sorted(obs.glob("*__*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in d["rows"]:
            r = dict(r)
            r["expected"] = r.get("expected") or exp.get((r["scenario"], r["check"], r["interface"]), "")
            rows.append(r)
    # replay rows: one per interface (every log of that interface exact)
    rp = v2lib.OUT / "replays.csv"
    if rp.exists():
        reps = [r for r in csv.DictReader(open(rp, encoding="utf-8")) if r["tag"] == "main"]
        by = defaultdict(list)
        for r in reps:
            by[r["interface"]].append(r)
        for iface, rs in sorted(by.items()):
            n = sum(r["exact"] == "True" for r in rs)
            calls = sum(int(r["n_compared"] or 0) for r in rs)
            certs = sum(int(r["certify_calls"]) for r in rs)
            exps = sum(int(r["export_calls"]) for r in rs)
            bad = [r["log"] + " " + r["mismatch_tools"] for r in rs if r["exact"] != "True"]
            rows.append(dict(scenario="X_replay", check="replay_all", capability=f"replay: every V2 session ({iface})",
                             interface=iface, profile="B,C", tool="amm.tools.replay",
                             expected="every log exact (ok, state hash, result of every call)",
                             expected_refusal=False, passed=n == len(rs),
                             observed=f"{n}/{len(rs)} logs exact, {calls} calls compared, {certs} certificates, "
                                      f"{exps} exports re-run" + (f"; not exact: {bad}" if bad else ""),
                             failures=bad, session="results/verification/v2/replays.csv"))
    # expected rows that never ran (a scenario that did not run or stopped): listed as failures
    seen = {(r["scenario"], r["check"], r["interface"]) for r in rows}
    for (sc, ck, iface), e in exp.items():
        if (sc, ck, iface) not in seen:
            cap = next((s["cap"] for s in SCENARIOS[sc]["steps"] if s.get("check") == ck), ck)
            rows.append(dict(scenario=sc, check=ck, capability=cap, interface=iface, profile=SCENARIOS[sc]["profile"],
                             tool="", expected=e, expected_refusal=False, passed=False, observed="NOT RUN",
                             failures=["not run"], session=""))
    for r in rows:
        r["result"] = ("fail" if not r["passed"] else "refused as expected" if str(r.get("expected_refusal")) == "True"
                       else "pass")
        r["group"] = group_of(r)
        r["cause"] = "" if r["passed"] else causes.get(f"{r['scenario']}/{r['check']}", causes.get(r["check"], "unexplained"))
    rows.sort(key=lambda r: (r["scenario"], r["check"], IFACES.index(r["interface"]) if r["interface"] in IFACES else 9))
    cols = ["group", "scenario", "check", "capability", "interface", "profile", "tool", "expected", "observed", "result",
            "cause", "session"]
    with open(v2lib.OUT / "matrix.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    # T12
    t = defaultdict(lambda: defaultdict(Counter))
    for r in rows:
        t[r["group"]][r["interface"]][r["result"]] += 1
    order = list(GROUPS)
    with open(v2lib.OUT / "T12_v2.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["capability group"] + [f"{i} (pass+refused/rows)" for i in IFACES] +
                   ["total rows", "pass", "refused as expected", "fail", "fail: V2 expectation or design",
                    "fail: amm", "fail: app"])

        def kinds(rs):
            k = Counter()
            for r in rs:
                if r["result"] == "fail":
                    c = r["cause"]
                    k["v2" if c.startswith(("V2 ", "cascade")) else "app" if c.startswith("app/") else "amm"] += 1
            return k
        tot = defaultdict(Counter)
        for g in order:
            if g not in t:
                continue
            cells, n_all, n_fail = [], 0, 0
            for i in IFACES:
                c = t[g][i]
                n = sum(c.values())
                tot[i].update(c)
                n_all += n
                n_fail += c["fail"]
                cells.append(f"{c['pass'] + c['refused as expected']}/{n}" if n else "-")
            k = kinds([r for r in rows if r["group"] == g])
            n_p = sum(t[g][i]["pass"] for i in IFACES)
            n_r = sum(t[g][i]["refused as expected"] for i in IFACES)
            w.writerow([g] + cells + [n_all, n_p, n_r, n_fail, k["v2"], k["amm"], k["app"]])
        cells = []
        for i in IFACES:
            c = tot[i]
            cells.append(f"{c['pass'] + c['refused as expected']}/{sum(c.values())}")
        k = kinds(rows)
        w.writerow(["All rows"] + cells + [sum(sum(c.values()) for c in tot.values()),
                                           sum(c["pass"] for c in tot.values()),
                                           sum(c["refused as expected"] for c in tot.values()),
                                           sum(c["fail"] for c in tot.values()), k["v2"], k["amm"], k["app"]])
    allc = Counter(r["result"] for r in rows)
    print(f"{len(rows)} rows: {dict(allc)}")
    for r in rows:
        if r["result"] == "fail":
            print(f"FAIL {r['interface']:8s} {r['scenario']}/{r['check']}: {r['observed'][:200]} | {r.get('failures')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
