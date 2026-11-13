"""Versioned outcome schema and the evidence a refusal must cite (plan item B1, section 2 S2).

Five outcomes of a design request, plus `need_info`:

  certified_candidate        the certificate accepts every target (guarded static bounds, inertia-count gap)
  refuted_candidate          the certificate shows a target is violated beyond its guard band
  proven_infeasible          a named rigorous bound (Voigt, cubic stability, gap rules) is violated
  not_found_in_families      nothing found in a bounded search of the declared families (the atlas verdict is an
                             estimate with calibrated search-tier error ranges, not a bound)
  numerically_undetermined   a claim lies inside the guard band: neither proven nor disproven at the certificate
                             resolutions
  need_info                  the request cannot be stated in solver units; the session stops and asks

Evidence records. The session keeps one record per tool result that can support an outcome:
  bound_violation            `check_bounds` with a violated rigorous bound, or `set_target` rejecting a gap that
                             contains f = 0 (rule W1, enforced on input; valid while no gap target is set)
  atlas_not_found            `check_bounds` whose atlas verdict is NOT_FOUND_IN_FAMILIES
  search_not_found           `search` that found no design (`found` false)
  certificate_undetermined   `certify` with verdict undetermined
  certificate_refuted        `certify` with verdict refuted
  certificate_certified      `certify` with verdict certified (supports a release only)
A record supports a refusal only for the spec it was computed for: the same normalized targets and Poisson ratio
(certificates: the same material too; atlas and search records: families covering every declared family).

Refusal rule (profile C; profile B, the E4 ablation arm without bounds or certificates, keeps its contract and
gets an outcome card with `evidence_checked` false):
  PROVEN_INFEASIBLE      needs bound_violation
  NOT_FOUND_IN_FAMILIES  needs atlas_not_found or search_not_found
  UNDETERMINED           needs certificate_undetermined
  OTHER                  needs any record except certificate_certified; the outcome follows the record
`submit(refuse)` cites records by `evidence` (their seq numbers) or, if none are given, cites every matching record
held; without one it is rejected with a message naming what is missing and what is held.
"""
from __future__ import annotations

OUTCOME_SCHEMA = "amm-outcome/1"

OUTCOMES = {
    "certified_candidate": ("Certified candidate",
                            "every target accepted by the certificate (guarded static bounds, inertia-count gap, "
                            "edge guard)"),
    "refuted_candidate": ("Refuted candidate", "the certificate shows a target is violated beyond its guard band"),
    "proven_infeasible": ("Proven infeasible",
                          "a named rigorous bound (Voigt, cubic stability, gap rules) is violated"),
    "not_found_in_families": ("Not found in families",
                              "nothing found in a bounded search of the declared families; the atlas is an "
                              "estimate with calibrated error ranges, not a bound"),
    "numerically_undetermined": ("Numerically undetermined",
                                 "a claim lies inside the guard band: neither proven nor disproven at the "
                                 "certificate resolutions"),
    "need_info": ("Information needed", "the request cannot be stated in solver units; the session stops and asks"),
}
# profile B only (no certificates): a release the system did not verify; not one of the five outcomes
UNVERIFIED = ("uncertified_release", "Uncertified release",
              "released without a certificate (profile B has no certify tool); not verified")
# export of a design without a certificate for the current targets (search-tier values only)
NOT_CERTIFIED = ("not_certified", "Not certified",
                 "no certificate of this design for the current targets in this session; any values are search-tier "
                 "estimates")
CERT_OUTCOME = {"certified": "certified_candidate", "refuted": "refuted_candidate",
                "undetermined": "numerically_undetermined"}

EVIDENCE_OUTCOME = {
    "bound_violation": "proven_infeasible",
    "atlas_not_found": "not_found_in_families",
    "search_not_found": "not_found_in_families",
    "certificate_undetermined": "numerically_undetermined",
    "certificate_refuted": "refuted_candidate",
    "certificate_certified": "certified_candidate",
}
_REFUSAL_KINDS = ("bound_violation", "atlas_not_found", "search_not_found", "certificate_undetermined",
                  "certificate_refuted")
VERDICT_EVIDENCE = {
    "PROVEN_INFEASIBLE": ("bound_violation",),
    "NOT_FOUND_IN_FAMILIES": ("atlas_not_found", "search_not_found"),
    "UNDETERMINED": ("certificate_undetermined",),
    "OTHER": _REFUSAL_KINDS,
}
VERDICT_HINT = {
    "PROVEN_INFEASIBLE": "a check_bounds result with a violated rigorous bound (call check_bounds)",
    "NOT_FOUND_IN_FAMILIES": ("a check_bounds result with atlas verdict NOT_FOUND_IN_FAMILIES, or a search over every "
                              "declared family that found nothing"),
    "UNDETERMINED": "a certificate with verdict undetermined for the current targets (call certify)",
    "OTHER": "any bound, atlas, search or certificate record for the current spec",
}
PRIORITY = ("proven_infeasible", "not_found_in_families", "numerically_undetermined", "refuted_candidate")
# the outcome a refusal claims by its verdict (profile B records the claim without checking it)
VERDICT_OUTCOME = {"PROVEN_INFEASIBLE": "proven_infeasible", "NOT_FOUND_IN_FAMILIES": "not_found_in_families",
                   "UNDETERMINED": "numerically_undetermined", "OTHER": None}
EVIDENCE_PROFILES = ("C",)
REFUSAL_ERROR = "refusal needs evidence: "  # prefix of every rejection by the refusal rule (amm.tools.replay tags it)


def evidence_from_result(tool: str, result: dict | None, ok: bool, error: str | None = None) -> list[dict]:
    """Evidence kinds (with a one-line summary) carried by one tool result. Context (targets, nu, families) is
    added by the session."""
    out = []
    if tool == "check_bounds" and ok:
        for b in result.get("violated") or []:
            out.append(dict(kind="bound_violation", bound=b["bound"],
                            summary=f"bound {b['bound']} ({b['scope']}): {b['statement']}; target {b['target']:.6g} "
                                    f"vs limit {b['limit']}"))
        at = result.get("atlas") or {}
        if at.get("verdict") == "NOT_FOUND_IN_FAMILIES":
            out.append(dict(kind="atlas_not_found",
                            summary=f"atlas NOT_FOUND_IN_FAMILIES: {at.get('n_cells')} cells, {at.get('n_possible')} "
                                    f"possible with the most favourable search-tier error (estimate, not a bound)"))
    elif tool == "search" and ok and not result.get("found"):
        best = (result.get("best") or [{}])[0]
        out.append(dict(kind="search_not_found",
                        summary=f"bounded search: {result.get('n_evaluations')} evaluations, objective "
                                f"{result.get('objective')}, margin {result.get('margin')}, best slack "
                                f"{best.get('slack_' + str(result.get('objective')))}; nothing found"))
    elif tool == "certify" and ok:
        v = result.get("verdict")
        if v in ("certified", "refuted", "undetermined"):
            d = result.get("design") or {}
            out.append(dict(kind=f"certificate_{v}", summary=f"certificate {v}: {d.get('kind')} {d.get('params')}"))
    elif tool == "set_target" and not ok and error and "cannot contain f = 0" in error:
        out.append(dict(kind="bound_violation", bound="W1",
                        summary="bound W1 (any): a complete gap cannot contain f = 0 (rejected by set_target)"))
    return out


def refusal_outcome(verdict: str, cited: list[dict]) -> str:
    outs = {EVIDENCE_OUTCOME[e["kind"]] for e in cited}
    return next(o for o in PRIORITY if o in outs)


def card(outcome: str | None, decision: str, verdict: str | None, evidence: list[dict], profile: str,
         design: dict | None = None) -> dict:
    """The outcome card returned by `submit` (schema amm-outcome/1). outcome None: a profile-B refusal with
    verdict OTHER (unclassified, not checked)."""
    if outcome == UNVERIFIED[0]:
        title, definition = UNVERIFIED[1:]
    elif outcome == NOT_CERTIFIED[0]:
        title, definition = NOT_CERTIFIED[1:]
    elif outcome is None:
        title, definition = "Unclassified refusal", "verdict OTHER without an evidence check (profile B)"
    else:
        title, definition = OUTCOMES[outcome]
    return dict(schema_version=OUTCOME_SCHEMA, outcome=outcome, title=title, definition=definition,
                decision=decision, verdict=verdict, design=design, profile=profile,
                evidence_checked=profile in EVIDENCE_PROFILES,
                evidence=[dict(seq=e["seq"], tool=e["tool"], kind=e["kind"], outcome=EVIDENCE_OUTCOME[e["kind"]],
                               summary=e["summary"]) for e in evidence])


def rejection(verdict: str, held: list[dict]) -> str:
    msg = (f"{REFUSAL_ERROR}refuse with verdict {verdict} must cite an evidence record held in this session for the "
           f"current spec: {VERDICT_HINT[verdict]}.")
    if held:
        msg += " Records held for the current spec: " + "; ".join(
            f"seq {e['seq']} {e['kind']} (supports {EVIDENCE_OUTCOME[e['kind']]})" for e in held) + "."
    else:
        msg += " No evidence record is held for the current spec."
    return msg


def audit_log(recs: list[dict]) -> dict:
    """Static check of a recorded session under the refusal rule, from the LOGGED results (no solver runs): the
    submitted refusal, the evidence the session held for the spec at submission, and whether the rule accepts it.
    Context matching uses the normalized targets each logged result reports and the families set by
    set_constraints (the material enters through the normalized targets; the Poisson ratio is not re-checked).
    The authoritative check is amm.tools.replay, which re-runs the session."""
    import json
    head = next((r for r in recs if r.get("type") == "session"), {})
    calls = [r for r in recs if r.get("type") == "call"]
    sub = next((r for r in calls if r["tool"] == "submit" and r["ok"]), None)
    out = dict(profile=head.get("profile"), schema=head.get("schema"), submitted=None, rule_applies=False)
    if sub is None:
        return out
    a = sub["args"]
    out["submitted"] = dict(seq=sub["seq"], decision=a.get("decision"), verdict=a.get("verdict"))
    if a.get("decision") != "refuse" or head.get("profile") not in EVIDENCE_PROFILES:
        return out
    out["rule_applies"] = True
    s = sub["result"]["submitted"].get("spec")
    if s is None:  # logs before 2026-11-06 (audit F04) do not record the spec at submission
        tg = None
        for c in calls:
            if c["seq"] < sub["seq"] and c["ok"] and c["tool"] in ("set_target", "undo"):
                r = c["result"] or {}
                tg = r.get("targets", (r.get("state") or {}).get("targets", tg))
        s = dict(targets=tg or {})
    # current normalized targets: the most recent logged normalization before submission
    norm = None
    for c in calls:
        if c["seq"] >= sub["seq"] or not c["ok"]:
            continue
        r = c["result"] or {}
        for k in ("normalized", "normalized_targets"):
            if isinstance(r.get(k), dict):
                norm = r[k]
    canon = lambda x: json.dumps(x, sort_keys=True)  # noqa: E731
    final_fams = None
    for c in calls:
        if c["seq"] < sub["seq"] and c["ok"] and c["tool"] == "set_constraints":
            final_fams = (c["result"] or {}).get("families", final_fams)
    final_fams = set(final_fams or ("tpms", "struts", "resonator"))
    held, fams = [], ("tpms", "struts", "resonator")
    for c in calls:
        if c["seq"] >= sub["seq"]:
            continue
        if c["ok"] and c["tool"] == "set_constraints":
            fams = (c["result"] or {}).get("families", fams)
        for e in evidence_from_result(c["tool"], c.get("result"), c["ok"], c.get("error")):
            r = c.get("result") or {}
            if e["kind"] == "bound_violation" and c["tool"] == "set_target":
                match = "gap" not in (s.get("targets") or {})
            elif c["tool"] == "certify":
                match = canon(r.get("targets")) == canon(norm)
            else:
                match = canon(r.get("normalized_targets")) == canon(norm)
                if e["kind"] in ("atlas_not_found", "search_not_found"):
                    searched = (c.get("args") or {}).get("families") if c["tool"] == "search" else None
                    match = match and final_fams <= set(searched or fams)
            held.append(dict(e, seq=c["seq"], tool=c["tool"], matches_spec=match))
    allowed = VERDICT_EVIDENCE.get(a.get("verdict"), ())
    ok = [e for e in held if e["matches_spec"] and e["kind"] in allowed]
    out.update(held=held, accepted=bool(ok), cited=[e["seq"] for e in ok],
               outcome=refusal_outcome(a.get("verdict"), ok) if ok else None)
    return out
