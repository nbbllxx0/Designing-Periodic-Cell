"""Five-outcome evidence cards built from a session log (plan section 2, S2):

  1. certified candidate      2. refuted candidate      3. request proven infeasible by a named bound
  4. not found in a bounded search of the declared families (with search budget and atlas-estimate status)
  5. numerically undetermined

The cards are a VIEW of the evidence already in the log (certify, check_bounds, search, atlas_suggest records and
the full certificates). They do not change any verdict. The binding five-outcome schema and "refusal must cite an
evidence record" rule are plan item B1 (after E4); `consistency` below only flags a submission whose stated
outcome has no supporting record in the session.
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def schema_rules():
    """amm/outcomes.py (the binding outcome schema and refusal-evidence rule of B1) loaded from its source file
    under a private module name. It imports nothing from amm, so mock mode still never imports the amm package
    (MKL, PARDISO, torch); the mirror then applies exactly the rules amm applies."""
    p = Path(__file__).resolve().parents[1] / "amm" / "outcomes.py"
    spec = importlib.util.spec_from_file_location("_amm_outcomes_source", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

OUTCOMES = [
    ("certified", "Certified candidate",
     "every target accepted by the certificate (guarded bounds, inertia-count gap, edge guard)"),
    ("refuted", "Refuted candidate", "the certificate shows a target is violated beyond its guard band"),
    ("proven_infeasible", "Proven infeasible", "a named rigorous bound (Voigt, cubic stability, gap rules) is violated"),
    ("not_found", "Not found in families",
     "no candidate in a bounded search of the declared families; the atlas is an estimate, not a bound"),
    ("undetermined", "Numerically undetermined",
     "a claim lies inside the guard band: neither proven nor disproven at the certificate resolutions"),
]
VERDICT_OF = {"PROVEN_INFEASIBLE": "proven_infeasible", "NOT_FOUND_IN_FAMILIES": "not_found",
              "UNDETERMINED": "undetermined"}


def _design_text(d: dict | None) -> str:
    if not d:
        return "-"
    p = d.get("params", {})
    return d["kind"] + " " + ", ".join(f"{k}={v:.4g}" if isinstance(v, (int, float)) else f"{k}={v}"
                                       for k, v in p.items())


def focus_design(calls: list[dict], submission: dict | None) -> dict | None:
    """The design the session is about: the released one, else the last certified/evaluated/suggested one."""
    if submission and submission.get("design"):
        return submission["design"]
    for r in reversed(calls):
        if not r.get("ok"):
            continue
        res = r.get("result") or {}
        if r["tool"] == "certify":
            return res.get("design") or r["args"].get("design")
        if r["tool"] == "evaluate" and res.get("results"):
            return res["results"][0]["design"]
        if r["tool"] in ("search", "atlas_suggest") and res.get("best"):
            return res["best"][0]["design"]
    return None


def _fmt(x, nd=4):
    return f"{x:.{nd}g}" if isinstance(x, (int, float)) else str(x)


def _target_lines(static: dict, targets: dict) -> list[dict]:
    out = []
    b = static.get("bounds") or {}
    per = (static.get("verdict") or {}).get("targets") or {}
    for key, verdict in per.items():
        q, side = key.rsplit("_", 1)
        if q not in b:
            continue
        lo, hi = b[q]["lower"], b[q]["upper"]
        t = targets.get(key)
        rel = "<=" if side == "max" else ">="
        guarded = hi if side == "max" else lo
        out.append(dict(label=f"{q} {rel} {_fmt(t)}", value=f"guarded [{_fmt(lo)}, {_fmt(hi)}]: {verdict}",
                        margin=(t - guarded) if side == "max" else (guarded - t), verdict=verdict))
    return out


def cards(calls: list[dict], submission: dict | None, norm: dict, cert_lookup=None) -> dict:
    ev = {k: [] for k, _, _ in OUTCOMES}
    ok = [r for r in calls if r.get("ok")]
    for r in ok:
        res = r.get("result") or {}
        ref = dict(seq=r["seq"], tool=r["tool"], actor=r.get("actor"))
        if r["tool"] == "certify":
            v = res.get("verdict")
            card = {"certified": "certified", "refuted": "refuted", "undetermined": "undetermined"}.get(v)
            if card is None:
                continue
            items = [dict(label="design", value=_design_text(res.get("design")))]
            st = res.get("static") or {}
            items += _target_lines(st, res.get("targets") or {})
            for c in st.get("checks_failed") or []:
                items.append(dict(label="static check", value=c))
            g = res.get("gap")
            if g:
                gv = g.get("verdict") or {}
                si = g.get("safe_interval") or [None, None]
                items.append(dict(label="gap claim", value=f"[{_fmt(g['claim'][0])}, {_fmt(g['claim'][1])}] f*"))
                items.append(dict(label="safe interval",
                                  value=f"[{_fmt(si[0])}, {_fmt(si[1])}] f*: {gv.get('verdict')}"
                                  + (f" ({gv['reason']})" if gv.get("reason") else "")))
            if res.get("as_built"):
                items.append(dict(label="as-built +-0.01 a", value=", ".join(
                    f"{k} {'pass' if p else 'fail'}" for k, p in res["as_built"].items())
                    + (" (robust)" if res.get("robust") else " (not robust: flag, not a verdict)")))
            if cert_lookup is not None and res.get("design"):
                c = cert_lookup(res["design"], res.get("targets") or {})
                if c:
                    items.append(dict(label="certificate file", value=c["path"]))
            ev[card].append(dict(ref=ref, items=items, design=res.get("design")))
        elif r["tool"] == "check_bounds":
            if res.get("violated"):
                ev["proven_infeasible"].append(dict(ref=ref, items=[
                    dict(label=f"bound {b['bound']} ({b['scope']})",
                         value=f"{b['statement']}: target {_fmt(b['target'])} vs limit {_fmt(b['limit'])}")
                    for b in res["violated"]] + [dict(label="advisory", value=a["statement"])
                                                 for a in res.get("advisory") or []]))
            at = res.get("atlas") or {}
            if at.get("verdict") == "NOT_FOUND_IN_FAMILIES":
                ev["not_found"].append(dict(ref=ref, items=[
                    dict(label="atlas verdict", value="NOT_FOUND_IN_FAMILIES (estimate with calibrated error)"),
                    dict(label="atlas cells", value=f"{at.get('n_cells')} scanned, {at.get('n_possible')} possible, "
                                                    f"{at.get('n_clear')} clear"),
                    dict(label="best pessimistic slack",
                         value=_fmt((at.get("best") or [{}])[0].get("slack_pess", "-")))]))
        elif r["tool"] == "search" and not res.get("found"):
            best = (res.get("best") or [{}])[0]
            ev["not_found"].append(dict(ref=ref, items=[
                dict(label="bounded search", value=f"{res.get('n_evaluations')} evaluations, objective "
                                                   f"{res.get('objective')}, margin {res.get('margin')}"),
                dict(label="arms", value=", ".join(a[0] + (f"/{a[1]}" if a[1] else "") for a in res.get("arms") or [])),
                dict(label="best candidate", value=_design_text(best.get("design"))),
                dict(label="slack nominal / expected / pess.",
                     value=" / ".join(_fmt(best.get(k, "-"), 3) for k in ("slack_nominal", "slack_expected",
                                                                           "slack_pess"))),
                dict(label="atlas seeded", value=str(res.get("atlas_seeded")))]))
    sub_card, consistency = None, None
    if submission:
        d = submission.get("decision")
        if d == "release":
            sub_card = "certified"
        elif d == "refuse":
            sub_card = VERDICT_OF.get(submission.get("verdict"))
        if sub_card is not None and not ev[sub_card]:
            consistency = (f"submitted as '{sub_card}' but this session holds no supporting record "
                           "(plan B1 will require the refusal to cite one)")
    out = []
    for k, title, definition in OUTCOMES:
        status = "submitted" if k == sub_card else ("evidence" if ev[k] else "none")
        out.append(dict(id=k, title=title, definition=definition, status=status, records=ev[k][-3:],
                        n_records=len(ev[k])))
    return dict(cards=out, submission=dict(decision=submission.get("decision"), verdict=submission.get("verdict"),
                                           note=submission.get("note")) if submission else None,
                submitted_outcome=sub_card, consistency=consistency,
                need_info=bool(submission and submission.get("decision") == "need_info"))


def certificate_view(c: dict) -> dict:
    """The parts of a full certificate the result panels show. c = {key, path, certificate}."""
    cert = c["certificate"]
    b = cert.get("blocks", {})
    out = dict(key=c["key"], path=c["path"], verdict=cert.get("verdict"), robust=cert.get("robust"),
               spec=cert.get("spec"), targets=cert.get("targets"), solver=cert.get("solver"), timing=cert.get("timing"))
    st = b.get("static")
    if st:
        conv = st.get("convergence") or {}
        q = {k: {kk: v.get(kk) for kk in ("lower", "upper", "extrapolated", "mode", "converged")}
             for k, v in (conv.get("quantities") or {}).items()}
        rows = st.get("resolutions") or {}
        tensor, src = None, None
        if rows:
            n = max(rows, key=lambda s: int(s))
            tensor, src = {k: rows[n].get(k) for k in ("C11", "C12", "C44")}, f"resolution {n}, phase 0"
        elif st.get("phase_rows"):
            pr = st["phase_rows"]
            nmax = max(int(k.split("@")[0]) for k in pr)
            sel = [v for k, v in pr.items() if int(k.split("@")[0]) == nmax]
            tensor = {k: sum(v[k] for v in sel) / len(sel) for k in ("C11", "C12", "C44")}
            src = f"resolution {nmax}, mean of {len(sel)} grid phases"
        out["static"] = dict(verdict=st.get("verdict"), quantities=q, checks_failed=st.get("checks_failed"),
                             resolutions=conv.get("resolutions"), safety=conv.get("safety"), tensor=tensor,
                             tensor_source=(src + "; unguarded finest-rung values") if src else None)
    bl = b.get("bloch")
    if bl:
        conv = bl.get("convergence") or {}
        claim = bl.get("claim") or {}
        si = conv.get("safe_interval")
        margins = None
        if si and claim and None not in si:
            margins = dict(lower=claim["f_lo"] - si[0], upper=si[1] - claim["f_hi"])
        out["bloch"] = dict(verdict=bl.get("verdict"), claim=claim, safe_interval=si, margins=margins,
                            lower_edge=conv.get("lower_edge"), upper_edge=conv.get("upper_edge"),
                            edges=conv.get("edges"), safety=conv.get("safety"), n_k=bl.get("n_k"),
                            resolutions={k: dict(passed=v.get("passed"), n_failures=v.get("n_failures"))
                                         for k, v in (bl.get("resolutions") or {}).items()})
    ab = b.get("as_built")
    if ab:
        out["as_built"] = dict(offset=ab.get("offset"), passed=ab.get("passed"),
                               cases={k: dict(passed=v.get("passed"), density=v.get("density"))
                                      for k, v in (ab.get("cases") or {}).items()})
    return out


# ================================================================================================================
# B1: the binding outcome schema (amm-outcome/1) as the session holds it
# ================================================================================================================
OUTCOME_ORDER = ("certified_candidate", "refuted_candidate", "proven_infeasible", "not_found_in_families",
                 "numerically_undetermined", "need_info")
LEGACY_ID = {"certified_candidate": "certified", "refuted_candidate": "refuted",
             "proven_infeasible": "proven_infeasible", "not_found_in_families": "not_found",
             "numerically_undetermined": "undetermined"}


def b1_view(session, calls: list[dict]) -> dict:
    """The amm-outcome/1 view of a session (mock mirror or live amm.tools.Session): every evidence record with the
    outcome it supports and whether it holds for the CURRENT spec, the records each refusal verdict could cite now,
    the outcome card of the submission, and the last submit the refusal-evidence rule rejected."""
    R = schema_rules()
    recs = []
    for e in getattr(session, "evidence", []) or []:
        try:
            holds = bool(session._holds(e))
        except Exception:  # noqa: BLE001 -- e.g. targets that no longer normalize
            holds = False
        recs.append(dict(seq=e["seq"], tool=e["tool"], kind=e["kind"], outcome=R.EVIDENCE_OUTCOME[e["kind"]],
                         summary=e.get("summary"), holds=holds))
    groups = []
    for oid in OUTCOME_ORDER:
        title, definition = R.OUTCOMES[oid]
        rs = [r for r in recs if r["outcome"] == oid]
        groups.append(dict(id=oid, legacy=LEGACY_ID.get(oid), title=title, definition=definition, records=rs[-4:],
                           n_records=len(rs), n_holding=sum(r["holds"] for r in rs)))
    can_cite = {v: [r["seq"] for r in recs if r["holds"] and r["kind"] in kinds]
                for v, kinds in R.VERDICT_EVIDENCE.items()}
    card, last_reject, sub_seq = None, None, None
    for r in calls:
        if r.get("tool") != "submit":
            continue
        if r.get("ok"):
            card = (r.get("result") or {}).get("outcome_card")
            sub_seq, last_reject = r["seq"], None
        elif sub_seq is None:
            last_reject = dict(seq=r["seq"], args=r.get("args"), error=r.get("error"),
                               refusal_rule=str(r.get("error", "")).startswith(R.REFUSAL_ERROR))
    return dict(schema=R.OUTCOME_SCHEMA, profile=getattr(session, "profile", None),
                evidence_checked=getattr(session, "profile", None) in R.EVIDENCE_PROFILES,
                groups=groups, records=recs, can_cite=can_cite, hints=dict(R.VERDICT_HINT),
                refusal_rule={k: list(v) for k, v in R.VERDICT_EVIDENCE.items()},
                card=card, submit_seq=sub_seq, last_rejected_submit=last_reject)
