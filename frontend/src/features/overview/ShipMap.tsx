import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { StatusBadge } from '../../components/ui';
import type { CrewMember } from '../../lib/crew';
import { SECTORS, SEVERITY, VIEW_H, VIEW_W, VIEW_X0, ago, type Focus, type SectorId, type Severity, type ShipReport } from '../../lib/ship';

const LABEL_END = new Set<SectorId>(['bridge', 'cabins', 'galley', 'steering']);
const ZONES: { id: string; sectors: SectorId[]; at: [number, number] }[] = [
  { id: 'house', sectors: ['bridge', 'cabins', 'galley'], at: [228, 150] },
  { id: 'machinery', sectors: ['engine', 'purifier', 'ecr', 'steering'], at: [232, 340] },
  { id: 'deck', sectors: ['deck'], at: [820, 180] },
  { id: 'holds', sectors: ['holds'], at: [560, 340] },
  { id: 'bow', sectors: ['bow'], at: [1092, 300] },
  { id: 'tanks', sectors: ['tanks'], at: [880, 392] },
];
const SLOT_X = 44;
const SLOT_Y = 36;

interface Placed {
  key: string;
  x: number;
  y: number;
  severity: Severity;
  report?: ShipReport;
  /** aggregated pin: count of reports in the sector */
  count?: number;
  sector: SectorId;
  status?: ShipReport['status'];
}

const hash = (s: string) => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
};

const pct = (x: number, y: number) => ({ left: `${((x - VIEW_X0) / VIEW_W) * 100}%`, top: `${(y / VIEW_H) * 100}%` });

/** Stable slots: each report hashes to a slot in its sector, probing on collision. */
function place(reports: ShipReport[], compact: boolean): Placed[] {
  const bySector = new Map<SectorId, ShipReport[]>();
  for (const r of reports) {
    const list = bySector.get(r.sector);
    if (list) list.push(r);
    else bySector.set(r.sector, [r]);
  }
  const out: Placed[] = [];
  if (compact) {
    // Phone width: one pin per zone, otherwise the superstructure pins pile up.
    for (const g of ZONES) {
      const list = reports
        .filter((r) => g.sectors.includes(r.sector))
        .sort((a, b) => SEVERITY[a.severity].rank - SEVERITY[b.severity].rank);
      if (!list.length) continue;
      out.push({ key: `zone-${g.id}`, x: g.at[0], y: g.at[1], severity: list[0].severity, count: list.length, sector: list[0].sector });
    }
    return out;
  }
  for (const s of SECTORS) {
    const list = (bySector.get(s.id) ?? []).sort(
      (a, b) => SEVERITY[a.severity].rank - SEVERITY[b.severity].rank || b.updated_at.localeCompare(a.updated_at),
    );
    if (!list.length) continue;
    const [ax, ay, aw, ah] = s.area;
    const cols = Math.max(1, Math.floor(aw / SLOT_X) + 1);
    const rows = Math.max(1, Math.floor(ah / SLOT_Y) + 1);
    const slots = cols * rows;
    const taken = new Set<number>();
    const visible = list.length > slots ? list.slice(0, slots - 1) : list;
    for (const r of visible) {
      let i = hash(r.report_id) % slots;
      while (taken.has(i)) i = (i + 1) % slots;
      taken.add(i);
      const c = i % cols;
      const row = Math.floor(i / cols);
      const x = ax + (cols === 1 ? aw / 2 : (c * aw) / (cols - 1));
      const y = ay + (rows === 1 ? ah / 2 : (row * ah) / (rows - 1));
      out.push({ key: r.report_id, x, y, severity: r.severity, report: r, sector: s.id, status: r.status });
    }
    if (list.length > visible.length) {
      let i = 0;
      while (taken.has(i)) i++;
      const c = i % cols;
      const row = Math.floor(i / cols);
      out.push({
        key: `more-${s.id}`,
        x: ax + (cols === 1 ? aw / 2 : (c * aw) / (cols - 1)),
        y: ay + (rows === 1 ? ah / 2 : (row * ah) / (rows - 1)),
        severity: list[visible.length].severity,
        count: list.length - visible.length,
        sector: s.id,
      });
    }
  }
  return out;
}

function PinGlyph({ severity, status, count }: { severity: Severity; status?: string; count?: number }) {
  const ink = severity === 'progress' || severity === 'rejected' ? 'var(--color-cream)' : 'var(--color-ink)';
  return (
    <svg viewBox="0 0 28 36" width="28" height="36" aria-hidden className="drop-shadow-[0_3px_6px_rgba(0,0,0,0.55)]">
      <path
        d="M14 35C14 35 2 22.5 2 13.5a12 12 0 1 1 24 0C26 22.5 14 35 14 35Z"
        fill={SEVERITY[severity].color}
        stroke="rgba(0,0,0,0.35)"
      />
      {count !== undefined ? (
        <text x="14" y="17.5" textAnchor="middle" fontSize={count > 9 ? 10 : 12} fontWeight="700" fill={ink} fontFamily="var(--font-mono)">
          {count > 99 ? '99+' : count}
        </text>
      ) : severity === 'action' ? (
        <g fill={ink}>
          <rect x="12.4" y="6.5" width="3.2" height="9" rx="1.6" />
          <circle cx="14" cy="19.2" r="1.9" />
        </g>
      ) : status === 'needs_clarification' ? (
        <text x="14" y="18" textAnchor="middle" fontSize="13" fontWeight="800" fill={ink}>
          ?
        </text>
      ) : severity === 'resolved' ? (
        <path d="M9 13.5l3.4 3.4L19.5 9.8" fill="none" stroke={ink} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      ) : severity === 'progress' ? (
        <g fill={ink}>
          <circle cx="9.5" cy="13.5" r="1.7" />
          <circle cx="14" cy="13.5" r="1.7" />
          <circle cx="18.5" cy="13.5" r="1.7" />
        </g>
      ) : severity === 'open' ? (
        <g fill="none" stroke={ink} strokeWidth="2" strokeLinecap="round">
          <circle cx="14" cy="13.5" r="5.6" />
          <path d="M14 10.6v3.2l2 1.4" />
        </g>
      ) : (
        <path d="M10 13.5h8" stroke={ink} strokeWidth="2.4" strokeLinecap="round" />
      )}
    </svg>
  );
}

/** Decorative hull, structure and machinery. Sectors are drawn over it as hit areas. */
function Hull() {
  const line = 'var(--color-cream)';
  return (
    <g>
      <defs>
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" fill="none" stroke={line} strokeOpacity="0.045" strokeWidth="1" />
        </pattern>
        <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0c1f39" />
          <stop offset="1" stopColor="#000000" />
        </linearGradient>
        <linearGradient id="hullFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0e2442" />
          <stop offset="1" stopColor="#081629" />
        </linearGradient>
      </defs>

      <rect x={VIEW_X0} y="0" width={VIEW_W} height={VIEW_H} fill="url(#grid)" />
      <rect x={VIEW_X0} y="300" width={VIEW_W} height="160" fill="url(#water)" />
      <path
        d="M-40 300 Q 0 296 40 300 T 120 300 T 200 300 T 280 300 T 360 300 T 440 300 T 520 300 T 600 300 T 680 300 T 760 300 T 840 300 T 920 300 T 1000 300 T 1080 300 T 1160 300 T 1240 300"
        fill="none"
        stroke="var(--color-steel)"
        strokeOpacity="0.55"
        strokeWidth="1.5"
      />

      {/* funnel + mast */}
      <path d="M152 40 L160 8 H198 L194 40 Z" fill="#183a63" stroke={line} strokeOpacity="0.8" strokeWidth="1.4" />
      <rect x="157.5" y="16" width="38" height="7" fill="var(--color-steel)" />
      <path d="M300 40V10M286 16H314" stroke={line} strokeOpacity="0.7" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="300" cy="8" r="2.5" fill={line} />

      {/* superstructure */}
      <path d="M126 200V76H110V40H346V76H330V200Z" fill="#183a63" fillOpacity="0.75" stroke={line} strokeOpacity="0.85" strokeWidth="1.5" />
      <path d="M126 76H330M126 144H330" stroke={line} strokeOpacity="0.45" />
      <path d="M126 110H330" stroke={line} strokeOpacity="0.2" strokeDasharray="3 4" />
      {Array.from({ length: 12 }, (_, i) => (
        <rect key={i} x={146 + i * 14} y="47" width="9" height="11" rx="1.5" fill="var(--color-steel)" fillOpacity="0.55" />
      ))}
      {Array.from({ length: 8 }, (_, i) => (
        <g key={i} fill="none" stroke={line} strokeOpacity="0.35">
          <circle cx={150 + i * 22} cy="93" r="3.5" />
          <circle cx={150 + i * 22} cy="127" r="3.5" />
        </g>
      ))}

      {/* hull */}
      <path
        d="M60 200H1036V182H1150C1158 232 1148 300 1110 366C1100 384 1086 396 1062 398H168C132 398 110 386 104 362L104 322C82 318 64 308 54 292L48 236Z"
        fill="url(#hullFill)"
        stroke={line}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      {/* waterline inside the hull */}
      <path d="M52 300H1146" stroke={line} strokeOpacity="0.18" strokeDasharray="6 6" />
      <text x="1160" y="304" fontSize="10" fill="var(--color-steel)" fontFamily="var(--font-mono)">
        WL
      </text>

      {/* engine room */}
      <path d="M96 200V372M372 200V372" stroke={line} strokeOpacity="0.55" />
      <path d="M96 262H372" stroke={line} strokeOpacity="0.22" strokeDasharray="3 4" />
      <rect x="186" y="286" width="86" height="80" rx="4" fill="none" stroke={line} strokeOpacity="0.4" />
      {Array.from({ length: 5 }, (_, i) => (
        <rect key={i} x={192 + i * 16} y="274" width="11" height="22" rx="2" fill="none" stroke={line} strokeOpacity="0.4" />
      ))}
      <rect x="116" y="334" width="52" height="32" rx="3" fill="none" stroke={line} strokeOpacity="0.3" />
      <path d="M186 352H100" stroke={line} strokeOpacity="0.45" strokeWidth="2" />
      <ellipse cx="88" cy="341" rx="4" ry="11" fill="var(--color-steel)" fillOpacity="0.8" />
      <ellipse cx="88" cy="363" rx="4" ry="11" fill="var(--color-steel)" fillOpacity="0.8" />
      <path d="M58 322H74V384C68 390 62 390 58 384Z" fill="#183a63" stroke={line} strokeOpacity="0.7" />

      {/* holds */}
      {[380, 543, 706, 869, 1032].map((x) => (
        <path key={x} d={`M${x} 200V372`} stroke={line} strokeOpacity="0.5" />
      ))}
      {[4, 3, 2, 1].map((n, i) => (
        <text
          key={n}
          x={461 + i * 163}
          y="338"
          textAnchor="middle"
          fontSize="44"
          fontWeight="700"
          fill={line}
          fillOpacity="0.05"
          fontFamily="var(--font-mono)"
        >
          {n}
        </text>
      ))}
      {[380, 543, 706, 869].map((x) => (
        <rect key={x} x={x + 18} y="189" width="127" height="11" rx="2" fill="#183a63" stroke={line} strokeOpacity="0.55" />
      ))}
      {[543, 706, 869].map((x) => (
        <g key={x} stroke={line} strokeOpacity="0.6" fill="#183a63">
          <rect x={x - 6} y="160" width="12" height="29" />
          <rect x={x - 9} y="152" width="18" height="10" rx="2" />
          <path d={`M${x + 4} 156L${x + 62} 138`} strokeWidth="3" strokeLinecap="round" />
        </g>
      ))}
      <path d="M152 372H1086" stroke={line} strokeOpacity="0.4" />
      {Array.from({ length: 9 }, (_, i) => (
        <path key={i} d={`M${240 + i * 100} 372V396`} stroke={line} strokeOpacity="0.18" />
      ))}

      {/* bow */}
      <path d="M1036 182V364" stroke={line} strokeOpacity="0.5" />
      <circle cx="1084" cy="336" r="13" fill="none" stroke={line} strokeOpacity="0.45" />
      <path d="M1076 336H1092M1084 328V344" stroke={line} strokeOpacity="0.35" />
      <rect x="1080" y="172" width="22" height="10" rx="2" fill="#183a63" stroke={line} strokeOpacity="0.6" />

      {/* steering gear room */}
      <path d="M52 214H96M52 300H96" stroke={line} strokeOpacity="0.3" />
    </g>
  );
}

export function ShipMap({
  reports,
  focus,
  highlight,
  thread,
  onFocus,
  crew = [],
}: {
  reports: ShipReport[];
  focus: Focus | null;
  /** ids to keep bright; everything else dims. null = no dimming */
  highlight: Set<string> | null;
  /** ordered ids to connect with arcs */
  thread: { from: string; to: string }[];
  onFocus: (f: Focus | null) => void;
  /** roster: on-duty / resting counts appear next to each compartment label */
  crew?: CrewMember[];
}) {
  const duty = useMemo(() => {
    const m = new Map<string, { on: number; off: number }>();
    for (const c of crew) {
      const d = m.get(c.station) ?? { on: 0, off: 0 };
      if (c.on_duty) d.on++;
      else d.off++;
      m.set(c.station, d);
    }
    return m;
  }, [crew]);
  const box = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(() => typeof window !== 'undefined' && window.innerWidth < 640);
  // Measure before paint so phones never flash the full pin layout.
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    setCompact(el.getBoundingClientRect().width < 560);
    const ro = new ResizeObserver(([e]) => setCompact(e.contentRect.width < 560));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const placed = useMemo(() => place(reports, compact), [reports, compact]);
  const pos = useMemo(() => new Map(placed.filter((p) => p.report).map((p) => [p.key, p])), [placed]);
  const sectorAlert = useMemo(() => new Set(reports.filter((r) => r.severity === 'action').map((r) => r.sector)), [reports]);

  const focusSector = focus?.kind === 'sector' ? focus.id : null;
  const focusId = focus?.kind === 'report' ? focus.id : null;
  const threadKey = JSON.stringify(focus);

  return (
    <div ref={box} className="relative w-full select-none" style={{ aspectRatio: `${VIEW_W} / ${VIEW_H}` }}>
      <svg
        viewBox={`${VIEW_X0} 0 ${VIEW_W} ${VIEW_H}`}
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label="Ship cross-section with report pins"
      >
        <Hull />
        {SECTORS.map((s) => (
          <path
            key={s.id}
            d={s.d}
            className="sector"
            data-alert={sectorAlert.has(s.id)}
            data-active={focusSector === s.id}
            stroke={focusSector === s.id ? 'var(--color-cream)' : 'none'}
            strokeOpacity="0.7"
            strokeDasharray="5 4"
            onClick={() => onFocus(focusSector === s.id ? null : { kind: 'sector', id: s.id })}
          >
            <title>{s.label}</title>
          </path>
        ))}
        {SECTORS.map((s) => (
          <text
            key={s.id}
            x={s.labelAt[0]}
            y={s.labelAt[1]}
            textAnchor={LABEL_END.has(s.id) ? 'end' : 'start'}
            className="sector-label pointer-events-none"
            fontSize="10.5"
            letterSpacing="1.4"
            fontFamily="var(--font-mono)"
            fill={focusSector === s.id ? 'var(--color-cream)' : sectorAlert.has(s.id) ? 'var(--color-alert)' : 'var(--color-cream)'}
            fillOpacity={focusSector === s.id || sectorAlert.has(s.id) ? 0.95 : 0.5}
          >
            {s.label.toUpperCase()}
            {duty.get(s.id)?.on ? (
              <tspan fill="var(--color-ok)" fillOpacity="1">
                {'  ●'}
                {duty.get(s.id)!.on}
              </tspan>
            ) : null}
            {duty.get(s.id)?.off ? (
              <tspan fill="var(--color-cream)" fillOpacity="0.6">
                {' ○'}
                {duty.get(s.id)!.off}
              </tspan>
            ) : null}
          </text>
        ))}

        {/* the "brain": arcs between connected reports */}
        <g key={threadKey} fill="none" strokeLinecap="round">
          {thread.map(({ from, to }) => {
            const a = pos.get(from);
            const b = pos.get(to);
            if (!a || !b) return null;
            const lift = 70 + Math.abs(a.x - b.x) * 0.22;
            const d = `M${a.x} ${a.y - 18}Q${(a.x + b.x) / 2} ${Math.min(a.y, b.y) - lift} ${b.x} ${b.y - 18}`;
            return (
              <g key={`${from}-${to}`}>
                <path d={d} stroke="var(--color-steel)" strokeOpacity="0.35" strokeWidth="6" pathLength={1} className="link" />
                <path d={d} stroke="var(--color-cream)" strokeOpacity="0.9" strokeWidth="1.6" pathLength={1} className="link" />
              </g>
            );
          })}
        </g>
      </svg>

      {placed.map((p) => {
        const selected = !!p.report && p.report.report_id === focusId;
        const dim = highlight
          ? !(p.report
              ? highlight.has(p.report.report_id)
              : p.count !== undefined && reports.some((r) => r.sector === p.sector && highlight.has(r.report_id)))
          : false;
        const label = p.report
          ? `${p.report.form?.equipment ?? 'Voice report'} — ${SEVERITY[p.severity].label}`
          : `${p.count} report${p.count === 1 ? '' : 's'} in ${SECTORS.find((s) => s.id === p.sector)?.label}`;
        return (
          <button
            key={p.key}
            type="button"
            aria-label={label}
            data-selected={selected}
            data-dim={dim}
            onClick={(e) => {
              e.stopPropagation();
              if (p.report) onFocus(selected ? null : { kind: 'report', id: p.report.report_id });
              else onFocus({ kind: 'sector', id: p.sector });
            }}
            className={`pin group absolute -ml-[14px] -mt-[36px] h-9 w-7 ${p.severity === 'action' && !dim ? 'pulse' : ''}`}
            style={pct(p.x, p.y)}
          >
            <PinGlyph severity={p.severity} status={p.status} count={p.count} />
            {p.report && (
              <span className="pin-tip absolute bottom-full left-1/2 mb-2 -ml-[120px] w-[240px] rounded-xl border border-cream/15 bg-navy-deep/95 p-3 text-left shadow-xl shadow-ink/50 backdrop-blur">
                <span className="block truncate text-sm font-semibold">{p.report.form?.equipment ?? 'Voice report'}</span>
                <span className="mt-0.5 block truncate text-xs text-cream/60">{p.report.form?.defect ?? p.report.transcript?.text}</span>
                <span className="mt-2 flex items-center justify-between gap-2">
                  <StatusBadge status={p.report.status} />
                  <span className="font-mono text-[11px] text-cream/50">{ago(p.report.updated_at)}</span>
                </span>
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
