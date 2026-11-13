// Outcome and evidence (plan B1, schema amm-outcome/1). Five outcomes plus "information needed"; per outcome the
// evidence records the session holds (from the tool results: bounds, atlas, search, certificates) and whether each
// still holds for the CURRENT spec; the outcome card of the submission with the evidence it cites; and the submit
// control. In profile C a refusal must cite a held record of the matching kind: amm rejects it otherwise, and the
// rejection (with what is missing and what is held) is shown here.
import { useState } from "react";
import { useStore } from "../store";
import type { B1Group, EvidenceRecord, OutcomeCard } from "../types";

const VERDICTS = ["PROVEN_INFEASIBLE", "NOT_FOUND_IN_FAMILIES", "UNDETERMINED", "OTHER"] as const;

function Detail({ rec }: { rec: EvidenceRecord }) {
  return (
    <table>
      <tbody>
        {rec.items.map((it, i) => (
          <tr key={i} className={it.verdict ? `v-${it.verdict}` : ""}><td>{it.label}</td><td>{it.value}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function OutcomeTile({ g, legacy, submitted, needInfo }: { g: B1Group; legacy?: OutcomeCard; submitted: boolean;
  needInfo: string[] }) {
  const status = submitted ? "submitted" : g.n_holding ? "evidence" : g.n_records ? "stale" : "none";
  const text = { submitted: "submitted", evidence: `${g.n_holding} held for this spec`, stale: "only for an earlier spec",
    none: "no evidence" }[status];
  const last = legacy?.records?.[legacy.records.length - 1];
  return (
    <article className={`card st-${status} oc-${g.legacy ?? g.id}`}>
      <header><b>{g.title}</b><span className={`status s-${status}`}>{text}</span></header>
      <p className="def">{g.definition}</p>
      {g.records.slice(-2).map((r) => (
        <div key={`${r.seq}${r.kind}`} className={`b1rec ${r.holds ? "holds" : "stale"}`}>
          <span className="ref">#{r.seq} {r.tool}: {r.kind}</span>
          <span className={`chip ${r.holds ? "h-yes" : "h-no"}`}>{r.holds ? "holds" : "stale"}</span>
          <div className="sum">{r.summary}</div>
        </div>
      ))}
      {last && g.records.some((r) => r.seq === last.ref.seq) && <div className="rec"><Detail rec={last} /></div>}
      {g.id === "need_info" && needInfo.length > 0 && <div className="sum">{needInfo.join("; ")}</div>}
    </article>
  );
}

function SubmitBox() {
  const s = useStore((x) => x.summary);
  const design = useStore((x) => x.design);
  const call = useStore((x) => x.call);
  const [decision, setDecision] = useState<"release" | "refuse" | "need_info">("refuse");
  const [verdict, setVerdict] = useState<(typeof VERDICTS)[number]>("PROVEN_INFEASIBLE");
  const [note, setNote] = useState("");
  if (!s) return null;
  const o = s.outcome;
  if (s.submission) return null;
  const cite = o?.can_cite?.[verdict] ?? [];
  const submit = () => {
    const args: Record<string, unknown> = { decision, note };
    if (decision === "release") args.design = design;
    if (decision === "refuse") args.verdict = verdict;
    void call("submit", args);
  };
  return (
    <div className="submitbox">
      <div className="row">
        <b>Submit</b>
        <select value={decision} onChange={(e) => setDecision(e.target.value as typeof decision)} aria-label="decision">
          <option value="release">release the current design</option>
          <option value="refuse">refuse the request</option>
          <option value="need_info">stop: information needed</option>
        </select>
        {decision === "refuse" && (
          <select value={verdict} onChange={(e) => setVerdict(e.target.value as typeof verdict)} aria-label="verdict">
            {VERDICTS.map((v) => <option key={v} value={v}>{v}{(o?.can_cite?.[v] ?? []).length ? ` (evidence: #${o.can_cite[v].join(", #")})` : " (no evidence held)"}</option>)}
          </select>
        )}
        <input placeholder="note" value={note} onChange={(e) => setNote(e.target.value)} size={14} />
        <button className="primary" onClick={submit}>Submit</button>
      </div>
      {decision === "refuse" && o?.evidence_checked && (
        <div className="muted small">Refusal rule (profile {o.profile}): {verdict} must cite {o.hints[verdict]}.
          {cite.length ? ` Held now: #${cite.join(", #")}.` : " Nothing held now: amm will reject this refusal."}</div>
      )}
      {decision === "release" && s.profile === "C" && (
        <div className="muted small">Release needs a certificate with verdict certified for this design and the current targets.</div>
      )}
    </div>
  );
}

export function EvidencePanel() {
  const s = useStore((x) => x.summary);
  if (!s) return null;
  const ev = s.evidence;
  const o = s.outcome;
  const card = o?.card;
  const legacyById: Record<string, OutcomeCard> = {};
  for (const c of ev?.cards ?? []) legacyById[c.id] = c;
  const subOutcome = card?.outcome ?? (ev?.submitted_outcome ? Object.values(o?.groups ?? []).find((g) => g.legacy === ev.submitted_outcome)?.id : null);
  const rej = o?.last_rejected_submit;
  return (
    <section className="panel evidence">
      <div className="panel-head">
        <h2>Outcome and evidence</h2>
        <span className="muted small">{o?.schema}; profile {o?.profile}{o?.evidence_checked ? ", refusals must cite evidence" : ", evidence not checked (ablation profile)"}</span>
      </div>
      {card && (
        <div className={`outcomecard oc-${card.outcome}`}>
          <div className="row"><span className="big">{card.title}</span>
            <span className={`decision d-${card.decision}`}>{card.decision}{card.verdict ? ` (${card.verdict})` : ""}</span>
            <span className="muted small">submit #{o.submit_seq}; evidence checked: {String(card.evidence_checked)}</span></div>
          <div className="def small">{card.definition}</div>
          {card.design && <div className="small">design: {card.design.kind} {Object.entries(card.design.params).map(([k, v]) => `${k}=${v}`).join(", ")}</div>}
          {card.evidence.length > 0 && (
            <ul className="cited">
              {card.evidence.map((e) => <li key={`${e.seq}${e.kind}`}><b>cites #{e.seq}</b> {e.tool}: {e.kind} - {e.summary}</li>)}
            </ul>
          )}
        </div>
      )}
      {!card && ev?.submission && (
        <div className="warn">submitted: {ev.submission.decision}{ev.submission.verdict ? ` (${ev.submission.verdict})` : ""} (a
          schema-1 log: no outcome card; the tiles below are a view of its records)</div>
      )}
      {rej && (
        <div className="reject">
          <b>Submit #{rej.seq} rejected{rej.refusal_rule ? " by the refusal-evidence rule" : ""}:</b> {rej.error}
        </div>
      )}
      <SubmitBox />
      <div className="cards">
        {(o?.groups ?? []).map((g) => (
          <OutcomeTile key={g.id} g={g} legacy={g.legacy ? legacyById[g.legacy] : undefined}
            submitted={subOutcome === g.id || (g.id === "need_info" && !!ev?.need_info)} needInfo={s.cannot_normalize} />
        ))}
      </div>
      {ev?.submission?.note && <div className="note small"><b>submission note:</b> {ev.submission.note}</div>}
    </section>
  );
}
