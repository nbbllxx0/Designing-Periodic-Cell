// Second-tier panels (plan B5): timeline, atlas map, agent panel. Stubs: the timeline lists the log with undo, the
// atlas map plots the search atlas (no click-to-load yet), the agent panel points to the MCP server (no LLM calls).
import { useEffect, useState } from "react";
import { get } from "../api";
import { useStore } from "../store";
import { fmt } from "../physics";

export function Timeline() {
  const summaryLog = useStore((s) => s.summary?.log);
  const log = summaryLog ?? [];
  const call = useStore((s) => s.call);
  const calls = log.filter((r) => r.type === "call");
  return (
    <div className="timeline">
      <div className="row"><b>Timeline</b><span className="muted small">{calls.length} calls (stub: no branch view yet)</span>
        <button onClick={() => void call("undo")}>Undo last spec change</button></div>
      <ol>
        {calls.slice(-40).map((r) => (
          <li key={r.seq} className={r.ok ? "ok" : "fail"} title={r.error ?? ""}>
            <span className="seq">#{r.seq}</span> <span className={`actor a-${r.actor}`}>{r.actor}</span> <b>{r.tool}</b>
            {r.mock_source && <span className="muted small"> [{r.mock_source.kind}{r.mock_source.session ? `: ${r.mock_source.session}` : ""}]</span>}
            {!r.ok && <span className="err small"> {r.error}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

interface Pt { kind: string; family: string; density: number; E100: number; best_rel_gap: number }

export function AtlasMap() {
  const nu = useStore((s) => s.summary?.physical.material?.nu);
  const [pts, setPts] = useState<Pt[]>([]);
  useEffect(() => {
    if (nu === undefined) return;
    get<{ points: Pt[]; available: boolean }>(`/api/atlas?nu=${nu}`).then((r) => setPts(r.available ? r.points : []))
      .catch(() => setPts([]));
  }, [nu]);
  const W = 360, H = 170, L = 34, B = 22;
  const emax = Math.max(0.01, ...pts.map((p) => p.E100));
  const dmax = Math.max(0.1, ...pts.map((p) => p.density)) * 1.02;
  const col: Record<string, string> = { tpms: "#4c78a8", struts: "#f58518", resonator: "#54a24b" };
  return (
    <div className="atlas">
      <div className="row"><b>Atlas map</b><span className="muted small">stub; search tier at nu_s = {nu ?? "-"}, {pts.length} cells;
        ring = complete gap &gt; 5 %</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart">
        <rect x={L} y={4} width={W - L - 6} height={H - B - 4} className="frame" />
        {pts.map((p, i) => (
          <circle key={i} cx={L + (p.density / dmax) * (W - L - 6)} cy={H - B - (p.E100 / emax) * (H - B - 8)} r={p.best_rel_gap > 0.05 ? 2.4 : 1.3}
            fill={p.best_rel_gap > 0.05 ? "none" : col[p.family]} stroke={col[p.family]} strokeWidth={p.best_rel_gap > 0.05 ? 1 : 0}
            opacity={0.7} />
        ))}
        <text x={W / 2} y={H - 4} textAnchor="middle" className="tick">solid fraction (0-{fmt(dmax, 2)})</text>
        <text x={10} y={H / 2} transform={`rotate(-90 10 ${H / 2})`} textAnchor="middle" className="tick">E100 / E_s (max {fmt(emax, 2)})</text>
      </svg>
    </div>
  );
}

export function AgentPanel() {
  return (
    <div className="agent">
      <div className="row"><b>Agent</b><span className="chip">stub</span></div>
      <p className="muted small">The agent is reached through the MCP server (<code>python -m amm.mcp_server --session DIR --profile C</code>), which serves the same
        tool contract (amm-tools/3) to an MCP client; its calls are logged with actor "agent". This panel is a stub: the GUI makes no LLM
        calls. Propose / Act modes with clarification chips are plan B5 second tier.</p>
      <textarea disabled placeholder="Describe the cell you need..." rows={3} />
      <div className="row buttons"><button disabled>Propose</button><button disabled>Act</button></div>
    </div>
  );
}
