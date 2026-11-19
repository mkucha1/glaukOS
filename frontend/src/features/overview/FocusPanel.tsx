import { useNavigate } from 'react-router-dom';
import { Btn, Eyebrow, PriorityBadge, StatusBadge, cx } from '../../components/ui';
import {
  AWAITING_STATUSES,
  SEVERITY,
  ago,
  equipmentKey,
  personName,
  personRole,
  relatedTo,
  reportsFor,
  sectorById,
  sfiGroup,
  SFI_GROUPS,
  type Focus,
  type Severity,
  type ShipReport,
} from '../../lib/ship';
import { MindMap, type MindNode, type Tone } from './MindMap';

const TONE: Record<Severity, Tone> = { action: 'alert', open: 'warn', progress: 'steel', resolved: 'ok', rejected: 'muted' };
const LANG: Record<string, string> = { pl: 'Polish', tl: 'Tagalog', en: 'English', uk: 'Ukrainian', ru: 'Russian', fil: 'Filipino' };

function SeverityChip({ s }: { s: Severity }) {
  return (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-ink/30 px-2.5 text-[11px] font-semibold">
      <span className="h-2 w-2 rounded-full" style={{ background: SEVERITY[s].color }} />
      {SEVERITY[s].label}
    </span>
  );
}

function CloseBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label="Close"
      className="press grid h-9 w-9 shrink-0 place-items-center rounded-full bg-cream/5 text-cream/70 hover:bg-cream/10 hover:text-cream"
    >
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
        <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    </button>
  );
}

const byUrgency = (a: ShipReport, b: ShipReport) =>
  SEVERITY[a.severity].rank - SEVERITY[b.severity].rank ||
  (a.form?.priority ?? 5) - (b.form?.priority ?? 5) ||
  b.updated_at.localeCompare(a.updated_at);

function reportNode(r: ShipReport, caption: string, onFocus: (f: Focus) => void): MindNode {
  return {
    id: r.report_id,
    caption,
    label: r.form?.equipment ?? 'Voice report',
    tone: TONE[r.severity],
    onClick: () => onFocus({ kind: 'report', id: r.report_id }),
  };
}

function ReportFocus({ r, all, onFocus }: { r: ShipReport; all: ShipReport[]; onFocus: (f: Focus | null) => void }) {
  const navigate = useNavigate();
  const lang = r.transcript?.lang ?? r.form?.lang_original;
  const nodes: MindNode[] = [
    {
      id: 'by',
      caption: 'Reported by',
      label: `${personName(r.actor)} · ${personRole(r.actor)}`,
      tone: 'steel',
      onClick: () => onFocus({ kind: 'person', actor: r.actor }),
    },
    {
      id: 'where',
      caption: 'Located in',
      label: sectorById(r.sector).label,
      tone: 'steel',
      onClick: () => onFocus({ kind: 'sector', id: r.sector }),
    },
  ];
  if (r.form)
    nodes.push({
      id: 'eq',
      caption: `SFI ${r.form.sfi_code} · ${sfiGroup(r.form.sfi_code) ?? 'equipment'}`,
      label: r.form.equipment,
      tone: 'cream',
      onClick: () => onFocus({ kind: 'equipment', key: equipmentKey(r.form!.equipment), label: r.form!.equipment }),
    });
  if (r.sensor)
    nodes.push({
      id: 'sensor',
      caption: `Sensor ${r.sensor.tag}`,
      label: `${r.sensor.sensor_value} ${r.sensor.unit} · ${r.sensor.matches ? 'agrees with report' : 'does NOT match'}`,
      tone: r.sensor.matches ? 'ok' : 'alert',
    });
  if (lang && lang !== 'en') nodes.push({ id: 'lang', caption: 'Spoken in', label: `${LANG[lang] ?? lang} → English log`, tone: 'muted' });
  if (r.approver)
    nodes.push({
      id: 'appr',
      caption: r.status === 'rejected' ? 'Rejected by' : r.corrected ? 'Approved with corrections by' : 'Approved by',
      label: personName(r.approver),
      tone: 'steel',
      onClick: () => onFocus({ kind: 'person', actor: r.approver! }),
    });
  if (r.assignee && r.assignee !== r.actor)
    nodes.push({
      id: 'asg',
      caption: 'Assigned to',
      label: personName(r.assignee),
      tone: 'steel',
      onClick: () => onFocus({ kind: 'person', actor: r.assignee! }),
    });
  for (const rel of relatedTo(r, all, 3)) nodes.push(reportNode(rel.report, `${rel.why} · ${ago(rel.report.updated_at)}`, onFocus));

  return (
    <div className="enter flex flex-col gap-5" key={r.report_id}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <Eyebrow>
            {sectorById(r.sector).label} · {ago(r.created_at)}
          </Eyebrow>
          <h2 className="mt-1.5 text-xl font-semibold leading-tight tracking-tight">{r.form?.equipment ?? 'Voice report'}</h2>
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <SeverityChip s={r.severity} />
            <StatusBadge status={r.status} />
            {r.form && <PriorityBadge p={r.form.priority} />}
          </div>
        </div>
        <CloseBtn onClick={() => onFocus(null)} />
      </div>

      {(r.form?.text_en || r.transcript) && (
        <div className="flex flex-col gap-2">
          {r.form?.text_en && <p className="text-[15px] leading-relaxed text-cream/90">{r.form.text_en}</p>}
          {r.transcript && lang !== 'en' && (
            <p className="border-l-2 border-steel/60 pl-3 text-sm italic leading-relaxed text-cream/55">
              “{r.transcript.text}” <span className="not-italic font-mono text-[10px] uppercase text-steel">{lang}</span>
            </p>
          )}
        </div>
      )}

      <div>
        <Eyebrow className="mb-3">Connections</Eyebrow>
        <MindMap root={{ caption: 'Report', label: r.form?.equipment ?? 'Voice report' }} nodes={nodes} />
      </div>

      {AWAITING_STATUSES.includes(r.status) && (
        <Btn onClick={() => navigate(`/officer?report=${r.report_id}`)} className="w-full">
          {r.status === 'pending_approval' ? 'Review & approve' : 'Open in approvals'}
        </Btn>
      )}
    </div>
  );
}

function GroupFocus({
  focus,
  all,
  onFocus,
}: {
  focus: Exclude<Focus, { kind: 'report' }>;
  all: ShipReport[];
  onFocus: (f: Focus | null) => void;
}) {
  const list = reportsFor(focus, all).sort(byUrgency);
  const counts = (s: Severity) => list.filter((r) => r.severity === s).length;
  let caption = '';
  let title = '';
  let rel = (_r: ShipReport) => ago(_r.updated_at);
  switch (focus.kind) {
    case 'person':
      caption = personRole(focus.actor);
      title = personName(focus.actor);
      rel = (r) => `${r.actor === focus.actor ? 'reported' : r.assignee === focus.actor ? 'assigned' : 'approved'} · ${ago(r.updated_at)}`;
      break;
    case 'sector':
      caption = 'Sector';
      title = sectorById(focus.id).label;
      break;
    case 'system':
      caption = `SFI group ${focus.group}`;
      title = SFI_GROUPS[focus.group] ?? focus.group;
      break;
    case 'equipment':
      caption = 'Equipment history';
      title = focus.label.replace(/No\.?\s*\d+/i, '').trim();
      break;
    case 'severity':
      caption = 'Filter';
      title = SEVERITY[focus.value].label;
      break;
  }
  const shown = list.slice(0, 8);
  const nodes = shown.map((r) => reportNode(r, `${focus.kind === 'sector' ? '' : `${sectorById(r.sector).label} · `}${rel(r)}`, onFocus));

  return (
    <div className="enter flex flex-col gap-5" key={JSON.stringify(focus)}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <Eyebrow>{caption}</Eyebrow>
          <h2 className="mt-1.5 text-xl font-semibold capitalize leading-tight tracking-tight">{title}</h2>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {(['action', 'open', 'progress', 'resolved'] as Severity[])
              .filter((s) => counts(s))
              .map((s) => (
                <span key={s} className="inline-flex h-6 items-center gap-1.5 rounded-full bg-ink/30 px-2.5 text-[11px] font-semibold">
                  <span className="h-2 w-2 rounded-full" style={{ background: SEVERITY[s].color }} />
                  {counts(s)} {SEVERITY[s].label.toLowerCase()}
                </span>
              ))}
          </div>
        </div>
        <CloseBtn onClick={() => onFocus(null)} />
      </div>
      {nodes.length ? (
        <div>
          <Eyebrow className="mb-3">Connected reports</Eyebrow>
          <MindMap root={{ caption, label: title }} nodes={nodes} />
          {list.length > shown.length && (
            <p className="mt-3 text-center text-xs text-cream/50">+ {list.length - shown.length} older reports</p>
          )}
        </div>
      ) : (
        <p className="text-cream/55">No reports here.</p>
      )}
    </div>
  );
}

function Attention({ all, onFocus }: { all: ShipReport[]; onFocus: (f: Focus) => void }) {
  const urgent = all
    .filter((r) => r.severity === 'action' || r.severity === 'open')
    .sort(byUrgency)
    .slice(0, 7);
  return (
    <div className="enter flex flex-col gap-4" key="attention">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Needs attention</h2>
        <p className="mt-1 text-sm text-cream/55">Tap a report, pin or compartment to see what it connects to.</p>
      </div>
      {urgent.length === 0 ? (
        <div className="rounded-2xl border border-ok/30 bg-ok/10 p-4 text-sm text-ok">All clear. Nothing requires action.</div>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {urgent.map((r) => (
            <li key={r.report_id}>
              <button
                onClick={() => onFocus({ kind: 'report', id: r.report_id })}
                className="press flex w-full items-center gap-3 rounded-2xl border border-cream/10 bg-ink/20 p-3 text-left hover:border-cream/25 hover:bg-cream/5"
              >
                <span className={cx('h-9 w-1 shrink-0 rounded-full')} style={{ background: SEVERITY[r.severity].color }} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">{r.form?.equipment ?? 'Voice report'}</span>
                  <span className="block truncate text-xs text-cream/55">
                    {sectorById(r.sector).label} · {r.form?.defect ?? r.transcript?.text} · {ago(r.updated_at)}
                  </span>
                </span>
                {r.form && <PriorityBadge p={r.form.priority} />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function FocusPanel({ focus, all, onFocus }: { focus: Focus | null; all: ShipReport[]; onFocus: (f: Focus | null) => void }) {
  if (!focus) return <Attention all={all} onFocus={onFocus} />;
  if (focus.kind === 'report') {
    const r = all.find((x) => x.report_id === focus.id);
    return r ? <ReportFocus r={r} all={all} onFocus={onFocus} /> : <Attention all={all} onFocus={onFocus} />;
  }
  return <GroupFocus focus={focus} all={all} onFocus={onFocus} />;
}
