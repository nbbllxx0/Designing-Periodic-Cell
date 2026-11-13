// Client-side helpers: unit display, cubic directional Young's modulus, design validity (mirror of amm.atlas.valid).
import type { Design, Families } from "./types";

export const PRESSURE_UNITS: Record<string, number> = { Pa: 1, kPa: 1e3, MPa: 1e6, GPa: 1e9, psi: 6894.757 };
export const FREQ_UNITS: Record<string, number> = { Hz: 1, kHz: 1e3, MHz: 1e6 };

export function fmt(x: number | null | undefined, nd = 4): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "-";
  if (x === 0) return "0";
  const a = Math.abs(x);
  if (a >= 1e5 || a < 1e-3) return x.toExponential(nd - 1);
  return x.toPrecision(nd).replace(/\.?0+$/, (m) => (m.includes(".") ? "" : m));
}

/** Pick a display unit for a pressure in Pa. */
export function pressure(pa: number | null | undefined): string {
  if (pa === null || pa === undefined) return "-";
  const a = Math.abs(pa);
  if (a >= 1e9) return `${fmt(pa / 1e9, 4)} GPa`;
  if (a >= 1e6) return `${fmt(pa / 1e6, 4)} MPa`;
  if (a >= 1e3) return `${fmt(pa / 1e3, 4)} kPa`;
  return `${fmt(pa, 4)} Pa`;
}

export function frequency(hz: number | null | undefined): string {
  if (hz === null || hz === undefined) return "-";
  const a = Math.abs(hz);
  if (a >= 1e6) return `${fmt(hz / 1e6, 4)} MHz`;
  if (a >= 1e3) return `${fmt(hz / 1e3, 4)} kHz`;
  return `${fmt(hz, 4)} Hz`;
}

/** E(n) of a cubic material: 1/E = S11 - 2 (S11 - S12 - S44/2) (n1^2 n2^2 + n2^2 n3^2 + n3^2 n1^2). */
export function youngDirectional(C11: number, C12: number, C44: number, x: number, y: number, z: number): number {
  const d = (C11 - C12) * (C11 + 2 * C12);
  const S11 = (C11 + C12) / d;
  const S12 = -C12 / d;
  const S44 = 1 / C44;
  const r2 = x * x + y * y + z * z;
  const J = (x * x * y * y + y * y * z * z + z * z * x * x) / (r2 * r2);
  return 1 / (S11 - 2 * (S11 - S12 - S44 / 2) * J);
}

export function familyOf(fam: Families | null, kind: string): string | null {
  if (!fam) return null;
  for (const [f, kinds] of Object.entries(fam.families)) if (kind in kinds) return f;
  return null;
}

/** Validity rule of amm.atlas.valid (geometric, not physics). Returns a message when violated. */
export function validity(fam: Families | null, d: Design): string | null {
  const p = d.params as Record<string, number>;
  if (d.kind === "cube_bars" && !(p.w <= p.c - 0.04)) return "cube_bars needs w <= c - 0.04 (bars thinner than the core)";
  if (d.kind === "sphere_ligaments" && !(p.w <= 2 * p.c - 0.02)) return "sphere_ligaments needs w <= 2c - 0.02";
  if (familyOf(fam, d.kind) === "struts" && !(p.R === 0 || p.R >= p.r + (fam?.r_gap ?? 0.03)))
    return `struts need R = 0 or R >= r + ${fam?.r_gap ?? 0.03}`;
  return null;
}

/** Default design of a kind: box mid-points (struts: R = 0; TPMS: network). */
export function defaultDesign(fam: Families, kind: string): Design {
  const f = familyOf(fam, kind)!;
  const info = fam.families[f][kind];
  const params: Record<string, number | string> = {};
  for (const [k, [lo, hi]] of Object.entries(info.params)) params[k] = Math.round(((lo + hi) / 2) * 1000) / 1000;
  if (f === "struts") params.R = 0;
  if (f === "resonator" && kind === "cube_bars") params.w = Math.min(params.w as number, (params.c as number) - 0.04);
  if (info.modes) params.mode = "network";
  return { kind, params };
}

// a perceptual sequential colormap (viridis control points)
const VIRIDIS = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
export function viridis(t: number): [number, number, number] {
  const u = Math.min(Math.max(t, 0), 1) * (VIRIDIS.length - 1);
  const i = Math.min(Math.floor(u), VIRIDIS.length - 2);
  const f = u - i;
  const a = VIRIDIS[i], b = VIRIDIS[i + 1];
  return [0, 1, 2].map((j) => (a[j] + f * (b[j] - a[j])) / 255) as [number, number, number];
}

export const TARGET_LABELS: Record<string, { label: string; kind: "fraction" | "stiffness" | "ratio" | "gap"; sense: string }> = {
  density_max: { label: "Solid fraction", kind: "fraction", sense: "<=" },
  density_min: { label: "Solid fraction", kind: "fraction", sense: ">=" },
  E100_min: { label: "E100 (Young's, cube axis)", kind: "stiffness", sense: ">=" },
  E100_max: { label: "E100 (Young's, cube axis)", kind: "stiffness", sense: "<=" },
  G_min: { label: "G (shear, C44)", kind: "stiffness", sense: ">=" },
  bulk_min: { label: "Bulk modulus", kind: "stiffness", sense: ">=" },
  nu100_min: { label: "Poisson ratio nu100", kind: "ratio", sense: ">=" },
  nu100_max: { label: "Poisson ratio nu100", kind: "ratio", sense: "<=" },
  gap: { label: "Complete band gap", kind: "gap", sense: "covers" },
};

/** Inverse of a small dense matrix (Gauss-Jordan with partial pivoting); null if singular. */
export function invert(A: number[][]): number[][] | null {
  const n = A.length;
  const M = A.map((r, i) => [...r, ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    if (Math.abs(M[p][c]) < 1e-300) return null;
    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c];
    for (let j = 0; j < 2 * n; j++) M[c][j] /= d;
    for (let r = 0; r < n; r++) {
      if (r === c) continue;
      const f = M[r][c];
      if (f) for (let j = 0; j < 2 * n; j++) M[r][j] -= f * M[c][j];
    }
  }
  return M.map((r) => r.slice(n));
}

/** E(n) from the full compliance S = inv(C*) (6x6 Voigt, engineering shear, order 11 22 33 23 13 12):
 * 1/E(n) = m^T S m with m = (n1^2, n2^2, n3^2, n2 n3, n1 n3, n1 n2) (amm/tensor.py). */
export function youngFromCompliance(S: number[][], x: number, y: number, z: number): number {
  const r = Math.hypot(x, y, z);
  const a = x / r, b = y / r, c = z / r;
  const m = [a * a, b * b, c * c, b * c, a * c, a * b];
  let q = 0;
  for (let i = 0; i < 6; i++) for (let j = 0; j < 6; j++) q += m[i] * S[i][j] * m[j];
  return 1 / q;
}
