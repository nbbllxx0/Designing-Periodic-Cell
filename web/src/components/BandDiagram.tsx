// Band diagram along G-X-M-G-R-X (search tier) with the target gap, the certified safe interval and its margins.
import { useStore } from "../store";
import { fmt, frequency } from "../physics";

const W = 560, H = 300, L = 52, R = 64, T = 14, B = 30;

export function BandDiagram() {
  const details = useStore((s) => s.details);
  const summary = useStore((s) => s.summary);
  const s = details?.search;
  const cert = details?.certificate;
  const target = summary?.normalized_targets?.gap as { f_lo: number; f_hi: number } | undefined;
  const ft = summary?.physical.fstar_to_Hz;
  const head = (
    <div className="panel-head">
      <h2>Band diagram</h2>
      <span className="muted small">f* = f a / c_t{ft ? `; right axis in Hz (a, c_t of the spec)` : ""}</span>
    </div>
  );
  if (!s?.available || !s.bands) {
    return <section className="panel bands">{head}<div className="muted">{s?.reason ?? "no band data for this design"}</div></section>;
  }
  const bands = s.bands;
  const nk = bands.length;
  const nb = bands[0].length;
  const claim = cert?.bloch?.claim ?? target;
  const safe = cert?.bloch?.safe_interval;
  // show the lowest ~12 bands, the target and the safe interval
  let fmax = Math.max(...bands.map((b) => b[Math.min(nb - 1, 11)]));
  if (claim) fmax = Math.max(fmax, claim.f_hi * 1.25);
  if (safe && safe[1]) fmax = Math.max(fmax, safe[1] * 1.1);
  const x = (i: number) => L + (i / (nk - 1)) * (W - L - R);
  const y = (f: number) => H - B - (f / fmax) * (H - T - B);
  const ticksY: number[] = [];
  const step = fmax > 1.5 ? 0.5 : fmax > 0.6 ? 0.2 : 0.1;
  for (let f = 0; f <= fmax + 1e-9; f += step) ticksY.push(f);
  const gaps = s.gaps ?? [];
  return (
    <section className="panel bands">
      {head}
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="band diagram">
        <defs><clipPath id="plotclip"><rect x={L} y={T} width={W - L - R} height={H - T - B} /></clipPath></defs>
        {/* search-tier complete gaps */}
        {gaps.map((g, i) => (
          <rect key={`g${i}`} x={L} width={W - L - R} y={Math.max(T, y(g.f_hi))} height={Math.max(0, y(g.f_lo) - Math.max(T, y(g.f_hi)))}
            className="gap-search" />
        ))}
        {/* certified safe interval and the target claim */}
        {safe && safe[0] !== null && safe[1] !== null && (
          <rect x={L} width={W - L - R} y={y(safe[1]!)} height={y(safe[0]!) - y(safe[1]!)} className="gap-safe" />
        )}
        {claim && (
          <rect x={L} width={W - L - R} y={y(claim.f_hi)} height={y(claim.f_lo) - y(claim.f_hi)} className="gap-claim" />
        )}
        {/* axes */}
        {ticksY.map((f) => (
          <g key={f}>
            <line x1={L} x2={W - R} y1={y(f)} y2={y(f)} className="grid" />
            <text x={L - 6} y={y(f) + 4} textAnchor="end" className="tick">{f.toFixed(step < 0.2 ? 2 : 1)}</text>
            {ft && <text x={W - R + 6} y={y(f) + 4} className="tick">{frequency(f * ft)}</text>}
          </g>
        ))}
        {(s.ticks ?? []).map(([i, lab]) => (
          <g key={`${i}${lab}`}>
            <line x1={x(i)} x2={x(i)} y1={T} y2={H - B} className="axis" />
            <text x={x(i)} y={H - B + 16} textAnchor="middle" className="tick">{lab === "G" ? "Γ" : lab}</text>
          </g>
        ))}
        <g clipPath="url(#plotclip)">
          {Array.from({ length: nb }, (_, j) => (
            <polyline key={j} className="band" fill="none"
              points={bands.map((b, i) => `${x(i)},${y(b[j])}`).join(" ")} />
          ))}
        </g>
        <rect x={L} y={T} width={W - L - R} height={H - T - B} className="frame" />
        <text x={14} y={T + (H - T - B) / 2} transform={`rotate(-90 14 ${T + (H - T - B) / 2})`} textAnchor="middle"
          className="tick">f*</text>
      </svg>
      <div className="legend small">
        <span><i className="sw claim" /> target gap{claim ? ` ${fmt(claim.f_lo, 3)}-${fmt(claim.f_hi, 3)}` : " (none)"}</span>
        {safe && <span><i className="sw safe" /> certified safe interval {fmt(safe[0], 3)}-{fmt(safe[1], 3)}
          {cert?.bloch?.margins ? `; margins ${fmt(cert.bloch.margins.lower, 3)} below, ${fmt(cert.bloch.margins.upper, 3)} above` : ""}
          {cert?.bloch?.verdict ? ` (${cert.bloch.verdict.verdict}${cert.bloch.verdict.reason ? ": " + cert.bloch.verdict.reason : ""})` : ""}</span>}
        <span><i className="sw search" /> search-tier gaps{gaps.length ? ": " + gaps.map((g) => `${fmt(g.f_lo, 3)}-${fmt(g.f_hi, 3)} (${fmt(100 * g.rel, 3)} %)`).join(", ") : ": none"}</span>
      </div>
      <div className="muted small">bands: {s.tier}; {s.source?.note}
        {s.source?.atlas_params ? ` (atlas cell ${Object.entries(s.source.atlas_params).map(([k, v]) => `${k}=${v}`).join(", ")})` : ""}</div>
    </section>
  );
}
