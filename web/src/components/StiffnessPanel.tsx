// Effective stiffness: the full 6x6 C* of the session's evaluate call (search tier; schema amm-tools/3), its derived
// quantities, the cubic constants (certificate finest rung when held), guarded certificate bounds against the targets,
// and the directional Young's modulus surface E(n) (from the full tensor when it is known).
import { useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useStore } from "../store";
import { fmt, invert, pressure, viridis, youngDirectional, youngFromCompliance } from "../physics";
import type { Cubic, TensorView } from "../types";

function cubicFrom(C11: number, C12: number, C44: number): Cubic {
  const E = (x: number, y: number, z: number) => youngDirectional(C11, C12, C44, x, y, z);
  const e = [E(1, 0, 0), E(1, 1, 0), E(1, 1, 1)];
  return { C11, C12, C44, E100: e[0], E110: e[1], E111: e[2], nu100: C12 / (C11 + C12), G: C44,
    bulk: (C11 + 2 * C12) / 3, zener: (2 * C44) / (C11 - C12), E_max: Math.max(...e), E_min: Math.min(...e) };
}

type EFn = (x: number, y: number, z: number) => number;

function YoungSurface({ E, k }: { E: EFn; k: string }) {
  const geo = useMemo(() => {
    const g = new THREE.SphereGeometry(1, 96, 64);
    const pos = g.attributes.position as THREE.BufferAttribute;
    const col = new Float32Array(pos.count * 3);
    const vals: number[] = [];
    for (let i = 0; i < pos.count; i++) vals.push(E(pos.getX(i), pos.getY(i), pos.getZ(i)));
    const emax = Math.max(...vals), emin = Math.min(...vals);
    for (let i = 0; i < pos.count; i++) {
      const s = vals[i] / emax;
      pos.setXYZ(i, pos.getX(i) * s, pos.getY(i) * s, pos.getZ(i) * s);
      const [r, gg, b] = viridis(emax > emin ? (vals[i] - emin) / (emax - emin) : 0.5);
      col.set([r, gg, b], 3 * i);
    }
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    g.computeVertexNormals();
    return g;
  }, [k]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <mesh geometry={geo}>
      <meshStandardMaterial vertexColors roughness={0.6} />
    </mesh>
  );
}

function Axes() {
  return (
    <group>
      {([[1.25, 0, 0, "#c33"], [0, 1.25, 0, "#3a3"], [0, 0, 1.25, "#36c"]] as [number, number, number, string][]).map(
        ([x, y, z, c]) => <Line key={c} points={[[0, 0, 0], [x, y, z]]} color={c} lineWidth={2} />)}
    </group>
  );
}

const VOIGT = ["11", "22", "33", "23", "13", "12"];

function FullTensor({ t, Es }: { t: TensorView; Es?: number }) {
  const [phys, setPhys] = useState(false);
  const d = t.derived ?? {};
  const M = phys && Es ? t.C.map((r) => r.map((v) => (v * Es) / 1e6)) : t.C;
  const scale = Math.max(...t.C.flat().map(Math.abs));
  const items: [string, string][] = [
    ["E[100] / E[110] / E[111]", [d.E100, d.E110, d.E111].map((x: number) => fmt(x, 4)).join(" / ")],
    ["Zener A", fmt(d.zener, 4)], ["cubic deviation", fmt(d.cubic_deviation, 3)], ["nu12", fmt(d.nu12, 4)],
    ["bulk Voigt / Reuss", `${fmt(d.bulk_voigt, 4)} / ${fmt(d.bulk_reuss, 4)}`],
    ["shear Voigt / Reuss", `${fmt(d.shear_voigt, 4)} / ${fmt(d.shear_reuss, 4)}`],
    ["eigenvalues", (d.eigenvalues ?? []).map((x: number) => fmt(x, 3)).join(", ")],
  ];
  return (
    <div className="fulltensor">
      <div className="row">
        <b>C* (6x6 Voigt{t.kind === "cubic" ? ", cubic reconstruction" : ", full tensor"})</b>
        <span className="muted small">order 11 22 33 23 13 12, engineering shear; {phys && Es ? "MPa" : "/ E_s"}</span>
        {Es && <button className={phys ? "on" : ""} onClick={() => setPhys(!phys)}>{phys ? "show / E_s" : "show MPa"}</button>}
      </div>
      <table className="c6">
        <thead><tr><th></th>{VOIGT.map((v) => <th key={v}>{v}</th>)}</tr></thead>
        <tbody>
          {M.map((r, i) => (
            <tr key={i}><th>{VOIGT[i]}</th>
              {r.map((v, j) => {
                const rel = Math.abs(t.C[i][j]) / scale;
                return <td key={j} className={rel < 1e-6 ? "zero" : ""} style={{ background: `rgba(47,111,184,${(0.05 + 0.3 * rel).toFixed(3)})` }}>
                  {rel < 1e-9 ? "0" : fmt(v, 4)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <table className="kv small derived"><tbody>
        {items.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}
      </tbody></table>
      <div className="muted small">{t.source}</div>
    </div>
  );
}

export function StiffnessPanel() {
  const details = useStore((s) => s.details);
  const summary = useStore((s) => s.summary);
  const Es = summary?.physical.material?.E;
  const search = details?.search?.cubic ?? null;
  const ct = details?.certificate?.static?.tensor;
  const certC = ct ? cubicFrom(ct.C11, ct.C12, ct.C44) : null;
  const show = certC ?? search;
  const tensor = details?.search?.tensor ?? null;
  const S = tensor ? invert(tensor.C) : null;
  const surf: { E: EFn; k: string; label: string } | null = certC
    ? { E: (x, y, z) => youngDirectional(certC.C11, certC.C12, certC.C44, x, y, z), k: `c${certC.C11}${certC.C12}${certC.C44}`,
      label: "cubic constants of the certificate's finest rung" }
    : S && tensor ? { E: (x, y, z) => youngFromCompliance(S, x, y, z), k: `t${tensor.C.flat().join(",")}`,
      label: tensor.kind === "full" ? "full tensor C* (search tier)" : "cubic C* (search tier)" }
    : show ? { E: (x, y, z) => youngDirectional(show.C11, show.C12, show.C44, x, y, z), k: `s${show.C11}${show.C12}${show.C44}`,
      label: "search tier" } : null;
  const q = details?.certificate?.static?.quantities ?? {};
  const tgt = summary?.normalized_targets ?? {};
  const rows: [keyof Cubic, string][] = [["C11", "C11"], ["C12", "C12"], ["C44", "C44 = G"], ["E100", "E[100]"],
    ["E110", "E[110]"], ["E111", "E[111]"], ["bulk", "bulk K"], ["nu100", "nu[100]"], ["zener", "Zener A"]];
  const dimless = new Set(["nu100", "zener"]);
  const bound = (k: string) => {
    const m: Record<string, string> = { E100: "E100", G: "G", C44: "G", bulk: "bulk", nu100: "nu100" };
    return m[k] ? q[m[k]] : undefined;
  };
  const tline = (k: string) => {
    const m: Record<string, string[]> = { E100: ["E100_min", "E100_max"], C44: ["G_min"], bulk: ["bulk_min"],
      nu100: ["nu100_min", "nu100_max"] };
    return (m[k] ?? []).filter((t) => tgt[t] !== undefined).map((t) => `${t.endsWith("min") ? ">=" : "<="} ${fmt(tgt[t])}`).join(", ");
  };
  return (
    <section className="panel stiffness">
      <div className="panel-head">
        <h2>Effective stiffness C*</h2>
        <span className="muted small">normalized by E_s{Es ? `; physical with E_s = ${pressure(Es)}` : ""}</span>
      </div>
      {!search && !certC && <div className="muted">{details?.search?.reason ?? "no stiffness data for this design"}</div>}
      {(search || certC) && (
        <div className="stiff-grid">
          <table className="ctable">
            <thead>
              <tr><th></th><th>search tier</th>{certC && <th>certificate</th>}{certC && <th>guarded bound</th>}<th>target</th></tr>
            </thead>
            <tbody>
              {rows.map(([k, lab]) => {
                const b = bound(k as string);
                return (
                  <tr key={k}>
                    <td>{lab}</td>
                    <td>{search ? fmt(search[k] as number) : "-"}
                      {search && Es && !dimless.has(k) && <div className="muted">{pressure((search[k] as number) * Es)}</div>}</td>
                    {certC && <td>{fmt(certC[k] as number)}
                      {Es && !dimless.has(k) && <div className="muted">{pressure((certC[k] as number) * Es)}</div>}</td>}
                    {certC && <td>{b ? `[${fmt(b.lower)}, ${fmt(b.upper)}]` : ""}</td>}
                    <td>{tline(k as string)}</td>
                  </tr>
                );
              })}
              {q.density && (
                <tr><td>solid fraction</td><td>{fmt(details?.search?.density)}</td>
                  <td>{fmt(q.density.extrapolated)}</td><td>[{fmt(q.density.lower)}, {fmt(q.density.upper)}]</td>
                  <td>{[tgt.density_max !== undefined ? `<= ${fmt(tgt.density_max)}` : "", tgt.density_min !== undefined ? `>= ${fmt(tgt.density_min)}` : ""].filter(Boolean).join(", ")}</td></tr>
              )}
            </tbody>
          </table>
          <div className="esurf">
            <Canvas camera={{ position: [1.9, 1.5, 2.2], fov: 38 }} gl={{ preserveDrawingBuffer: true }}>
              <color attach="background" args={["#f4f6f9"]} />
              <ambientLight intensity={0.6} />
              <directionalLight position={[3, 4, 5]} intensity={0.9} />
              {surf && <YoungSurface E={surf.E} k={surf.k} />}
              <Axes />
              <OrbitControls makeDefault enableDamping={false} />
            </Canvas>
            <div className="overlay small">
              E(n) / E_max; E_max {show ? fmt(show.E_max) : "-"}, E_min {show ? fmt(show.E_min) : "-"} (E_s units)
              <br />from the {surf?.label ?? "-"}; x red, y green, z blue
            </div>
          </div>
        </div>
      )}
      <div className="muted small">
        {details?.certificate?.static?.tensor_source ?? (search ? `search tier: ${details?.search?.source?.note ?? ""}` : "")}
      </div>
      {tensor && <FullTensor t={tensor} Es={Es} />}
    </section>
  );
}
