// Shapes of the amm GUI backend responses (app/server.py). Normalized quantities: stiffness / E_s, f* = f a / c_t.

export type Params = Record<string, number | string>;
export interface Design {
  kind: string;
  params: Params;
}

export interface ToolParam {
  name: string;
  type: string;
  default: string | null;
  required: boolean;
}
export interface ToolSpec {
  name: string;
  doc: string;
  params: ToolParam[];
  mutates: boolean;
  profiles: string[];
  available: boolean;
  queued: boolean;
}

export interface Material {
  E: number;
  nu: number;
  rho: number;
  process?: string;
  min_feature?: number;
  tolerance?: number;
}

export interface KindInfo {
  params: Record<string, [number, number]>;
  modes: string[] | null;
}
export interface Families {
  families: Record<string, Record<string, KindInfo>>;
  rules: Record<string, string>;
  r_gap: number;
}

export interface LogRecord {
  type: string;
  seq?: number;
  t?: string;
  actor?: string;
  tool?: string;
  args?: Record<string, unknown>;
  ok?: boolean;
  result?: any;
  error?: string;
  dt_s?: number;
  mock_source?: { kind: string; session?: string; seq?: number; note?: string };
}

export interface EvidenceItem {
  label: string;
  value: string;
  margin?: number;
  verdict?: string;
}
export interface EvidenceRecord {
  ref: { seq: number; tool: string; actor?: string };
  items: EvidenceItem[];
  design?: Design;
}
export interface OutcomeCard {
  id: string;
  title: string;
  definition: string;
  status: "submitted" | "evidence" | "none";
  records: EvidenceRecord[];
  n_records: number;
}
export interface Evidence {
  cards: OutcomeCard[];
  submission: { decision: string; verdict?: string; note?: string } | null;
  submitted_outcome: string | null;
  consistency: string | null;
  need_info: boolean;
}

export interface Physical {
  material: { E: number; nu: number; rho: number } | null;
  c_t?: number;
  a_m?: number;
  fstar_to_Hz?: number;
}

export interface SessionState {
  material: string | { E: number; nu: number; rho: number } | null;
  cell_size: [number, string] | null;
  targets: Record<string, any>;
  families: string[];
  sources: Record<string, { source: string; note: string }>;
  gap_type: string | null;
}

export interface Summary {
  mode: "mock" | "live";
  meta: { kind: string; id?: string; source?: string; brief?: string | null; same_code?: boolean; profile?: string; code?: string;
    replay?: { n_mismatch: number } };
  profile: string;
  state: SessionState;
  normalized_targets: Record<string, any>;
  cannot_normalize: string[];
  certificates: Record<string, { verdict: string; robust: boolean }>;
  submission: any;
  budget_used: { designs: number; certify: number };
  budget: { designs: number; certify: number };
  seq: number;
  state_hash: string;
  log: LogRecord[];
  focus: Design | null;
  physical: Physical;
  evidence: Evidence;
  outcome: B1View;
  exports: ExportItem[];
  schema_version: string | null;
}

export interface Cubic {
  C11: number; C12: number; C44: number; E100: number; E110: number; E111: number; nu100: number; G: number;
  bulk: number; zener: number; E_max: number; E_min: number;
}
export interface Gap { below_band?: number; f_lo: number; f_hi: number; rel: number }
export interface SearchView {
  available: boolean;
  reason?: string;
  tier?: string;
  source?: { kind: string; note?: string; atlas_params?: Params; param_distance?: number; nu?: number; seq?: number };
  density?: number;
  valid?: boolean;
  cubic?: Cubic | null;
  bands?: number[][] | null;
  ticks?: [number, string][];
  gaps?: Gap[];
  tensor?: TensorView | null;
}
export interface Bound { lower: number; upper: number; extrapolated?: number; mode?: string; converged?: boolean }
export interface CertificateView {
  key: string;
  path: string;
  verdict: string;
  robust: boolean;
  spec: { kind: string; params: Params };
  targets: Record<string, any>;
  static?: { verdict: any; quantities: Record<string, Bound>; checks_failed: string[]; resolutions: number[];
    safety: number; tensor: { C11: number; C12: number; C44: number } | null; tensor_source: string | null };
  bloch?: { verdict: { verdict: string; reason?: string }; claim: { f_lo: number; f_hi: number; below_band: number };
    safe_interval: [number | null, number | null] | null; margins: { lower: number; upper: number } | null;
    safety: number; n_k: number; resolutions: Record<string, { passed: boolean; n_failures: number }> };
  as_built?: { offset: number; passed: boolean; cases: Record<string, { passed: boolean; density: number }> };
}
export interface Details {
  design: Design;
  family: string;
  search: SearchView;
  certificate: CertificateView | null;
  physical: Physical;
}

export interface Job {
  id: string;
  kind: string;
  tool: string;
  args: Record<string, unknown>;
  actor: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  t_queued: number;
  t_start: number | null;
  t_end: number | null;
  output: { ok: boolean; error?: string; result?: any; mock_source?: any } | null;
  progress?: JobProgress | null;
  cancel_requested?: boolean;
}

export interface Preview {
  kind: string;
  n: number;
  density_preview: number;
  vertices: number[];
  faces: number[];
  note: string;
}

export interface RecordedSession {
  id: string;
  source: string;
  profile: string;
  same_code: boolean;
  n_calls: number;
  decision: string | null;
  verdict: string | null;
  n_certificates: number;
}

// ---- live mode, B1 outcome schema, B2 export (2026-11-08) ---------------------------------------------------------
export interface B1Record {
  seq: number;
  tool: string;
  kind: string;
  outcome: string;
  summary: string;
  holds: boolean;
}
export interface B1Group {
  id: string;
  legacy: string | null;
  title: string;
  definition: string;
  records: B1Record[];
  n_records: number;
  n_holding: number;
}
export interface OutcomeCardB1 {
  schema_version: string;
  outcome: string | null;
  title: string;
  definition: string;
  decision: string;
  verdict: string | null;
  design: Design | null;
  profile: string;
  evidence_checked: boolean;
  evidence: { seq: number; tool: string; kind: string; outcome: string; summary: string }[];
}
export interface B1View {
  schema: string;
  profile: string;
  evidence_checked: boolean;
  groups: B1Group[];
  records: B1Record[];
  can_cite: Record<string, number[]>;
  hints: Record<string, string>;
  refusal_rule: Record<string, string[]>;
  card: OutcomeCardB1 | null;
  submit_seq: number | null;
  last_rejected_submit: { seq: number; args: any; error: string; refusal_rule: boolean } | null;
}
export interface ExportFile { path: string; sha256: string; bytes: number; n_triangles?: number; method?: string;
  unit?: string; url: string }
export interface ExportItem {
  seq: number;
  tool: "export" | "screen_manufacturing";
  design: Design;
  result: any;
  files?: Record<string, ExportFile>;
  zip_url?: string;
}
export interface TensorView {
  C: number[][];
  C_MPa?: number[][] | null;
  derived: Record<string, any>;
  kind: "full" | "cubic";
  source: string;
}
export interface JobProgress { stage?: string; last?: string; counts?: Record<string, number>; elapsed_s?: number }
