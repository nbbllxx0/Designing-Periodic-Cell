// Family, kind and parameter sliders (boxes from amm.atlas.BOX via the backend), validity rule, and the solver
// actions (search-tier evaluate, certify) that go to the one GPU worker queue.
import { useState } from "react";
import { useStore } from "../store";
import { defaultDesign, familyOf, fmt, validity } from "../physics";
import type { Design, LogRecord } from "../types";

const dtext = (d: Design) => `${d.kind} ${Object.entries(d.params).map(([k, v]) => `${k}=${typeof v === "number" ? fmt(v, 3) : v}`).join(", ")}`;

/** Candidates of the last atlas_suggest or search call (search tier, not certificates): click to load. */
function Suggestions({ log }: { log: LogRecord[] }) {
  const setDesign = useStore((s) => s.setDesign);
  const design = useStore((s) => s.design);
  const r = [...log].reverse().find((x) => x.type === "call" && x.ok && (x.tool === "atlas_suggest" || x.tool === "search")
    && x.result && !x.result._truncated);
  if (!r) return null;
  const best: { design: Design; slack_nominal: number; slack_pess: number }[] = r.result.best ?? [];
  return (
    <div className="suggest">
      <div className="muted small">#{r.seq} {r.tool}{r.tool === "search" ? `: found ${r.result.found}, ${r.result.n_evaluations} evaluations` : ""};
        slack &gt; 0 means every target met (nominal / pessimistic, search tier)</div>
      <ol>
        {best.map((b, i) => (
          <li key={i} className={JSON.stringify(b.design) === JSON.stringify(design) ? "on" : ""}>
            <button onClick={() => setDesign(b.design)}>{dtext(b.design)}</button>
            <span className={`muted small ${b.slack_pess > 0 ? "okc" : ""}`}> {fmt(b.slack_nominal, 3)} / {fmt(b.slack_pess, 3)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function DesignPanel() {
  const fam = useStore((s) => s.families);
  const design = useStore((s) => s.design);
  const setDesign = useStore((s) => s.setDesign);
  const call = useStore((s) => s.call);
  const summary = useStore((s) => s.summary);
  const preview = useStore((s) => s.preview);
  const [budget, setBudget] = useState(16);
  if (!fam || !design) return <section className="panel">loading...</section>;
  const f = familyOf(fam, design.kind) ?? "tpms";
  const info = fam.families[f][design.kind];
  const bad = validity(fam, design);
  const allowed = summary?.state.families ?? [];
  return (
    <section className="panel design">
      <h2>Cell design</h2>
      <div className="tabs">
        {Object.keys(fam.families).map((x) => (
          <button key={x} className={x === f ? "on" : ""} onClick={() => setDesign(defaultDesign(fam, Object.keys(fam.families[x])[0]))}
            title={allowed.includes(x) ? "" : "not in the allowed families of the spec"}>
            {x}{allowed.includes(x) ? "" : " (excluded)"}
          </button>
        ))}
      </div>
      <div className="row">
        <label>Kind</label>
        <select value={design.kind} onChange={(e) => setDesign(defaultDesign(fam, e.target.value))}>
          {Object.keys(fam.families[f]).map((k) => <option key={k}>{k}</option>)}
        </select>
        {info.modes && (
          <span className="seg">
            {info.modes.map((m) => (
              <button key={m} className={design.params.mode === m ? "on" : ""}
                onClick={() => setDesign({ ...design, params: { ...design.params, mode: m } })}>{m}</button>
            ))}
          </span>
        )}
      </div>
      {Object.entries(info.params).map(([k, [lo, hi]]) => {
        const v = Number(design.params[k]);
        return (
          <div className="slider" key={k}>
            <label>{k}</label>
            <input type="range" min={lo} max={hi} step={(hi - lo) / 200} value={v}
              onChange={(e) => setDesign({ ...design, params: { ...design.params, [k]: Number(Number(e.target.value).toFixed(4)) } })} />
            <span className="val">{fmt(v, 4)}</span>
            <span className="muted">[{lo}, {hi}] a</span>
          </div>
        );
      })}
      <div className="muted small">{fam.rules[design.kind] ?? fam.rules[f]}; lengths in units of a</div>
      {bad && <div className="warn">{bad}</div>}
      {preview && <div className="muted small">preview solid fraction {fmt(preview.density_preview, 3)} (voxel centres, n = {preview.n})</div>}
      <div className="row buttons">
        <button onClick={() => void call("atlas_suggest", { top: 5 })} title="closest precomputed atlas cells (no solve)">
          Atlas suggest</button>
        <button onClick={() => void call("search", { budget })} title="Bayesian optimization over the allowed families (1-15 min, GPU)">
          Search</button>
        <select value={budget} onChange={(e) => setBudget(Number(e.target.value))} aria-label="search budget">
          {[8, 16, 32, 48].map((b) => <option key={b} value={b}>{b} evals</option>)}
        </select>
      </div>
      {summary && <Suggestions log={summary.log} />}
      <div className="row buttons">
        <button disabled={!!bad} onClick={() => void call("evaluate", { designs: [design] })}>Evaluate (search tier)</button>
        <button disabled={!!bad || summary?.profile !== "C"} className="primary" onClick={() => void call("certify", { design })}
          title="certificate against the current targets (1-20 min; static ladder, Bloch counts, as-built flag)">
          Certify
        </button>
      </div>
    </section>
  );
}
