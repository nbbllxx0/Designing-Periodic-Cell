import { useEffect, useState } from "react";
import { useStore } from "./store";
import { SpecPanel } from "./components/SpecPanel";
import { DesignPanel } from "./components/DesignPanel";
import { CellView } from "./components/CellView";
import { BandDiagram } from "./components/BandDiagram";
import { StiffnessPanel } from "./components/StiffnessPanel";
import { EvidencePanel } from "./components/EvidencePanel";
import { AgentPanel, AtlasMap, Timeline } from "./components/Secondary";
import { ExportPanel } from "./components/ExportPanel";
import { fmt } from "./physics";

function JobsIndicator() {
  const jobs = useStore((s) => s.jobs);
  const list = Object.values(jobs).sort((a, b) => a.t_queued - b.t_queued);
  const running = list.find((j) => j.status === "running");
  const queued = list.filter((j) => j.status === "queued").length;
  const last = list[list.length - 1];
  return (
    <span className={`jobs ${running ? "busy" : ""}`} title="one GPU worker: solver calls run one at a time">
      GPU worker: {running ? `running ${running.tool}` : "idle"}{queued ? `, ${queued} queued` : ""}
      {!running && last ? ` (last: ${last.tool} ${last.status})` : ""}
    </span>
  );
}

/** Running and queued solver jobs with their progress (SSE "progress" events) and a Cancel button. */
function JobsBar() {
  const jobs = useStore((s) => s.jobs);
  const cancelJob = useStore((s) => s.cancelJob);
  const mode = useStore((s) => s.mode);
  const [, tick] = useState(0);
  const list = Object.values(jobs).filter((j) => j.status === "running" || j.status === "queued")
    .sort((a, b) => a.t_queued - b.t_queued);
  useEffect(() => {
    if (!list.length) return;
    const t = window.setInterval(() => tick((x) => x + 1), 1000);
    return () => window.clearInterval(t);
  }, [list.length]);
  if (!list.length) return null;
  return (
    <div className="jobsbar">
      {list.map((j) => {
        const el = j.t_start ? Date.now() / 1000 - j.t_start : 0;
        const p = j.progress;
        const counts = p?.counts ? Object.entries(p.counts).map(([k, v]) => `${v} ${k}`).join(", ") : "";
        return (
          <div key={j.id} className={`job j-${j.status}`}>
            <b>{j.tool}</b>
            <span className="chip">{j.status}{j.cancel_requested ? ", cancelling" : ""}</span>
            {j.status === "running" && <span className="muted">{fmt(el, 3)} s</span>}
            <span className="stage">{p?.stage ?? (j.status === "queued" ? "waiting for the worker" : "")}</span>
            {counts && <span className="muted small">{counts}</span>}
            <span className="grow" />
            <button onClick={() => void cancelJob(j.id)} disabled={j.cancel_requested}
              title={mode === "live" ? "stops at the next solver checkpoint; the call is rolled back (not logged)" : ""}>
              Cancel
            </button>
          </div>
        );
      })}
    </div>
  );
}

function Header() {
  const s = useStore();
  const [pick, setPick] = useState("");
  const meta = s.summary?.meta;
  const groups: Record<string, typeof s.recorded> = {};
  for (const r of s.recorded) (groups[r.source] ??= []).push(r);
  return (
    <header className="top">
      <div className="brand">amm <span className="sub">metamaterial cell design</span></div>
      <span className={`mode m-${s.mode}`} title={s.mode === "mock" ? "recorded results only; no solver runs" : "live solver"}>
        {s.mode.toUpperCase()}
      </span>
      {s.mode !== "live" && <select value={pick} onChange={(e) => { setPick(e.target.value); if (e.target.value) void s.loadRecorded(e.target.value); }}
        aria-label="recorded session">
        <option value="">open recorded session...</option>
        {Object.entries(groups).map(([g, rs]) => (
          <optgroup key={g} label={g}>
            {rs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id} - {r.decision ?? "no submit"}{r.verdict ? ` ${r.verdict}` : ""}{r.same_code ? "" : " (older code)"}
              </option>
            ))}
          </optgroup>
        ))}
      </select>}
      <button onClick={() => { setPick(""); void s.newSession(); }}>New session</button>
      <span className="sess muted small">
        {meta?.kind === "recorded" ? `session ${meta.id}${meta.same_code ? "" : " (written by older amm code)"}`
          : s.mode === "live" ? `live session (amm ${meta?.code ?? ""}, ${s.summary?.schema_version ?? ""})` : "new session"}
        {s.summary ? `; seq ${s.summary.seq}; state ${s.summary.state_hash}` : ""}
      </span>
      <span className="grow" />
      <JobsIndicator />
      <span className={`conn ${s.connected ? "on" : ""}`} title="event stream">
        {s.connected ? "live events" : new URLSearchParams(window.location.search).get("static") === "1" ? "static view" : "offline"}
      </span>
      <button className="primary" onClick={() => void s.exportBundle()}
        title={s.mode === "live" ? "amm export tool: cell and tiled STL + report.json" : "mock: preview bundle"}>Export</button>
    </header>
  );
}

function Brief() {
  const meta = useStore((s) => s.summary?.meta);
  if (!meta?.brief) return null;
  return <div className="brief small"><b>Request:</b> {meta.brief}</div>;
}

export function App() {
  const init = useStore((s) => s.init);
  const message = useStore((s) => s.message);
  const [tab, setTab] = useState<"timeline" | "atlas" | "agent">(
    (new URLSearchParams(window.location.search).get("tab") as "timeline" | "atlas" | "agent") ?? "timeline");
  useEffect(() => {
    void init();
  }, [init]);
  return (
    <div className="app">
      <Header />
      <JobsBar />
      <Brief />
      <main className="grid">
        <div className="col left">
          <SpecPanel />
          <DesignPanel />
          <ExportPanel />
        </div>
        <div className="col mid">
          <CellView />
          <BandDiagram />
        </div>
        <div className="col right">
          <StiffnessPanel />
          <EvidencePanel />
        </div>
      </main>
      <footer className="bottom">
        <div className="tabs">
          {(["timeline", "atlas", "agent"] as const).map((t) => (
            <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t}</button>
          ))}
        </div>
        {tab === "timeline" && <Timeline />}
        {tab === "atlas" && <AtlasMap />}
        {tab === "agent" && <AgentPanel />}
      </footer>
      {message && <div className={`toast ${message.error ? "err" : ""}`}>{message.text}</div>}
    </div>
  );
}
