"""paper/ANALYSIS_failures.md: every undetermined, refuted, marginal, inconclusive, refused and failed case of V1b,
V1c, V3, E4, V2 (failed matrix rows) and V6 (not-certified calls, flags), with the cause as recorded in the result files (plan item A1).

Causes are copied from the certificates (`verdict.reason`, `checks_failed`), the comparison tables and the NOTES
files; nothing is re-solved. Every count written here is registered in the claims ledger.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

from common import PAPER, ROOT, Ledger, md_escape, pct, read_csv, read_json, read_text

S = "scripts/paper/failures.py"


def _p(params) -> str:
    if isinstance(params, str):
        params = json.loads(params)
    return ", ".join(f"{k} {v:g}" if isinstance(v, (int, float)) else f"{k} {v}" for k, v in params.items())


def _tab(header, rows) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append("| " + " | ".join(md_escape(x) for x in r) + " |")
    return out


def _short(s, n=150) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ------------------------------------------------------------------------------------------------------------ V1b
def _v1b(L: Ledger) -> list[str]:
    src = "results/verification/v1b/T4_v1b.csv"
    v = read_csv(src)
    out = ["## 1. V1b two-sided check (Q2-FCM reference, six cells)", "",
           "Status rule (v1b/NOTES.md section 0.5): a guarded bound or safe edge is *sound* if it clears the "
           "reference R by 2u, *marginal* within R ± 2u, *unsound* beyond. No status is unsound; the marginal ones "
           "are listed below with the recorded cause.", ""]
    rows, n = [], collections.Counter()
    for r in v:
        if not (r["check"].startswith("static:") or r["check"].startswith("gap:")):
            continue
        st = [r["status_lower"], r["status_upper"]]
        if "marginal" not in st and "unsound" not in st:
            continue
        q = r["check"].split(":")[1]
        if q == "density":
            cause = ("density guard band (~1e-4 rel.) narrower than the Q2 soft-indicator volume uncertainty; "
                     "the sharp/analytic density lies inside amm's bounds (NOTES 1.2)")
        elif q == "nu100":
            cause = "difference -1.3e-4 against 2u = 8.5e-4: inside the reference band (NOTES 1.2)"
        elif q == "hi_edge":
            cause = ("ligament w 0.061 spans 1-2 voxels; the reference edge depends on which three Q2 levels are "
                     "used (16-20-24: lower marginal; 24-28-32: upper marginal; never unsound; NOTES deviation 6)")
        else:
            cause = "see v1b/NOTES.md"
        for side, s_ in zip(("lower", "upper"), st):
            if s_ in ("marginal", "unsound"):
                n[(q if q in ("density", "nu100") else "gap edge", s_)] += 1
        rows.append([r["cell"].split("_nu")[0], q, f"{st[0] or '–'} / {st[1] or '–'}",
                     f"[{float(r['amm_lower']):.5g}, {float(r['amm_upper']):.5g}]" if r["amm_lower"] else "–",
                     f"{float(r['ref']):.5g} ± {float(r['ref_u']):.2g}" if r["ref"] else "–", cause])
    out += _tab(["cell", "quantity", "lower / upper status", "amm bounds", "reference R ± u", "recorded cause"], rows)
    tot = sum(n.values())
    L.add("FAIL", "v1b.marginal_statuses", tot, src, "marginal entries of status_lower/upper (static + gap rows)",
          status="derived", script=S)
    for (q, s_), k in sorted(n.items()):
        L.add("FAIL", f"v1b.{s_}.{q}", k, src, f"{s_} statuses on {q} rows", status="derived", script=S)
    claims = [r for r in v if r["check"].startswith("claim:") and r["claim_status"] != "agrees"]
    out += ["", f"{tot} marginal statuses in total. Certified claims that do not *agree*: {len(claims)}.", ""]
    crow = []
    for r in claims:
        _, which, q = r["check"].split(":")
        crow.append([r["cell"].split("_nu")[0], which, q, r["target"], r["claim_status"],
                     pct(float(r["margin_rel"]), 3) if r["margin_rel"] else "–",
                     "margin below the reference uncertainty (NOTES 1.2 (ii))"])
    out += _tab(["cell", "claim set", "quantity", "target", "status", "margin", "recorded cause"], crow)
    L.add("FAIL", "v1b.claims_not_agree", len(claims), src, "claim rows with claim_status != agrees",
          status="derived", script=S)
    out += ["", "All six V1b cells are amm-certified designs; V1b has no undetermined or refuted amm verdict "
            "(summary.json amm_verdict).", ""]
    vs = read_json("results/verification/v1b/summary.json")
    nc = sum(c["amm_verdict"] != "certified" for c in vs.values())
    L.add("FAIL", "v1b.amm_not_certified", nc, "results/verification/v1b/summary.json", "amm_verdict != certified",
          status="derived", script=S)
    assert nc == 0
    return out


# ------------------------------------------------------------------------------------------------------------ V1c
def _v1c(L: Ledger) -> list[str]:
    src = "results/verification/dolfinx/summary.csv"
    dv = read_csv(src)
    out = ["## 2. V1c third-party check (DOLFINx-MPC, 8 cells, 16 edges)", "",
           "Edge verdicts under the final rule and the three reported variants (from `dolfinx/<case>.json`). "
           "No variant has an unsound edge.", ""]
    rows, cnt = [], collections.Counter()
    for r in dv:
        cj = read_json(f"results/verification/dolfinx/{r['case']}.json")
        vv = {}
        for vk, key in (("final", None), ("coarse", "coarse_reference"), ("hmax", "hmax_reference"),
                        ("per_k", "per_k_reference")):
            blk = cj if key is None else cj[key]
            vv[vk] = (blk["verdict_lo"], blk["verdict_hi"])
            for s_ in vv[vk]:
                cnt[(vk, s_)] += 1
        if any(s_ != "sound" for p in vv.values() for s_ in p):
            rows.append([r["case"].split("_nu")[0], r["model"]] + [f"{a} / {b}" for a, b in vv.values()])
    out += _tab(["cell", "model", "final (lo / hi)", "coarse levels", "h = largest edge", "per-k"], rows)
    for (vk, s_), k in sorted(cnt.items()):
        L.add("FAIL", f"v1c.{vk}.{s_}", k, "results/verification/dolfinx/<case>.json", f"{vk} edge verdicts",
              status="derived", script=S)
    thin = [r for r in dv if r["case"].startswith("thin_sl")][0]
    mlo = (float(thin["amm_safe_lo"]) - float(thin["ref_lo"])) / (2 * float(thin["u_lo"]))
    L.add("FAIL", "v1c.thin_lo_margin_over_2u", f"{mlo:.2f}", src, "(amm_safe_lo - ref_lo)/(2 u_lo), thin_sl",
          status="derived", script=S)
    out += ["", f"Recorded causes (dolfinx/NOTES.md, 'Unresolved' and the variant table):",
            f"- Thin resonator (SL c 0.402, w 0.061) lower edge marginal in every variant (margin {mlo:.2f} × 2u): "
            "the reference is the n = 30 value because the fcm sequence is not monotone; a finer level (n = 40) "
            "was not run.",
            "- With the levels as first planned (coarse variant) three more upper edges are marginal "
            "(CB c 0.5 w 0.2, c 0.6 w 0.3, c 0.7 w 0.3); the final count of one marginal edge depends on "
            "deviations 5 and 9, decided after the first comparison numbers existed.",
            "- Gate: the literal pre-registered verdict is **weak**, because the identity test requires residuals "
            "<= 1e-8 on both sides and DOLFINx reaches 9.7e-8 (deviation 7); `summary.csv` `identity_passed` "
            "checks frequencies only. The qualified assessment is adequate (NOTES correction log 2026-11-08).", ""]
    nt = read_text("results/verification/dolfinx/NOTES.md")
    if re.search(r"pre-registered gate gives \*strong\*", nt) and "Literal pre-registered gate verdict: WEAK" in nt:
        L.conflict("FAIL", "V1c gate verdict wording inside dolfinx/NOTES.md",
                   {"dolfinx/NOTES.md 'Verdict for the venue gate' section": "'the pre-registered gate gives strong'",
                    "dolfinx/NOTES.md correction log 2026-11-08": "'Literal pre-registered gate verdict: WEAK'"},
                   script=S, note="stale sentence left above the correction log; the paper uses weak (literal) / "
                                  "adequate (qualified) per the plan wording rule")
    return out


# ------------------------------------------------------------------------------------------------------------ V3
def _cert(r):
    p = ROOT / f"results/verification/v14/bench/certs/{r['target_id']}_{r['final_hash']}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _cause(d) -> tuple[str, str]:
    """(short reason class, detail) from a certificate."""
    b = d["blocks"]
    st, bl = b.get("static") or {}, b.get("bloch") or {}
    parts, cls = [], []
    if st and st.get("verdict", {}).get("verdict") not in (None, "certified"):
        cls.append(f"static {st['verdict']['verdict']}")
        parts += st.get("checks_failed", [])
    if bl and bl.get("verdict", {}).get("verdict") not in (None, "certified"):
        reason = bl["verdict"].get("reason", "")
        cls.append(f"gap: {reason}")
        conv = bl.get("convergence", {})
        si = conv.get("safe_interval")
        cl = bl.get("claim", {})
        fails = {k: v.get("n_failures") for k, v in bl.get("resolutions", {}).items()}
        det = f"claim [{cl.get('f_lo', 0):.4f}, {cl.get('f_hi', 0):.4f}]"
        if si:
            det += ", safe interval [" + ", ".join("none" if x is None else f"{x:.4f}" for x in si) + "]"
        if any(fails.values()):
            det += ", count failures per n " + ", ".join(f"{k}: {v}" for k, v in fails.items())
        parts.append(det)
    return "; ".join(cls) or d.get("verdict", ""), "; ".join(parts)


def _v3(L: Ledger) -> list[str]:
    src = "results/verification/v14/bench/runs.csv"
    rr = read_csv(src)
    out = ["## 3. V3 search benchmark (20 primary targets × 6 methods, 4 calibration targets × 2 methods)", ""]
    cnt = collections.Counter((r["set"], r["method"], r["cert_verdict"]) for r in rr)
    hdr = ["set", "method", "certified", "undetermined", "refuted", "search-tier miss"]
    trows = []
    for (st, m) in sorted({(r["set"], r["method"]) for r in rr}, key=lambda x: (x[0] != "primary", x[1])):
        vals = [cnt[(st, m, k)] for k in ("certified", "undetermined", "refuted", "not_certified_search_tier_miss")]
        trows.append([st, m] + vals)
        for k, v in zip(("certified", "undetermined", "refuted", "search_tier_miss"), vals):
            L.add("FAIL", f"v3.{st}.{m}.{k}", v, src, f"count cert_verdict ({st})", status="derived", script=S)
    out += _tab(hdr, trows) + [""]

    # 3.1 search-tier misses
    miss = [r for r in rr if r["cert_verdict"] == "not_certified_search_tier_miss"]
    assert all(r["certify_attempted"] == "False" for r in miss)
    by_t = collections.defaultdict(list)
    for r in miss:
        by_t[(r["set"], r["target_id"], r["target_type"], r["difficulty"])].append(
            f"{r['method']} ({float(r['slack_nominal']):+.2f})")
    out += ["### 3.1 Search-tier misses (no certificate attempted)", "",
            f"{len(miss)} rows. Cause as recorded: the method's final design after the method's allocated search "
            f"procedure (searching methods: {'/'.join(sorted({r['evals_spent'] for r in rr if r['method'] != 'M1'}))} "
            "search-tier evaluations; atlas-only M1: "
            f"{'/'.join(sorted({r['evals_spent'] for r in rr if r['method'] == 'M1'}))} evaluations, it selects an "
            "atlas row) has negative nominal slack against at least one target, so `certify_attempted` is False. The "
            "value in brackets is `slack_nominal` of the final design.", ""]
    L.add("FAIL", "v3.evals_spent_searching", "/".join(sorted({r["evals_spent"] for r in rr if r["method"] != "M1"})),
          src, "distinct evals_spent of methods M2-M6", status="derived", script=S)
    L.add("FAIL", "v3.evals_spent_atlas_only", "/".join(sorted({r["evals_spent"] for r in rr if r["method"] == "M1"})),
          src, "distinct evals_spent of method M1", status="derived", script=S)
    out += _tab(["set", "target", "type", "difficulty", "methods that missed (slack_nominal)"],
                [[k[0], k[1], k[2], k[3], ", ".join(v)] for k, v in sorted(by_t.items(), key=lambda x: -len(x[1]))])
    L.add("FAIL", "v3.search_tier_miss_rows", len(miss), src, "cert_verdict == not_certified_search_tier_miss",
          status="derived", script=S)
    allm = [k[1] for k, v in by_t.items() if len(v) >= 5]
    L.add("FAIL", "v3.targets_missed_by_5plus_methods", ", ".join(allm), src, "targets missed by >= 5 of 6 methods",
          status="derived", script=S)

    # 3.2 certificate failures
    bad = [r for r in rr if r["cert_verdict"] in ("undetermined", "refuted")]
    out += ["", "### 3.2 Certificates that did not certify", "",
            f"{len(bad)} rows (several methods can share one certificate, `cert_shared_with`). Cause copied from "
            "the certificate: `blocks.static.checks_failed` and `blocks.bloch.verdict.reason`; the safe interval "
            "'none' means that edge could not be bounded (edge sequence neither convergent nor within phase noise).",
            ""]
    rows, why = [], collections.Counter()
    hashes = set()
    for r in bad:
        d = _cert(r)
        assert d is not None, r
        hashes.add(r["final_hash"])
        c, det = _cause(d)
        why[c] += 1
        rows.append([r["set"][:3], r["target_id"], r["target_type"], r["method"], r["cert_verdict"],
                     f"{r['final_kind']} {_p(r['final_params'])}", c, det])
    out += _tab(["set", "target", "type", "method", "verdict", "final design", "cause", "detail"], rows)
    out += ["", "Counts by cause:", ""] + [f"- {k}: {v}" for k, v in why.most_common()] + [""]
    for k, v in why.items():
        L.add("FAIL", f"v3.cause.{k}", v, "results/verification/v14/bench/certs/<target>_<hash>.json",
              "rows by certificate cause", status="derived", script=S)
    L.add("FAIL", "v3.failed_cert_rows", len(bad), src, "cert_verdict in (undetermined, refuted)", status="derived",
          script=S)
    L.add("FAIL", "v3.failed_cert_unique", len(hashes), src, "unique final_hash among them", status="derived",
          script=S)
    sl = [r for r in bad if r["final_kind"] == "sphere_ligaments"]
    L.add("FAIL", "v3.failed_cert_sphere_ligaments", f"{len(sl)}/{len(bad)}", src, "final_kind sphere_ligaments",
          status="derived", script=S)
    ref = [r for r in bad if r["cert_verdict"] == "refuted"]
    for r in ref:
        d = _cert(r)
        q = d["blocks"]["static"]["convergence"]["quantities"]
        tgt = d["targets"]
        lines = []
        for k, t in tgt.items():
            qn = k.rsplit("_", 1)[0]
            if qn in q and k.endswith("_min"):
                lines.append(f"{qn} guarded [{q[qn]['lower']:.5f}, {q[qn]['upper']:.5f}] vs target ≥ {t:.5f}")
        out.append(f"Refuted row {r['target_id']} {r['method']}: " + "; ".join(lines) + " – the whole guarded "
                   "interval lies below the target, although the search tier had the design meeting it "
                   f"(slack_nominal {float(r['slack_nominal']):+.3f}).")
        L.add("FAIL", f"v3.refuted.{r['target_id']}.{r['method']}", "; ".join(lines),
              f"results/verification/v14/bench/certs/{r['target_id']}_{r['final_hash']}.json",
              "blocks.static.convergence.quantities lower/upper vs targets", status="derived", script=S)
    out.append("")

    # 3.3 BO certified, atlas-only not (and the reverse)
    prim = [r for r in rr if r["set"] == "primary"]
    res = {(r["target_id"], r["method"]): r for r in prim}
    targets = sorted({r["target_id"] for r in prim})
    bo_only = [t for t in targets if res[(t, "M4")]["certified"] == "True" and res[(t, "M1")]["certified"] != "True"]
    at_only = [t for t in targets if res[(t, "M1")]["certified"] == "True" and res[(t, "M4")]["certified"] != "True"]
    L.add("FAIL", "v3.discordant_M4_only", ", ".join(bo_only) or "none", src, "M4 certified and M1 not (primary)",
          status="derived", script=S)
    L.add("FAIL", "v3.discordant_M1_only", ", ".join(at_only) or "none", src, "M1 certified and M4 not (primary)",
          status="derived", script=S)
    out += ["### 3.3 Targets certified by BO (M4) but not by atlas-only (M1)", "",
            f"Discordant pairs: M4 only {len(bo_only)} ({', '.join(bo_only)}), M1 only {len(at_only)}"
            f"{' (' + ', '.join(at_only) + ')' if at_only else ''}. This is the 14 vs 12 of the primary test "
            "(exact McNemar p 0.5, v3/NOTES.md).", ""]
    rows = []
    for t in bo_only:
        for m in ("M1", "M4"):
            r = res[(t, m)]
            d = _cert(r)
            c, det = _cause(d) if d else ("–", "")
            rows.append([t, r["target_type"], m, f"{r['final_kind']} {_p(r['final_params'])}", r["from_atlas"],
                         r["evals_to_final"], f"{float(r['slack_nominal']):+.3f}", r["cert_verdict"],
                         c if r["cert_verdict"] != "certified" else "–", det if r["cert_verdict"] != "certified"
                         else ""])
    out += _tab(["target", "type", "method", "final design", "from atlas", "evals to final", "slack_nominal",
                 "verdict", "cause", "detail"], rows)
    same_kind = all(res[(t, "M1")]["final_kind"] == res[(t, "M4")]["final_kind"] for t in bo_only)
    m4_off = all(res[(t, "M4")]["from_atlas"] == "False" for t in bo_only)
    m1_reason = {_cause(_cert(res[(t, "M1")]))[0] for t in bo_only}
    static_ok = all((res[(t, m)]["static_verdict"] in ("certified", "")) for t in bo_only for m in ("M1", "M4"))
    slack_up = [t for t in bo_only if float(res[(t, "M4")]["slack_nominal"]) > float(res[(t, "M1")]["slack_nominal"])]
    slack_dn = [t for t in bo_only if t not in slack_up]
    if same_kind and m4_off and len(m1_reason) == 1 and static_ok:
        out += ["", f"Reading (descriptive): in {', '.join(bo_only)} M1 returns an atlas cell and M4 a nearby "
                f"off-grid design of the same family ({res[(bo_only[0], 'M1')]['final_kind']}). The static targets "
                f"are certified for both; M1's gap certificate is undetermined ({next(iter(m1_reason))}). The "
                f"search-tier slack does not predict which one certifies: M4's nominal slack is larger in "
                f"{', '.join(slack_up) or 'none'} and smaller in {', '.join(slack_dn) or 'none'}. On these two "
                "targets the gain comes from local refinement around an atlas seed (M4 is atlas-seeded), not from a "
                "different family; two targets cannot separate this from chance (p 0.5).", ""]
    L.add("FAIL", "v3.discordant_slack_M4_larger", ", ".join(slack_up) or "none", src,
          "slack_nominal M4 > M1 among M4-only targets", status="derived", script=S)

    # 3.4 calibration targets
    cal = [r for r in rr if r["set"] == "calibration" and r["certified"] != "True"]
    out += ["### 3.4 Calibration targets (ν 0.342 / 0.39; M4 and M6 only)", ""]
    out += _tab(["target", "type", "method", "verdict", "cause"],
                [[r["target_id"], r["target_type"], r["method"], r["cert_verdict"],
                  (_cause(_cert(r))[0] if _cert(r) else "search tier miss")] for r in cal])
    L.add("FAIL", "v3.calibration_not_certified", len(cal), src, "calibration rows not certified", status="derived",
          script=S)
    return out + [""]


# ------------------------------------------------------------------------------------------------------------ E4
def _e4(L: Ledger) -> list[str]:
    src = "results/bench/e4/scores.json"
    sc = [x for x in read_json(src) if x["partition"] == "confirmatory"]
    out = ["## 4. E4 agent evaluation (Codex, A2 scoring, confirmatory partition)", "",
           "E4 is scoped to the frozen system (plan wording rule). Outcome per job from `scores.json` (`outcome`), "
           "the agent's own decision and verdict code (`decision`, `verdict`), the number of certify calls, and the "
           "agent's note as recorded (truncated). Cause of a false refusal or abstention in arm C is also read from "
           "the session certificates (`jobs/<job>/session/certificates/*.json`).", ""]
    oc = collections.Counter((x["arm"], x["outcome"]) for x in sc)
    arms = ["D", "B", "C"]
    outs = ["success", "correct_refusal", "abstention", "false_refusal", "overclaim", "no_answer"]
    out += _tab(["arm"] + outs, [[a] + [oc.get((a, o), 0) for o in outs] for a in arms]) + [""]
    for a in arms:
        for o in outs:
            L.add("FAIL", f"e4.{a}.{o}", oc.get((a, o), 0), src, "count outcome (confirmatory)", status="derived",
                  script=S)

    # arm C: per job with session certificates
    out += ["### 4.1 Arm C (bounds + certify): every non-success job", ""]
    rows, certcls = [], collections.Counter()
    for x in sorted([x for x in sc if x["arm"] == "C" and x["outcome"] != "success"],
                    key=lambda x: (outs.index(x["outcome"]), x["job"])):
        cdir = ROOT / f"results/bench/e4/jobs/{x['job']}/session/certificates"
        cs = []
        for f in sorted(cdir.glob("*.json")) if cdir.exists() else []:
            d = json.loads(f.read_text(encoding="utf-8"))
            c, _ = _cause(d) if d.get("verdict") != "certified" else ("certified", "")
            cs.append(c)
            certcls[c] += 1
        cc = collections.Counter(cs)
        rows.append([x["job"].replace("codex-C-r1-", ""), x["cls"], x["outcome"], x["verdict"], x["n_certify"],
                     "; ".join(f"{k} ×{v}" for k, v in cc.items()) or "–", _short(x["note"], 140)])
    out += _tab(["brief", "class", "outcome", "verdict code", "certify calls", "session certificates (cause)",
                 "agent note (truncated)"], rows)
    fr = [r for r in rows if r[2] == "false_refusal"]
    L.add("FAIL", "e4.C.false_refusal_briefs", ", ".join(r[0] for r in fr), src, "arm C false_refusal jobs",
          status="derived", script=S)
    for k, v in certcls.items():
        L.add("FAIL", f"e4.C.nonsuccess_session_certs.{k}", v, "results/bench/e4/jobs/codex-C-r1-*/session/"
              "certificates", "certificate cause in arm C non-success jobs", status="derived", script=S)
    # the reading below is asserted from the data, not assumed
    frx = [x for x in sc if x["arm"] == "C" and x["outcome"] == "false_refusal"]
    fam = collections.Counter()
    all_failed = True
    for x in frx:
        for f in sorted((ROOT / f"results/bench/e4/jobs/{x['job']}/session/certificates").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            all_failed &= d.get("verdict") != "certified"
            fam[d["spec"]["kind"]] += 1
    witnessed = all(x["truth_level"] == "witnessed" for x in frx)
    used_cert = all(int(x["n_certify"]) >= 1 for x in frx)
    undet = all(x["verdict"] == "UNDETERMINED" for x in frx)
    ab = [x for x in sc if x["arm"] == "C" and x["outcome"] == "abstention"]
    cr = [x for x in sc if x["arm"] == "C" and x["outcome"] == "correct_refusal"]
    L.add("FAIL", "e4.C.false_refusal_cert_kinds", dict(fam), "results/bench/e4/jobs/<job>/session/certificates",
          "spec.kind of session certificates in arm C false-refusal jobs", status="derived", script=S)
    if witnessed and used_cert and undet and all_failed:
        out += ["", f"Reading (descriptive, checked in the script): all {len(frx)} arm C false refusals are witnessed "
                "feasible briefs where the agent used at least one certify call, every session certificate came back "
                "undetermined or refuted, and the agent then answered UNDETERMINED instead of releasing; the scorer "
                "counts that as a false refusal. Cell kinds submitted to certify in these jobs: "
                + ", ".join(f"{k} {v}" for k, v in fam.most_common()) + ". "
                f"The {len(ab)} abstentions answer NOT_FOUND_IN_FAMILIES "
                f"({sum(x['verdict'] == 'NOT_FOUND_IN_FAMILIES' for x in ab)}/{len(ab)}) on briefs whose truth is "
                f"unresolved ({sum(x['truth_level'] == 'unresolved' for x in ab)}/{len(ab)}); the {len(cr)} correct "
                f"refusals answer PROVEN_INFEASIBLE ({sum(x['verdict'] == 'PROVEN_INFEASIBLE' for x in cr)}/"
                f"{len(cr)}) with {sum(int(x['n_certify']) for x in cr)} certify calls in total.", ""]
    else:
        out += ["", "Reading: the arm C false refusals do not share one pattern; see the table.", ""]

    # all arm C session certificates that did not certify (including in jobs that ended in success)
    allc = collections.Counter()
    for f in sorted((ROOT / "results/bench/e4/jobs").glob("codex-C-r1-*/session/certificates/*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        allc[d.get("verdict")] += 1
    L.add("FAIL", "e4.C.session_certs_by_verdict", dict(allc), "results/bench/e4/jobs/codex-C-r1-*/session/"
          "certificates/*.json", "verdict over all arm C session certificates", status="derived", script=S)
    out += [f"All arm C session certificates (any job): " + ", ".join(f"{k} {v}" for k, v in allc.items()) + ".", ""]

    # arms B and D
    for a, name in (("B", "B (+ search tools, no bounds or certify)"), ("D", "D (LLM alone)")):
        xs = sorted([x for x in sc if x["arm"] == a and x["outcome"] != "success"],
                    key=lambda x: (outs.index(x["outcome"]), x["job"]))
        vc = collections.Counter((x["outcome"], x["verdict"]) for x in xs)
        out += [f"### 4.{2 if a == 'B' else 3} Arm {name}: {len(xs)} non-success jobs", "",
                "By outcome and verdict code:", ""]
        out += _tab(["outcome", "verdict code", "jobs"], [[o, v, k] for (o, v), k in sorted(vc.items())]) + [""]
        for (o, v), k in vc.items():
            L.add("FAIL", f"e4.{a}.{o}.{v}", k, src, "count (outcome, verdict)", status="derived", script=S)
        out += _tab(["brief", "class", "truth", "outcome", "verdict code", "agent note (truncated)"],
                    [[x["job"].split("-r1-")[1], x["cls"], x["truth_level"], x["outcome"], x["verdict"],
                      _short(x["note"], 110)] for x in xs]) + [""]
    return out


def _v2(L: Ledger) -> list[str]:
    src = "results/verification/v2/matrix.csv"
    mat = read_csv(src)
    fails = [r for r in mat if r["result"] == "fail"]
    out = ["## 5. V2 capability and interface matrix: failed rows", "",
           f"`{src}` keeps every failed row with its cause ({len(fails)} of {len(mat)} rows). No failure is an amm bug; "
           "the three amm bugs V2 found were found by the probe and fixed before run 1 "
           "(results/verification/v2/NOTES.md sections 3 and 4).", ""]
    by = collections.OrderedDict()
    for r in fails:
        by.setdefault(r["cause"], []).append(r)
    rows = []
    for cause, rs in by.items():
        checks = sorted({f"{r['scenario']}/{r['check']}" for r in rs})
        ifs = sorted({r["interface"] for r in rs})
        rows.append([", ".join(checks), ", ".join(ifs), len(rs), _short(cause, 260)])
    out += _tab(["check", "interfaces", "rows", "cause (from matrix.csv)"], rows) + [""]
    L.add("FAIL", "v2.fail_rows", len(fails), src, "result == fail", status="derived", script=S)
    L.add("FAIL", "v2.fail_causes", len(by), src, "distinct cause texts among failed rows", status="derived", script=S)
    return out


def _v6(L: Ledger) -> list[str]:
    v6 = "results/verification/v6"
    out = ["## 6. V6 engineering cases: not-certified calls, flags and screening", ""]
    rows = []
    for sess in ("case1/session_design", "case1/session_reference", "case2/session_PA12", "case2/session_316L"):
        for f in sorted((ROOT / v6 / sess / "certificates").glob("*.json")):
            c = json.loads(f.read_text(encoding="utf-8"))
            st = c["blocks"]["static"]
            ab = c["blocks"].get("as_built", {}).get("cases", {})
            abf = [k for k, v in ab.items() if not v["passed"]]
            why = "; ".join(st.get("checks_failed") or []) or "-"
            rows.append([sess.split("/")[1], c["spec"]["kind"] + " " + _p(c["spec"]["params"]), c["verdict"],
                         str(st.get("used")), _short(why, 120), ", ".join(abf) or "none"])
            rp = f.relative_to(ROOT).as_posix()
            L.add("FAIL", f"v6.{sess.split('/')[1]}.{c['spec_hash']}.verdict", c["verdict"], rp, "verdict",
                  script=S)
    out += ["Every certificate written in the four acceptance sessions (`" + v6 + "/case*/session_*/certificates/`):",
            ""]
    out += _tab(["session", "design", "verdict", "static rung used", "static checks failed", "as-built fails"],
                rows) + [""]
    und = [r for r in rows if r[2] != "certified"]
    L.add("FAIL", "v6.not_certified", len(und), f"{v6}/case*/session_*/certificates/*.json", "verdict != certified",
          status="derived", script=S)
    sc = read_json(f"{v6}/case2/session_PA12/summary.json")["calls"]["screen_manufacturing"]["result"]["min_feature"]
    L.add("FAIL", "v6.PA12_filter.min_solid_mm", f"{sc['solid_est_mm']:.3f}", f"{v6}/case2/session_PA12/summary.json",
          "calls.screen_manufacturing.result.min_feature.solid_est_mm", unit="mm", script=S)
    out += [f"- The one not-certified call is the first mount reference candidate: the static guard climbed to the "
            "finest rung and its guarded lower E100 stayed below the target, so the verdict is undetermined (an "
            "abstention, not a refutation). The next candidate by the fixed rule was certified (V6 NOTES 1.5, 8.1).",
            "- As-built flags: the mount design and the mount reference fail erosion by 0.01 a on E100; the 316L filter "
            "fails dilation on the gap counts. Flags are reported; they do not block release.",
            f"- Screening: the PA12 filter design fails the 0.8 mm SLS feature limit (min solid "
            f"{sc['solid_est_mm']:.2f} mm, {100 * sc['solid_thinner_than_limit']:.1f} % of the solid thinner than the "
            "limit). Screening is not part of the certificate; the case reports it and does not tune the design.",
            "- Timing deviations (contention with V2) and the case-1 rerun under one code identity are in V6 NOTES "
            "section 7 (deviations 4 and 5).", ""]
    L.add("FAIL", "v6.PA12_filter.solid_thinner_than_limit", f"{100 * sc['solid_thinner_than_limit']:.1f}",
          f"{v6}/case2/session_PA12/summary.json", "min_feature.solid_thinner_than_limit x 100", status="derived",
          unit="%", script=S)
    return out


def build(L: Ledger) -> list[Path]:
    md = ["# Failure analysis: undetermined, refuted, marginal and refused cases", "",
          "Generated by `scripts/paper/failures.py` (run `scripts/paper/make_all.py`) from result files only. "
          "Counts are registered in `results/claims_ledger.csv` (asset FAIL). Wording follows the plan rules: "
          "V1c literal gate weak / qualified adequate; E4 scoped to the frozen system; S4 limited to the V6 "
          "acceptance tests.", ""]
    md += _v1b(L) + _v1c(L) + _v3(L) + _e4(L) + _v2(L) + _v6(L)
    p = PAPER / "ANALYSIS_failures.md"
    p.write_text("\n".join(md) + "\n", encoding="utf-8")
    return [p]
