"""Benchmark briefs, the deterministic clarification oracle, and one agent session per brief.

Brief JSON: {id, class, text, intended: {material, cell_size, targets (amm.units request form)},
             oracle: {facts}, expected: {decision, verdict?}, truth_source}
`text` is all the agent sees. The oracle answers ask_clarification from `intended`: it picks the first option whose
`set` matches the intended spec, and otherwise states `oracle.facts` verbatim, as a user would (counted as a miss).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import units

ARMS = ("D", "B", "C", "O")

SCOPE = """Scope (the same for every request): designs are periodic unit cells with cubic symmetry from three
families (TPMS sheets and networks, strut lattices, mass-in-frame resonators), made of one isotropic linear-elastic
solid. Stiffness and Poisson-ratio targets refer to the homogenized (infinite-lattice) cubic elastic tensor. The
band gaps the tools compute and certify are complete gaps of the infinite periodic lattice (all wave directions
and polarizations); a request for a gap does not always say which kind of gap the user needs. The material is
named for its elastic constants and density only; manufacturability (printable feature size, supports, powder
removal) is not evaluated."""

# what an answer must settle for each kind of ambiguous brief (scoring and oracle; re-audit #2)
MISSING_KEYS = {"material": ("material",), "cell_size": ("cell_size",),
                "quantity": ("E100_min", "G_min", "bulk_min"),
                "unit": ("E100_min", "E100_max", "G_min", "bulk_min", "gap", "cell_size"),
                "gap_type": ("gap_type",)}

PROMPT = """You are a design assistant for periodic metamaterial unit cells. Handle the request below with the
amm tools.
{scope}
- If information you need is missing from the request, ask the user with ask_clarification instead of guessing.
- Finish by calling the submit tool exactly once: release one design, refuse the request (with a verdict), or
  need_info.
- After submit, reply with one short paragraph that states the outcome and the design or the reason.

Request:
{text}
"""


def _mat_key(m) -> str:
    return re.sub(r"[^a-z0-9]", "", str(m).lower())


def _cell_m(v):
    if isinstance(v, (int, float)):
        return float(v) * 1e-3
    return float(v[0]) * units.LENGTH_UNITS[v[1]]


NEUTRAL = "I have nothing to add: everything I need is in the request and my answers so far. Use your judgement."


def settles(option_set: dict, missing: str | None) -> bool:
    """Does choosing this option settle the brief's missing item? (Any matching option on a clear brief.)"""
    return missing is None or any(k in MISSING_KEYS.get(missing, ()) for k in option_set)


class Oracle:
    def __init__(self, brief: dict):
        self.intended = brief["intended"]
        self.facts = (brief.get("oracle") or {}).get("facts", "")
        self.missing = (brief.get("oracle") or {}).get("missing")  # ambiguous briefs: the item left out
        self.asked = 0
        self.resolved = False  # the missing item is settled (a matching option that sets it was chosen)

    def _norm(self, key, value):
        req = {k: v for k, v in self.intended.items() if k in ("material", "cell_size")}
        if key == "gap" and isinstance(value, dict) and "unit" in value:
            u = value["unit"]
            value = ({"f_lo": value["f_lo"], "f_hi": value["f_hi"]} if u == "f*" else
                     {"f_lo": [value["f_lo"], u], "f_hi": [value["f_hi"], u]})
        if isinstance(value, dict) and "value" in value and "unit" in value:
            value = value["value"] if value["unit"] == "E_s" else [value["value"], value["unit"]]
        req[key] = value
        t, _, _ = units.normalize(req)
        return t.get(key)

    def matches(self, s: dict) -> bool:
        if not s:
            return False
        it = self.intended
        for k, v in s.items():
            try:
                if k == "material":
                    if _mat_key(v) != _mat_key(it.get("material")):
                        return False
                elif k == "cell_size":
                    if it.get("cell_size") is None or abs(_cell_m(v) / _cell_m(it["cell_size"]) - 1) > 1e-6:
                        return False
                elif k == "gap_type":
                    if v != it.get("gap_type", "complete"):
                        return False
                elif k in it.get("targets", {}):
                    a, b = self._norm(k, v), self._norm(k, it["targets"][k])
                    if a is None or b is None:
                        return False
                    if isinstance(a, dict):
                        if any(abs(a[e] / b[e] - 1) > 0.01 for e in ("f_lo", "f_hi")):
                            return False
                    elif abs(a / b - 1) > 0.01:
                        return False
                else:
                    return False
            except (TypeError, KeyError, ValueError, ZeroDivisionError):
                return False
        return True

    def __call__(self, question: str, options: list[dict]) -> dict:
        self.asked += 1
        for i, o in enumerate(options):
            if self.matches(o.get("set") or {}):
                if settles(o.get("set") or {}, self.missing):
                    self.resolved = True
                return dict(choice=i, label=o["label"], comment="")
        # state the missing fact until it is settled; after that a user has nothing to add (pilot A04: restating
        # the settled fact to an unrelated question left the agent without an answer)
        note = NEUTRAL if self.resolved or not self.facts else self.facts
        about_size = (any("cell_size" in (o.get("set") or {}) for o in options)
                      or re.search(r"cell|size|dimension|feature|scale", question, re.I))
        if self.intended.get("cell_size") is None and about_size:
            # a request without a frequency target has no fixed cell size (pilot A04: the oracle restated an
            # unrelated fact, and both arms stopped with need_info)
            note = "The cell size is not fixed: choose any cell size; printability is not evaluated."
        return dict(choice=None, label=None, comment=note)


def load_brief(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_run(out_dir: Path, rec: dict):
    (Path(out_dir) / "run.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")


def run_brief(brief_path: Path, out_dir: Path, profile: str = "C", provider: str = "codex", **kw) -> dict:
    """One session on one brief, logged to out_dir/session/session.jsonl. Arms: B / C = an LLM with the amm MCP
    tools of that profile; D = the LLM alone (no tools, answers in JSON; the harness logs its answer through the
    tool contract); O = no LLM (bounds, atlas, search and certify on the oracle spec). run.json is always written,
    with status done | timeout | error (audit F03)."""
    brief = load_brief(brief_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    rec = dict(brief=brief.get("id"), arm=profile, profile=profile, provider=provider if profile != "O" else "none",
               status="error", returncode=None, wall_s=None, usage={}, final="")
    try:
        if profile in ("B", "C"):
            rec.update(_run_tools_arm(brief, brief_path, out_dir, profile, provider, **kw))
        elif profile == "D":
            rec.update(_run_direct(brief, out_dir, provider, **kw))
        elif profile == "O":
            rec.update(_run_baseline(brief, out_dir))
        else:
            raise ValueError(f"unknown arm {profile}")
    except Exception as e:  # noqa: BLE001 -- recorded, never lost
        rec["error"] = f"{type(e).__name__}: {e}"
    finally:
        rec["wall_s"] = round(time.perf_counter() - t0, 1)
        _write_run(out_dir, rec)
    return rec


def _cli(provider: str, prompt: str, workdir: Path, mcp: dict | None, **kw):
    from . import llm
    if provider == "codex":
        extra = llm.codex_mcp_config(**mcp) if mcp else None
        return llm.run_codex(prompt, workdir, extra_config=extra, **kw)
    if provider == "claude":
        cfg = llm.claude_mcp_config(path=Path(workdir).parent / "mcp_config.json", **mcp) if mcp else None
        return llm.run_claude(prompt, workdir, mcp_config=cfg, **kw)
    raise ValueError(f"unknown provider {provider}")


def _cli_fields(r) -> dict:
    return dict(model=r.model, effort=r.effort, cli=r.cli_version, returncode=r.returncode, usage=r.usage,
                final=r.final, stderr_tail=r.stderr[-1500:], status="timeout" if r.timed_out else "done")


def _run_tools_arm(brief, brief_path, out_dir, profile, provider, **kw) -> dict:
    prompt = PROMPT.format(scope=SCOPE, text=brief["text"])
    (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    r = _cli(provider, prompt, out_dir / provider, dict(session_dir=out_dir / "session", profile=profile,
                                                       brief=brief_path), **kw)
    return _cli_fields(r)


# ---- arm D: the LLM alone ----------------------------------------------------------------------------------------
DIRECT_PROMPT = """You are a design assistant for periodic metamaterial unit cells. You have no tools and no
solver: answer from your own knowledge.
{scope}

Families (lengths in units of the cell size a; density = solid fraction):
- tpms: gyroid, schwarz_p, diamond, iwp; params {{density: 0.06-0.6, mode: "sheet" | "network"}} (network TPMS do
  not percolate below density ~0.10, Schwarz P ~0.15);
- struts: sc, bcc, octet; params {{r: 0.04-0.15 (strut radius), R: 0-0.32 (node-sphere radius; R = 0 or
  R >= r + 0.03)}};
- resonator: cube_bars {{c: 0.3-0.86, w: 0.06-0.36, w <= c - 0.04}}, sphere_ligaments {{c: 0.12-0.46, w: 0.06-0.34,
  w <= 2 c - 0.02}} (a mass in a frame, held by bars or ligaments).
Materials: PA12, Ti6Al4V, 316L, AlSi10Mg.

Reply with ONE JSON object and nothing else, in one of these forms:
1. a question when information you need is missing (at most {asks_left} more):
   {{"decision": "ask", "question": "...", "options": [{{"label": "...", "set": {{"material": "PA12"}}}}, ...]}}
   (2-5 options; "set" keys: material, cell_size ([value, unit]), gap_type, or a target key);
2. the final answer:
   {{"decision": "release" | "refuse" | "need_info",
     "material": "PA12" | "Ti6Al4V" | "316L" | "AlSi10Mg" | null,
     "cell_size": [value, "mm"] | null,
     "targets": {{"density_max": 0.25, "E100_min": {{"value": 10, "unit": "GPa"}},
                 "gap": {{"f_lo": 100, "f_hi": 150, "unit": "kHz"}}, ...}}  (the request's targets: density_max,
                 density_min, E100_min, G_min, bulk_min, nu100_min, nu100_max, gap),
     "design": {{"kind": "gyroid", "params": {{"density": 0.2, "mode": "sheet"}}}}  (release only),
     "verdict": "PROVEN_INFEASIBLE" | "NOT_FOUND_IN_FAMILIES" | "UNDETERMINED" | "OTHER"  (refuse only),
     "note": "one sentence"}}

Request:
{text}
{dialogue}"""


def _last_json(text: str):
    dec = json.JSONDecoder()
    found = None
    for i, ch in enumerate(text or ""):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                if isinstance(obj, dict) and "decision" in obj:
                    found = obj
            except json.JSONDecodeError:
                pass
    return found


def _run_direct(brief, out_dir, provider, max_asks: int = 2, **kw) -> dict:
    from . import tools
    s = tools.Session(out_dir / "session", profile="B", answerer=Oracle(brief))
    dialogue, usage, finals, rounds, status = "", {}, [], 0, "done"
    ans = None
    for rnd in range(max_asks + 1):
        prompt = DIRECT_PROMPT.format(scope=SCOPE, text=brief["text"], dialogue=dialogue, asks_left=max_asks - rnd)
        (out_dir / f"prompt_{rnd}.txt").write_text(prompt, encoding="utf-8")
        r = _cli(provider, prompt, out_dir / f"{provider}_{rnd}", None, **kw)
        rounds += 1
        for k, v in r.usage.items():
            usage[k] = usage.get(k, 0) + v
        finals.append(r.final)
        if r.timed_out:
            status = "timeout"
            break
        ans = _last_json(r.final)
        if not ans or ans.get("decision") != "ask":
            break
        if rnd == max_asks:  # no questions left: an unanswered question is no answer
            ans = None
            break
        opts = ans.get("options") if isinstance(ans.get("options"), list) else []
        out = s.call("ask_clarification", dict(question=str(ans.get("question", "")), options=opts), actor="harness")
        a = out["result"]["answer"] if out["ok"] else dict(choice=None, comment=f"(invalid question: {out['error']})")
        pick = opts[a["choice"]].get("label") if a.get("choice") is not None else None
        dialogue += (f"\nEarlier you asked: {ans.get('question')}\nThe user answered: "
                     + (f"option '{pick}'. " if pick else "") + (a.get("comment") or "") + "\n")
        ans = None
    if ans and ans.get("decision") in ("release", "refuse", "need_info"):
        _log_direct_answer(s, ans)
    return dict(status=status, returncode=0, usage=usage, final=finals[-1] if finals else "", rounds=rounds,
                parsed=ans is not None)


def _log_direct_answer(s, ans: dict):
    """Arm D's JSON answer through the tool contract, so that one scorer reads every arm."""
    if ans.get("material"):
        s.call("set_material", {"name": ans["material"]}, actor="harness")
    cs = ans.get("cell_size")
    if isinstance(cs, list) and len(cs) == 2:
        s.call("set_constraints", {"cell_size": cs[0], "cell_size_unit": cs[1]}, actor="harness")
    if isinstance(ans.get("targets"), dict) and ans["targets"]:
        s.call("set_target", ans["targets"], actor="harness")
    sub = {"decision": ans["decision"], "note": str(ans.get("note", ""))[:400]}
    if ans["decision"] == "release":
        sub["design"] = ans.get("design")
    if ans["decision"] == "refuse":
        sub["verdict"] = ans.get("verdict") or "OTHER"
    s.call("submit", sub, actor="harness")


# ---- arm O: no LLM ----------------------------------------------------------------------------------------------
def intended_tool_args(intended: dict) -> dict:
    """The intended spec as tool arguments (set_material, set_constraints, set_target)."""
    t = {}
    for k, v in intended["targets"].items():
        if k == "gap":
            lo, hi = v["f_lo"], v["f_hi"]
            t["gap"] = (dict(f_lo=lo[0], f_hi=hi[0], unit=lo[1]) if isinstance(lo, list) else
                        dict(f_lo=lo, f_hi=hi, unit="f*"))
        elif isinstance(v, list):
            t[k] = dict(value=v[0], unit=v[1])
        elif isinstance(v, (int, float)) and k in ("E100_min", "E100_max", "G_min", "bulk_min"):
            t[k] = dict(value=v, unit="E_s")
        else:
            t[k] = v
    if "gap" in t:
        t["gap_type"] = "complete"
    cs = intended.get("cell_size")
    return dict(material=intended["material"],
                constraints=dict(cell_size=cs[0], cell_size_unit=cs[1]) if cs else None, targets=t)


def _run_baseline(brief, out_dir, max_certify: int = 3, search_budget: int = 48) -> dict:
    """Deterministic reference: rigorous bounds, then atlas cells and a BoTorch search on the ORACLE spec, then
    certificates of up to `max_certify` candidates (atlas cells with pessimistic slack > 0, then search designs with
    expected slack > 0, then atlas cells with nominal slack > 0); release the first certified one, else refuse
    (NOT_FOUND_IN_FAMILIES when the atlas oracle says so, else UNDETERMINED)."""
    from . import tools
    s = tools.Session(out_dir / "session", profile="C")
    a = intended_tool_args(brief["intended"])

    def c(n, x=None):
        return s.call(n, x or {}, actor="baseline")
    c("set_material", {"name": a["material"]})
    if a["constraints"]:
        c("set_constraints", a["constraints"])
    st = c("set_target", a["targets"])
    if not st["ok"]:
        # a request the tool contract cannot even state (e.g. a gap reaching 0 Hz): check the rigorous bounds on
        # the intended request directly, then refuse (re-audit #12)
        from . import bounds
        req = dict(brief["intended"]["targets"], material=brief["intended"]["material"])
        if brief["intended"].get("cell_size"):
            req["cell_size"] = brief["intended"]["cell_size"]
        tn, _, _ = units.normalize(req)
        bv = bounds.check(tn, nu_s=units.MATERIALS[brief["intended"]["material"]]["nu"])
        proven = bv["verdict"] == bounds.PROVEN
        c("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE" if proven else "OTHER",
                     "note": f"spec rejected by the tools: {st['error'][:200]}"})
        return dict(status="done", returncode=0, n_candidates=0, spec_rejected=st["error"][:300])
    b = c("check_bounds")
    if b["ok"] and b["result"]["verdict"] == "PROVEN_INFEASIBLE":
        c("submit", {"decision": "refuse", "verdict": "PROVEN_INFEASIBLE", "note": "rigorous bound violated"})
        return dict(status="done", returncode=0, n_candidates=0)
    at = c("atlas_suggest", {"top": 5})
    se = c("search", {"budget": search_budget, "objective": "expected"})
    cands = []
    if at["ok"]:
        cands += [x["design"] for x in at["result"]["best"] if x["slack_pess"] > 0]
    if se["ok"]:
        cands += [x["design"] for x in se["result"]["best"] if x["slack_expected"] > 0]
    if at["ok"]:
        cands += [x["design"] for x in at["result"]["best"] if x["slack_nominal"] > 0]
    seen, order = set(), []
    for d in cands:
        k = json.dumps(d, sort_keys=True)
        if k not in seen:
            seen.add(k)
            order.append(d)
    for d in order[:max_certify]:
        r = c("certify", {"design": d})
        if r["ok"] and r["result"]["verdict"] == "certified":
            c("submit", {"decision": "release", "design": d, "note": "first certified candidate"})
            return dict(status="done", returncode=0, n_candidates=len(order))
    atlas_v = ((b.get("result") or {}).get("atlas") or {}).get("verdict") if b["ok"] else None
    c("submit", {"decision": "refuse", "verdict": "NOT_FOUND_IN_FAMILIES" if atlas_v == "NOT_FOUND_IN_FAMILIES"
                 else "UNDETERMINED", "note": f"{len(order)} candidates, none certified within {max_certify}"})
    return dict(status="done", returncode=0, n_candidates=len(order))
