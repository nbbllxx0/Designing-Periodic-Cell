"""Scoring of benchmark sessions (plan E3/E4) against the briefs' ground truth.

One session = one brief x one arm. From the tool log (session.jsonl) and the run record (run.json):

decision   release | refuse | need_info | none (no successful submit, or no session log at all)
asked      number of answered ask_clarification calls; `asked_relevant`: some answer picked an option that matches
           the intended spec or stated the brief's missing fact (amm.bench.Oracle)
release check  every released design is certified against the INTENDED request (the brief's own spec, normalized
           with the intended material and cell size), not against what the agent typed. A certificate from the
           session counts only if the session's normalized targets equal the intended ones and both the spec and the
           certificate used the intended material; otherwise the design is certified afresh (`posthoc`, cached in
           results/bench/posthoc, keyed by the checker's code hash). A request that violates a rigorous bound
           refutes any release without a solve.

Truth levels (audit F01, 2026-11-06): `witnessed` (a design certified against the stated request: S, G, M, the
relabelled R, and their ambiguous pairs), `proven` (a rigorous bound violated: X and pairs) and `unresolved` (no
certified witness found by the recorded searches, no bound violated: N, the other R, and pairs). Unresolved briefs
have no physical ground truth; they are scored for honest scope, not as correct or wrong refusals.

spec at submission: the material, cell size and targets in force when submit was called (recorded by submit since
2026-11-06; for older logs rebuilt by re-running the spec calls before submit, undo included). `spec_ok` = the
intended material, the intended normalized targets and, when the brief fixes one, the intended cell size.
Certificates count only from the current checker with the intended material and Poisson ratio (re-audit #3).
Questions count only before submit, and only when the answer settles the missing item (re-audit #2).

outcome  release:  success (certified against the intended request and spec_ok) | spec_error_release (certified
                   against the intended request, but the agent's stated material, cell size or targets were wrong;
                   on any truth level) |
                   silent_failure (refuted) | unverified_release (undetermined) | witness_found (certified on an
                   unresolved brief: the brief becomes witnessed)
         refuse:   witnessed -> false_refusal; proven -> correct_refusal (verdict_match exact | weaker | other);
                   unresolved -> abstention (NOT_FOUND / UNDETERMINED / OTHER) | overclaim (PROVEN_INFEASIBLE)
         need_info or no submit: no_answer
correct (decision quality, witnessed and proven briefs only; None on unresolved): success or correct_refusal, and
         on an ambiguous brief the agent asked a question whose answer resolved the missing item.
appropriate (unresolved briefs only): abstention or witness_found, with the same clarification rule.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from amm import bounds, units

ROOT = Path(__file__).resolve().parents[2]
POSTHOC_DIR = ROOT / "results" / "bench" / "posthoc"


def _close(a, b, rel=1e-9) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_close(a[k], b[k], rel) for k in a)
    try:
        return abs(float(a) - float(b)) <= rel * max(abs(float(a)), abs(float(b)), 1e-300)
    except (TypeError, ValueError):
        return a == b


def intended_normalized(brief: dict) -> dict:
    it = brief["intended"]
    req = dict(it["targets"], material=it["material"])
    if it.get("cell_size") is not None:
        req["cell_size"] = it["cell_size"]
    t, missing, _ = units.normalize(req)
    if missing:
        raise ValueError(f"{brief['id']}: intended spec cannot be normalized: {missing}")
    return t


def posthoc_certify(spec: dict, targets: dict, nu: float, cache_dir: Path = POSTHOC_DIR, legacy_ok: bool = False) -> dict:
    """Certificate of a released design against the intended targets (as-built flag off; cached on disk, keyed by
    the checker's code hash). Only the current checker counts. `legacy_ok` (development runs before 2026-11-06 only,
    never E4): a record of the earlier, unhashed checker is reused, labelled checker="legacy", unless its verdict
    came from a numerical failure (the verdict rule that changed, audit F05)."""
    from amm import certify
    legacy = hashlib.sha256(json.dumps(dict(spec=spec, targets=targets, nu=nu), sort_keys=True).encode()).hexdigest()[:16]
    chk = certify.checker_hash()
    key = hashlib.sha256(json.dumps(dict(spec=spec, targets=targets, nu=nu, checker=chk),
                                    sort_keys=True).encode()).hexdigest()[:16]
    f = Path(cache_dir) / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    lf = Path(cache_dir) / f"{legacy}.json"
    if legacy_ok and lf.exists():
        old = json.loads(lf.read_text(encoding="utf-8"))
        if not str((old.get("static_verdict") or {}).get("note", "")).startswith("numerics failed"):
            return dict(old, checker="legacy")
    c = certify.certify(spec, targets, nu=nu, as_built=False)
    out = dict(key=key, checker=chk, spec=spec, targets=targets, nu=nu, verdict=c["verdict"], seconds=c["seconds"],
               static_verdict=c["blocks"]["static"]["verdict"],
               gap_verdict=(c["blocks"].get("bloch") or {}).get("verdict"))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    (f.parent / f"{key}_full.json").write_text(json.dumps(c, default=float), encoding="utf-8")
    return out


def read_session(sess_dir: Path) -> dict:
    """Tolerant read: a line that does not parse (a log cut by a timeout kill) is skipped and counted."""
    recs, bad = [], 0
    for line in (Path(sess_dir) / "session.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    head = next((r for r in recs if r.get("type") == "session"), {})
    return dict(head=head, calls=[r for r in recs if r.get("type") == "call"], bad_lines=bad)


def truth_level(brief: dict) -> str:
    t = brief["truth"]
    if t["decision"] == "release":
        return "witnessed"
    return "proven" if t.get("verdict") == "PROVEN_INFEASIBLE" else "unresolved"


def spec_key(brief: dict) -> str:
    """Identity of the intended specification (statistical unit: ambiguous briefs share their pair's key)."""
    return hashlib.sha256(json.dumps(brief["intended"], sort_keys=True).encode()).hexdigest()[:12]


def spec_at_submit(calls: list[dict], profile: str, sub: dict | None) -> dict | None:
    if sub is None:
        return None
    if sub.get("spec"):
        return sub["spec"]
    from amm import tools
    s = tools.Session(None, profile=profile)
    for c in calls:
        if c["tool"] == "submit" and c["ok"]:
            break
        if c["ok"] and c["tool"] in ("set_material", "set_constraints", "set_target", "set_source", "undo"):
            s.call(c["tool"], c["args"], actor="replay")
    m = s._material()
    return dict(material=s.state["material"], nu=m["nu"] if m else None, cell_size=s.state["cell_size"],
                targets=dict(s.state["targets"]), gap_type=s.state.get("gap_type"), rebuilt=True)


def _relevant_answer(c: dict, brief: dict) -> bool:
    """The answer settled the brief's missing item: the chosen option matched the intended spec AND sets that item,
    or the oracle stated the missing fact (re-audit #2)."""
    from amm.bench import settles
    a = c.get("answer") or {}
    facts = (brief.get("oracle") or {}).get("facts", "")
    if bool(facts) and a.get("comment") == facts:
        return True
    ch = a.get("choice")
    opts = (c.get("args") or {}).get("options") or []
    return ch is not None and 0 <= ch < len(opts) and settles(opts[ch].get("set") or {}, brief.get("missing"))


def _no_log_record(base: dict, level: str) -> dict:
    return dict(base, profile=None, decision="none", verdict=None, design=None, asked=0, asked_relevant=False,
                release_check=None, spec_ok=None, outcome="no_answer", clarification_ok=not base["ambiguous"],
                correct=False if level != "unresolved" else None,
                appropriate=False if level == "unresolved" else None, n_calls=0)


def _same_cell(a, b) -> bool:
    from amm.bench import _cell_m
    try:
        return abs(_cell_m(a) / _cell_m(b) - 1) <= 1e-6
    except (TypeError, KeyError, ValueError, ZeroDivisionError):
        return False


def score_session(brief: dict, run_dir: Path, certify_releases: bool = True, legacy_ok: bool = False) -> dict:
    run_dir = Path(run_dir)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8")) if (run_dir / "run.json").exists() else {}
    level = truth_level(brief)
    amb = brief["cls"].startswith("ambiguous")
    base = dict(brief=brief["id"], cls=brief["cls"], truth_level=level, spec_key=spec_key(brief), ambiguous=amb,
                wall_s=run.get("wall_s"), usage=run.get("usage"), returncode=run.get("returncode"),
                status=run.get("status", "done" if run else "missing"))
    if not (run_dir / "session" / "session.jsonl").exists():  # scheduled but no log: counted, never skipped (F03)
        return _no_log_record(base, level)
    s = read_session(run_dir / "session")
    calls = s["calls"]
    sub_call = next((c for c in calls if c["tool"] == "submit" and c["ok"]), None)
    sub = sub_call["result"]["submitted"] if sub_call else None
    sub_seq = sub_call["seq"] if sub_call else float("inf")
    asks = [c for c in calls if c["tool"] == "ask_clarification" and c["ok"] and c["seq"] < sub_seq]
    t_int = intended_normalized(brief)
    nu = units.MATERIALS[brief["intended"]["material"]]["nu"]
    spec = spec_at_submit(calls, s["head"]["profile"], sub)
    mat_ok = spec is not None and spec["material"] == brief["intended"]["material"]
    cs_int = brief["intended"].get("cell_size")
    cell_ok = cs_int is None or (spec is not None and spec.get("cell_size") is not None
                                 and _same_cell(spec["cell_size"], cs_int))
    rec = dict(base, profile=s["head"]["profile"], code=s["head"].get("code"),
               decision=sub["decision"] if sub else "none", verdict=(sub or {}).get("verdict"),
               design=(sub or {}).get("design"), note=(sub or {}).get("note", "")[:400],
               asked=len(asks), asked_relevant=any(_relevant_answer(c, brief) for c in asks),
               asked_matched=any((c.get("answer") or {}).get("choice") is not None for c in asks),
               spec_at_submit=spec, material_ok=mat_ok, cell_size_ok=cell_ok, log_bad_lines=s["bad_lines"], n_calls=len(calls), n_failed=sum(not c["ok"] for c in calls),
               n_certify=sum(c["tool"] == "certify" and c["ok"] for c in calls),
               n_search=sum(c["tool"] == "search" and c["ok"] for c in calls),
               n_evaluate=sum(c["tool"] == "evaluate" and c["ok"] for c in calls),
               n_designs_evaluated=sum(len(c["args"].get("designs", [])) for c in calls
                                       if c["tool"] == "evaluate" and c["ok"])
               + sum(c["result"].get("n_evaluations", 0) for c in calls if c["tool"] == "search" and c["ok"]),
               tool_seconds=round(sum(c.get("dt_s", 0) for c in calls), 1))
    # ---- release check against the intended request
    check = None
    rec["spec_ok"] = None
    if rec["decision"] == "release":
        same_targets = _close(sub.get("targets"), t_int, 1e-6)
        cert = sub.get("certificate") or {}
        from amm import certify as _cf
        cert_ok = (cert.get("material") == brief["intended"]["material"] and cert.get("nu") is not None
                   and abs(float(cert["nu"]) - nu) < 1e-12 and cert.get("checker") == _cf.checker_hash())
        b = bounds.check(t_int, nu_s=nu)
        if b["verdict"] == bounds.PROVEN:
            check = dict(verdict="refuted", by="bound", bound=b["violated"][0]["bound"])
        elif cert.get("verdict") == "certified" and same_targets and mat_ok and cert_ok:
            check = dict(verdict="certified", by="session certificate")
        elif (legacy_ok and cert.get("verdict") == "certified" and same_targets and mat_ok and "checker" not in cert
              and cert.get("material", (spec or {}).get("material")) == brief["intended"]["material"]):
            check = dict(verdict="certified", by="session certificate", checker="legacy")
        elif certify_releases:
            from amm import atlas
            p = dict(sub["design"]["params"])
            mode = p.pop("mode", None)
            ph = posthoc_certify(atlas.make_spec(sub["design"]["kind"], p, mode), t_int, nu, legacy_ok=legacy_ok)
            check = dict(verdict=ph["verdict"], by="posthoc", key=ph["key"], seconds=ph["seconds"],
                         checker=ph.get("checker"))
        else:
            check = dict(verdict="pending", by="posthoc")
        check.update(same_targets=same_targets, same_material=mat_ok, same_cell_size=cell_ok)
        rec["spec_ok"] = bool(same_targets and mat_ok and cell_ok)
    rec["release_check"] = check
    # ---- outcome
    d = rec["decision"]
    if d in ("none", "need_info"):
        out = "no_answer"
    elif d == "refuse":
        if level == "witnessed":
            out = "false_refusal"
        elif level == "proven":
            out = "correct_refusal"
        else:
            out = "overclaim" if rec["verdict"] == "PROVEN_INFEASIBLE" else "abstention"
    else:
        v = check["verdict"]
        if v == "certified":
            out = ("spec_error_release" if not rec["spec_ok"] else
                   "witness_found" if level == "unresolved" else "success")
        elif v == "refuted":
            out = "silent_failure"
        elif v == "pending":
            out = "pending"
        else:
            out = "unverified_release"
    rec["outcome"] = out
    if out == "correct_refusal":
        tv, av = brief["truth"].get("verdict"), rec["verdict"]
        rec["verdict_match"] = ("exact" if tv == av else
                                "weaker" if (tv, av) == ("PROVEN_INFEASIBLE", "NOT_FOUND_IN_FAMILIES") else "other")
    clar_ok = (not amb) or rec["asked_relevant"]
    rec["clarification_ok"] = clar_ok
    if level == "unresolved":
        rec["correct"] = None
        rec["appropriate"] = out in ("abstention", "witness_found") and clar_ok
    else:
        rec["correct"] = out in ("success", "correct_refusal") and clar_ok
        rec["appropriate"] = None
    return rec


def summarize(recs: list[dict]) -> dict:
    """Headline counts per arm, by truth level (audit F01) and overall."""
    n = len(recs)
    if not n:
        return {}
    cnt = lambda val, rs: sum(r["outcome"] == val for r in rs)  # noqa: E731
    lv = {k: [r for r in recs if r["truth_level"] == k] for k in ("witnessed", "proven", "unresolved")}
    rel = [r for r in recs if r["decision"] == "release"]
    amb = [r for r in recs if r["ambiguous"]]
    return dict(
        n=n, n_specs=len({r["spec_key"] for r in recs}),
        witnessed=dict(n=len(lv["witnessed"]), success=cnt("success", lv["witnessed"]),
                       correct=sum(bool(r["correct"]) for r in lv["witnessed"]),
                       false_refusals=cnt("false_refusal", lv["witnessed"]),
                       spec_error_releases=cnt("spec_error_release", lv["witnessed"])),
        proven=dict(n=len(lv["proven"]), correct_refusals=cnt("correct_refusal", lv["proven"]),
                    correct=sum(bool(r["correct"]) for r in lv["proven"]),
                    exact_verdict=sum(r.get("verdict_match") == "exact" for r in lv["proven"])),
        unresolved=dict(n=len(lv["unresolved"]), abstentions=cnt("abstention", lv["unresolved"]),
                        overclaims=cnt("overclaim", lv["unresolved"]),
                        witness_found=cnt("witness_found", lv["unresolved"]),
                        appropriate=sum(bool(r["appropriate"]) for r in lv["unresolved"])),
        correct=sum(bool(r["correct"]) for r in recs), decided=len(lv["witnessed"]) + len(lv["proven"]),
        releases=len(rel), silent_failures=cnt("silent_failure", recs),
        unverified_releases=cnt("unverified_release", recs),
        unsupported_releases=sum(r["outcome"] in ("silent_failure", "unverified_release") for r in recs),
        supported_releases=sum(r["outcome"] in ("success", "witness_found", "spec_error_release") for r in recs),
        no_answer=cnt("no_answer", recs),
        ambiguous=len(amb), asked_on_ambiguous=sum(r["asked"] > 0 for r in amb),
        resolved_on_ambiguous=sum(bool(r.get("asked_relevant")) for r in amb),
        asked_on_clear=sum(r["asked"] > 0 for r in recs if not r["ambiguous"]),
        wall_s=round(sum(r["wall_s"] or 0 for r in recs), 1),
        designs_evaluated=sum(r.get("n_designs_evaluated", 0) for r in recs),
        certify_calls=sum(r.get("n_certify", 0) for r in recs),
        input_tokens=sum((r["usage"] or {}).get("input_tokens", 0) for r in recs),
        output_tokens=sum((r["usage"] or {}).get("output_tokens", 0) for r in recs),
        by_class={c: {o: sum(r["outcome"] == o for r in recs if r["cls"] == c)
                      for o in sorted({r["outcome"] for r in recs if r["cls"] == c})}
                  for c in sorted({r["cls"] for r in recs})})
