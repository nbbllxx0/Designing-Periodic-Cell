// Spec panel: material with its constants, cell size, targets in physical units with their normalized values,
// and the source of each item (stated / derived / assumed / answered), all through the tool contract.
import { useState } from "react";
import { useStore } from "../store";
import type { Material } from "../types";
import { fmt, frequency, pressure, PRESSURE_UNITS, FREQ_UNITS, TARGET_LABELS } from "../physics";

const SOURCES = ["stated", "derived", "assumed", "answered"] as const;

function SourceChip({ k }: { k: string }) {
  const summary = useStore((s) => s.summary);
  const call = useStore((s) => s.call);
  const src = summary?.state.sources[k];
  const next = () => {
    const i = src ? SOURCES.indexOf(src.source as (typeof SOURCES)[number]) : -1;
    void call("set_source", { key: k, source: SOURCES[(i + 1) % SOURCES.length], note: src?.note ?? "" });
  };
  return (
    <button className={`chip src-${src?.source ?? "none"}`} title={src?.note || "click to set the source of this item"}
      onClick={next}>
      {src?.source ?? "source?"}
    </button>
  );
}

function targetText(key: string, v: any, phys: { E?: number; ft?: number }): { shown: string; norm: string } {
  const info = TARGET_LABELS[key];
  if (!info) return { shown: JSON.stringify(v), norm: "" };
  if (info.kind === "stiffness") {
    if (Array.isArray(v)) return { shown: `${fmt(v[0])} ${v[1]}`, norm: "" };
    return { shown: `${fmt(v)} E_s`, norm: phys.E ? pressure(v * phys.E) : "" };
  }
  if (info.kind === "gap") {
    const lo = v.f_lo, hi = v.f_hi;
    if (Array.isArray(lo)) return { shown: `${fmt(lo[0])}-${fmt(hi[0])} ${hi[1]}`, norm: "" };
    return { shown: `${fmt(lo)}-${fmt(hi)} f*`, norm: phys.ft ? `${frequency(lo * phys.ft)}-${frequency(hi * phys.ft)}` : "" };
  }
  return { shown: fmt(v), norm: "" };
}

function normText(key: string, n: any): string {
  if (n === undefined) return "not normalized";
  if (key === "gap") return `f* ${fmt(n.f_lo)}-${fmt(n.f_hi)}`;
  if (TARGET_LABELS[key]?.kind === "stiffness") return `${fmt(n)} E_s`;
  return fmt(n);
}

function AddTarget() {
  const call = useStore((s) => s.call);
  const [key, setKey] = useState("E100_min");
  const [val, setVal] = useState("1");
  const [hi, setHi] = useState("2");
  const [unit, setUnit] = useState("GPa");
  const info = TARGET_LABELS[key];
  const units = info.kind === "stiffness" ? [...Object.keys(PRESSURE_UNITS), "E_s"] : info.kind === "gap"
    ? [...Object.keys(FREQ_UNITS), "f*"] : [];
  const apply = () => {
    const v = Number(val);
    let args: Record<string, unknown>;
    if (info.kind === "stiffness") args = { [key]: { value: v, unit } };
    else if (info.kind === "gap") args = { gap: { f_lo: v, f_hi: Number(hi), unit }, gap_type: "complete" };
    else args = { [key]: v };
    void call("set_target", args);
  };
  return (
    <div className="add-target">
      <select value={key} onChange={(e) => {
        const k = e.target.value;
        setKey(k);
        const kind = TARGET_LABELS[k].kind;
        setUnit(kind === "stiffness" ? "GPa" : kind === "gap" ? "kHz" : "");
      }}>
        {Object.entries(TARGET_LABELS).map(([k, i]) => (
          <option key={k} value={k}>{`${i.label} ${i.sense}`}</option>
        ))}
      </select>
      <input value={val} onChange={(e) => setVal(e.target.value)} size={6} aria-label="value" />
      {info.kind === "gap" && <input value={hi} onChange={(e) => setHi(e.target.value)} size={6} aria-label="upper" />}
      {units.length > 0 && (
        <select value={unit} onChange={(e) => setUnit(e.target.value)}>
          {units.map((u) => <option key={u}>{u}</option>)}
        </select>
      )}
      <button onClick={apply}>Set</button>
    </div>
  );
}

export function SpecPanel() {
  const summary = useStore((s) => s.summary);
  const materials = useStore((s) => s.materials);
  const call = useStore((s) => s.call);
  const [size, setSize] = useState("");
  if (!summary) return <section className="panel">loading...</section>;
  const st = summary.state;
  const matName = typeof st.material === "string" ? st.material : st.material ? "custom" : "";
  const mat: Material | null = typeof st.material === "string" ? materials[st.material] : st.material;
  const phys = { E: summary.physical.material?.E, ft: summary.physical.fstar_to_Hz };
  return (
    <section className="panel spec">
      <h2>Specification</h2>
      <div className="row">
        <label>Material</label>
        <select value={matName} onChange={(e) => void call("set_material", { name: e.target.value })}>
          <option value="" disabled>choose...</option>
          {Object.keys(materials).map((m) => <option key={m}>{m}</option>)}
        </select>
        <SourceChip k="material" />
      </div>
      {mat && (
        <table className="kv">
          <tbody>
            <tr><td>E_s</td><td>{pressure(mat.E)}</td><td>nu_s</td><td>{fmt(mat.nu, 3)}</td></tr>
            <tr><td>rho_s</td><td>{fmt(mat.rho)} kg/m3</td><td>c_t</td>
              <td>{summary.physical.c_t ? `${fmt(summary.physical.c_t)} m/s` : "-"}</td></tr>
            {mat.process && (
              <tr><td>process</td><td>{mat.process}</td><td>min feature</td>
                <td>{mat.min_feature ? `${fmt(mat.min_feature * 1e3)} mm` : "-"}</td></tr>
            )}
          </tbody>
        </table>
      )}
      <div className="row">
        <label>Cell size a</label>
        <span className="val">{st.cell_size ? `${fmt(st.cell_size[0])} ${st.cell_size[1]}` : "unset"}</span>
        <input placeholder="mm" size={5} value={size} onChange={(e) => setSize(e.target.value)} />
        <button onClick={() => size && void call("set_constraints", { cell_size: Number(size), cell_size_unit: "mm" })}>
          Set
        </button>
        <SourceChip k="cell_size" />
      </div>
      <div className="row">
        <label>Families</label>
        {["tpms", "struts", "resonator"].map((f) => (
          <label key={f} className="check">
            <input type="checkbox" checked={st.families.includes(f)} onChange={(e) => {
              const fams = e.target.checked ? [...st.families, f] : st.families.filter((x) => x !== f);
              if (fams.length) void call("set_constraints", { families: fams });
            }} />
            {f}
          </label>
        ))}
      </div>
      <h3>Targets</h3>
      <table className="targets">
        <thead><tr><th>target</th><th>stated</th><th>normalized</th><th>source</th></tr></thead>
        <tbody>
          {Object.entries(st.targets).length === 0 && <tr><td colSpan={4} className="muted">no targets yet</td></tr>}
          {Object.entries(st.targets).map(([k, v]) => {
            const t = targetText(k, v, phys);
            return (
              <tr key={k}>
                <td>{TARGET_LABELS[k]?.label ?? k} {TARGET_LABELS[k]?.sense}</td>
                <td>{t.shown}{t.norm && <div className="muted">{t.norm}</div>}</td>
                <td>{normText(k, summary.normalized_targets[k])}</td>
                <td><SourceChip k={k} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {summary.cannot_normalize.length > 0 && (
        <div className="warn">{summary.cannot_normalize.map((m) => <div key={m}>{m}</div>)}</div>
      )}
      <AddTarget />
      <div className="row buttons">
        <button onClick={() => void call("set_target", { clear: true })}>Clear targets</button>
        <button onClick={() => void call("check_bounds")} disabled={summary.profile !== "C"}>Check bounds</button>
        <button onClick={() => void call("undo")}>Undo</button>
      </div>
      <div className="budget muted">
        budget: {summary.budget_used.designs}/{summary.budget.designs} designs, {summary.budget_used.certify}/
        {summary.budget.certify} certificates; profile {summary.profile}
      </div>
    </section>
  );
}
