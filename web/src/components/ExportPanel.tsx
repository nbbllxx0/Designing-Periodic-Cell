// Export and manufacturing screening (plan B2) through the amm tools `screen_manufacturing` and `export`: single-cell
// and tiled STL of the certified geometry model, report.json with the evidence, and the screening checks (minimum
// feature against a printer limit, tiled connectivity, watertight surface). Screening only: never a printability claim.
import { useState } from "react";
import { useStore } from "../store";
import { fmt } from "../physics";
import type { Design, ExportItem, Material } from "../types";

// amm.export.SCREEN_DISCLAIMER (shown before any result exists; results carry the tool's own copy)
const DISCLAIMER = "manufacturing screening only, NOT a printability claim: minimum feature against a stated printer " +
  "limit (one-voxel resolution), tiled connectivity and a watertight surface are checked; support, powder removal, " +
  "residual stress, roughness and process parameters are not";

const same = (a?: Design | null, b?: Design | null) => !!a && !!b && JSON.stringify(a) === JSON.stringify(b);
const kb = (n: number) => (n > 1e6 ? `${fmt(n / 1e6, 3)} MB` : `${fmt(n / 1e3, 3)} kB`);
const pf = (v: boolean | null | undefined) => (v === null || v === undefined ? "not checked" : v ? "pass" : "fail");

function Screening({ r }: { r: any }) {
  const mf = r.min_feature ?? {};
  const tc = r.tiled_connectivity ?? {};
  const wt = r.watertight ?? {};
  const wtv = (k: string) => (typeof wt[k] === "object" ? wt[k]?.watertight : wt[k]);
  return (
    <table className="kv screen">
      <tbody>
        <tr><td>verdict</td><td colSpan={2}><b className={r.passed ? "okc" : "badc"}>{r.verdict}</b></td></tr>
        <tr><td>min solid feature</td>
          <td>{mf.solid_est_mm !== undefined && mf.solid_est_mm !== null ? `~${fmt(mf.solid_est_mm, 3)} mm` : `${fmt(mf.solid_est_cell_units, 3)} a`}
            {mf.printer_limit_mm ? ` vs limit ${fmt(mf.printer_limit_mm, 3)} mm` : ""}</td>
          <td className={mf.passed ? "okc" : mf.passed === false ? "badc" : ""}>{pf(mf.passed)}
            {mf.solid_thinner_than_limit !== undefined ? ` (${fmt(100 * mf.solid_thinner_than_limit, 2)} % thinner)` : ""}</td></tr>
        <tr><td>narrowest channel</td>
          <td>{mf.void_est_mm !== undefined && mf.void_est_mm !== null ? `~${fmt(mf.void_est_mm, 3)} mm` : `${fmt(mf.void_est_cell_units, 3)} a`}</td>
          <td className={mf.void_passed === false ? "warnc" : ""}>{mf.void_passed === undefined ? "" : mf.void_passed ? "wider than limit" : "narrower than limit"}</td></tr>
        <tr><td>tiled connectivity</td>
          <td>{tc.tiles ? `${tc.tiles}^3 block: ` : ""}{tc.n_components ?? "-"} piece(s){tc.spans ? `, spans x/y/z ${tc.spans.map((x: boolean) => (x ? "y" : "n")).join("")}` : ""}</td>
          <td className={tc.passed ? "okc" : "badc"}>{pf(tc.passed)}</td></tr>
        <tr><td>watertight</td><td>cell {pf(wtv("cell"))}, tiled {pf(wtv("tiled"))}</td>
          <td className={wt.passed === false ? "badc" : "okc"}>{wt.passed === undefined ? "" : pf(wt.passed)}</td></tr>
        {mf.limit_source && <tr><td>printer limit</td><td colSpan={2} className="muted small">{mf.limit_source}</td></tr>}
        {mf.note && <tr><td></td><td colSpan={2} className="muted small">{mf.note}</td></tr>}
      </tbody>
    </table>
  );
}

function ExportFiles({ e }: { e: ExportItem }) {
  const r = e.result;
  return (
    <div className="exportfiles">
      <div className="row"><b>{r.name}</b><span className={`chip oc-${r.outcome}`}>{r.outcome_title}</span>
        <span className="muted small">#{e.seq}, lengths in {r.unit}</span></div>
      <ul>
        {Object.entries(e.files ?? {}).map(([k, f]) => (
          <li key={k}><a href={f.url} download>{f.path.split("/").pop()}</a>
            <span className="muted small"> {kb(f.bytes)}{f.n_triangles ? `, ${f.n_triangles} triangles (${f.method})` : ""}; sha256 {f.sha256.slice(0, 10)}</span></li>
        ))}
        {e.zip_url && <li><a href={e.zip_url} download>all files + session.jsonl (zip)</a></li>}
      </ul>
    </div>
  );
}

export function ExportPanel() {
  const mode = useStore((s) => s.mode);
  const design = useStore((s) => s.design);
  const summary = useStore((s) => s.summary);
  const materials = useStore((s) => s.materials);
  const call = useStore((s) => s.call);
  const jobs = useStore((s) => s.jobs);
  const [limit, setLimit] = useState("");
  const [tiles, setTiles] = useState(3);
  const [res, setRes] = useState(64);
  if (!summary || !design) return null;
  const st = summary.state;
  const mat: Material | null = typeof st.material === "string" ? materials[st.material] : null;
  const busy = Object.values(jobs).some((j) => (j.tool === "export" || j.tool === "screen_manufacturing")
    && (j.status === "queued" || j.status === "running"));
  const args = () => {
    const a: Record<string, unknown> = { design, tiles, resolution: res };
    if (limit) a.printer_min_feature_mm = Number(limit);
    return a;
  };
  const items = summary.exports ?? [];
  const lastScreen = items.find((e) => e.tool === "screen_manufacturing" || e.tool === "export");
  const lastExport = items.find((e) => e.tool === "export");
  const screenRes = lastScreen ? (lastScreen.tool === "export" ? lastScreen.result.screening : lastScreen.result) : null;
  return (
    <section className="panel export">
      <div className="panel-head"><h2>Export and manufacturing screening</h2><span className="muted small">amm tools, B2</span></div>
      <div className="disclaimer"><b>Screening only.</b> {screenRes?.disclaimer ?? lastExport?.result?.disclaimer ?? DISCLAIMER}.</div>
      <div className="row">
        <label>Printer limit</label>
        <input size={5} value={limit} onChange={(e) => setLimit(e.target.value)} aria-label="printer minimum feature (mm)"
          placeholder={mat?.min_feature ? fmt(mat.min_feature * 1e3, 3) : "mm"} />
        <span className="muted small">mm{!limit && mat?.min_feature ? ` (default: ${st.material} ${mat.process ?? ""} typical)` : ""}</span>
      </div>
      <div className="row">
        <label>Tiles</label>
        <select value={tiles} onChange={(e) => setTiles(Number(e.target.value))}>{[1, 2, 3, 4, 5].map((t) => <option key={t} value={t}>{t}^3</option>)}</select>
        <label className="check">samples / a</label>
        <select value={res} onChange={(e) => setRes(Number(e.target.value))}>{[32, 48, 64, 96].map((t) => <option key={t}>{t}</option>)}</select>
      </div>
      {!st.cell_size && <div className="warn">Set the cell size: the minimum-feature check and mm units need it.</div>}
      <div className="row buttons">
        <button disabled={busy} onClick={() => void call("screen_manufacturing", args())}>Screen manufacturing</button>
        <button disabled={busy} className="primary" onClick={() => void call("export", { ...args(), tile_resolution: 32 })}>
          Export STL + report</button>
      </div>
      {mode !== "live" && <div className="muted small">Mock mode: export and screening are served from recordings only (none
        exist for the development sessions); the header Export gives a preview bundle. Run with --live for the amm tools.</div>}
      {screenRes && (
        <>
          <h3>Screening #{lastScreen!.seq}{same(lastScreen!.design, design) ? "" : " (another design)"}</h3>
          <Screening r={screenRes} />
        </>
      )}
      {lastExport && (
        <>
          <h3>Export #{lastExport.seq}{same(lastExport.design, design) ? "" : " (another design)"}</h3>
          <ExportFiles e={lastExport} />
        </>
      )}
    </section>
  );
}
