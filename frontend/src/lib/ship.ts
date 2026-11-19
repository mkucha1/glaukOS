// Ship model for the overview: sectors of the cross-section, where each report belongs,
// how urgent it is, and how reports connect to each other (the "brain").
import type { ReportView } from './store';
import type { ReportStatus } from '../types';
import { translate } from './i18n';

/** viewBox: x from VIEW_X0, so labels fit left of the stern. */
export const VIEW_X0 = -40;
export const VIEW_W = 1240;
export const VIEW_H = 460;

export type SectorId = 'bridge' | 'cabins' | 'galley' | 'purifier' | 'ecr' | 'engine' | 'steering' | 'deck' | 'holds' | 'bow' | 'tanks';

export interface Sector {
  id: SectorId;
  label: string;
  d: string;
  /** Where pins may be placed: x, y, w, h in view units. */
  area: [number, number, number, number];
  labelAt: [number, number];
}

const rect = (x1: number, y1: number, x2: number, y2: number) => `M${x1} ${y1}H${x2}V${y2}H${x1}Z`;

/** Drawn back to front: later sectors sit on top and win the click. */
export const SECTORS: Sector[] = [
  { id: 'engine', label: 'Engine room', d: rect(96, 202, 372, 372), area: [116, 296, 236, 62], labelAt: [104, 280] },
  { id: 'holds', label: 'Cargo holds', d: rect(380, 204, 1032, 370), area: [404, 250, 604, 104], labelAt: [392, 222] },
  { id: 'deck', label: 'Main deck', d: rect(380, 132, 1032, 200), area: [420, 176, 580, 10], labelAt: [392, 126] },
  {
    id: 'bow',
    label: 'Bow & mooring',
    d: 'M1036 182H1149C1157 232 1146 300 1108 364H1036Z',
    area: [1052, 222, 60, 100],
    labelAt: [1040, 170],
  },
  {
    id: 'tanks',
    label: 'Ballast & tanks',
    d: 'M152 372H1086C1078 384 1070 392 1060 396H160C156 390 154 380 152 372Z',
    area: [430, 390, 540, 2],
    labelAt: [170, 420],
  },
  { id: 'steering', label: 'Steering', d: rect(52, 214, 94, 300), area: [62, 250, 20, 40], labelAt: [42, 262] },
  { id: 'purifier', label: 'Purifiers', d: rect(102, 208, 186, 258), area: [120, 236, 50, 8], labelAt: [108, 252] },
  { id: 'ecr', label: 'ECR', d: rect(282, 208, 366, 258), area: [300, 236, 48, 8], labelAt: [288, 252] },
  { id: 'galley', label: 'Galley & mess', d: rect(126, 144, 330, 200), area: [150, 178, 160, 12], labelAt: [118, 176] },
  { id: 'cabins', label: 'Cabins', d: rect(126, 76, 330, 144), area: [150, 104, 160, 30], labelAt: [118, 112] },
  { id: 'bridge', label: 'Bridge', d: rect(110, 40, 346, 76), area: [160, 66, 150, 2], labelAt: [104, 62] },
];

export const sectorById = (id: SectorId) => SECTORS.find((s) => s.id === id)!;
/** Compartment name in the interface language. */
export const sectorLabel = (id: SectorId) => translate(sectorById(id).label);

// ---------- report → sector ----------

const RULES: [SectorId, RegExp][] = [
  ['purifier', /purifier|separator/],
  ['ecr', /\becr\b|control room|switchboard|alarm panel/],
  ['steering', /steering|rudder/],
  ['bridge', /bridge|wheelhouse|radar|ecdis|gyro|vhf|navigation|autopilot/],
  ['galley', /galley|cold room|provision|mess\b|pantry/],
  ['cabins', /cabin|accommodation|hvac|ac unit|air condition/],
  ['bow', /\bbow\b|forecastle|windlass|anchor|forepeak/],
  ['deck', /crane|hatch|davit|lifeboat|boat deck|main deck|mooring/],
  ['holds', /\bhold\b|cargo/],
  ['tanks', /ballast|double bottom|\btank\b/],
  ['engine', /engine|generator|aux|boiler|compressor|pump|bilge/],
];

export function sectorOf(r: ReportView): SectorId {
  // Before the LLM fills the form, the pin goes where the reporter works.
  if (!r.form && r.station && SECTORS.some((s) => s.id === r.station)) return r.station as SectorId;
  const text = `${r.form?.location ?? ''} ${r.form?.equipment ?? ''}`.toLowerCase();
  for (const [id, re] of RULES) if (re.test(text)) return id;
  switch (r.form?.sfi_code?.[0]) {
    case '4':
      return 'bridge';
    case '5':
      return 'cabins';
    case '3':
      return 'holds';
    case '2':
      return 'tanks';
    default:
      return 'engine';
  }
}

// ---------- severity ----------

export type Severity = 'action' | 'open' | 'progress' | 'resolved' | 'rejected';

export const SEVERITY: Record<Severity, { label: string; color: string; rank: number }> = {
  action: { label: 'Action required', color: 'var(--color-alert)', rank: 0 },
  open: { label: 'Open', color: 'var(--color-warn)', rank: 1 },
  progress: { label: 'In progress', color: 'var(--color-steel)', rank: 2 },
  resolved: { label: 'Resolved', color: 'var(--color-ok)', rank: 3 },
  rejected: { label: 'Rejected', color: 'color-mix(in srgb, var(--color-cream) 45%, transparent)', rank: 4 },
};

const OPEN: ReportStatus[] = [
  'queued',
  'recorded',
  'transcribed',
  'structured',
  'needs_clarification',
  'clarified',
  'pending_approval',
  'approved',
  'assigned',
];

export function severityOf(r: ReportView): Severity {
  if (r.status === 'rejected') return 'rejected';
  if (r.status === 'closed') return 'resolved';
  if (r.status === 'acknowledged') return 'progress';
  if (OPEN.includes(r.status) && ((r.form?.priority ?? 3) <= 2 || r.sensor?.matches === false)) return 'action';
  return 'open';
}

export const APPROVED: ReportStatus[] = ['approved', 'assigned', 'acknowledged', 'closed'];

/** Officer changed what the LLM proposed. */
export function wasCorrected(r: ReportView) {
  const a = r.aiForm;
  const b = r.form;
  if (!a || !b || a === b) return false;
  return (['equipment', 'priority', 'value', 'defect', 'text_en', 'sfi_code'] as const).some((k) => a[k] !== b[k]);
}

/** "Reported correctly": approved as the AI structured it, and sensors (if any) agree. */
export const isCorrect = (r: ReportView) => APPROVED.includes(r.status) && r.sensor?.matches !== false && !wasCorrected(r);

// ---------- SFI ----------

export const SFI_GROUPS: Record<string, string> = {
  '1': 'Ship general',
  '2': 'Hull',
  '3': 'Cargo equipment',
  '4': 'Ship equipment',
  '5': 'Crew & accommodation',
  '6': 'Machinery main components',
  '7': 'Systems for machinery',
  '8': 'Ship common systems',
};

export const sfiGroup = (code?: string) => (code ? SFI_GROUPS[code[0]] : undefined);

// ---------- enriched model ----------

export interface ShipReport extends ReportView {
  sector: SectorId;
  severity: Severity;
  correct: boolean;
  corrected: boolean;
}

export function enrich(reports: ReportView[]): ShipReport[] {
  return reports
    .filter((r) => r.form || r.transcript || r.station)
    .map((r) => ({ ...r, sector: sectorOf(r), severity: severityOf(r), correct: isCorrect(r), corrected: wasCorrected(r) }));
}

export const equipmentKey = (s?: string) =>
  (s ?? '')
    .toLowerCase()
    .replace(/no\.?\s*\d+|\d+[a-z]?|[,.()]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

/** Reports that share equipment, SFI system or sector, strongest link first. */
export function relatedTo(r: ShipReport, all: ShipReport[], limit = 4) {
  const eq = equipmentKey(r.form?.equipment);
  const sfi = r.form?.sfi_code ?? '';
  return all
    .filter((o) => o.report_id !== r.report_id)
    .map((o) => {
      let score = 0;
      let why = '';
      if (eq && equipmentKey(o.form?.equipment) === eq) [score, why] = [4, 'same equipment'];
      else if (sfi && o.form?.sfi_code === sfi) [score, why] = [3, `SFI ${sfi}`];
      else if (sfi.length >= 2 && o.form?.sfi_code?.slice(0, 2) === sfi.slice(0, 2)) [score, why] = [2, `SFI ${sfi.slice(0, 2)}x`];
      else if (o.sector === r.sector && o.severity !== 'resolved' && o.severity !== 'rejected') [score, why] = [1, 'same sector'];
      return { report: o, score, why };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || b.report.updated_at.localeCompare(a.report.updated_at))
    .slice(0, limit);
}

// ---------- focus: what the user is looking at ----------

export type Focus =
  | { kind: 'report'; id: string }
  | { kind: 'person'; actor: string }
  | { kind: 'sector'; id: SectorId }
  | { kind: 'system'; group: string }
  | { kind: 'equipment'; key: string; label: string }
  | { kind: 'severity'; value: Severity };

export function reportsFor(f: Focus, all: ShipReport[]): ShipReport[] {
  switch (f.kind) {
    case 'report':
      return all.filter((r) => r.report_id === f.id);
    case 'person':
      return all.filter((r) => r.actor === f.actor || r.assignee === f.actor || r.approver === f.actor);
    case 'sector':
      return all.filter((r) => r.sector === f.id);
    case 'system':
      return all.filter((r) => r.form?.sfi_code?.[0] === f.group);
    case 'equipment':
      return all.filter((r) => equipmentKey(r.form?.equipment) === f.key);
    case 'severity':
      return all.filter((r) => r.severity === f.value);
  }
}

export const sameFocus = (a: Focus | null, b: Focus | null) => JSON.stringify(a) === JSON.stringify(b);

// ---------- people ----------

export const personName = (actor?: string) => {
  if (!actor) return '';
  const name = actor.split(':')[1] ?? actor;
  return name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, ' ');
};
export const personRole = (actor?: string) => {
  const id = actor?.split(':')[0] ?? '';
  const label = POSITION_LABELS[id];
  return label ? translate(label) : id.replace(/_/g, ' ');
};

const POSITION_LABELS: Record<string, string> = {
  captain: 'Captain',
  chief_officer: 'Chief Officer',
  chief_engineer: 'Chief Engineer',
  '2nd_officer': '2nd Officer',
  '2nd_engineer': '2nd Engineer',
  '3rd_officer': '3rd Officer',
  '3rd_engineer': '3rd Engineer',
  electrician: 'Electro-Technical Officer',
  bosun: 'Bosun',
  chief_cook: 'Chief Cook',
  ab: 'Able Seaman',
  oiler: 'Oiler',
  motorman: 'Motorman',
  messman: 'Messman',
};

export function ago(iso: string, now = Date.now()) {
  const m = Math.round((now - new Date(iso).getTime()) / 60000);
  if (m < 1) return translate('just now');
  if (m < 60) return translate('{n} min ago', { n: m });
  const h = Math.floor(m / 60);
  return h < 24 ? translate('{n} h ago', { n: h }) : translate('{n} d ago', { n: Math.floor(h / 24) });
}

// ---------- metrics ----------

export function metrics(all: ShipReport[]) {
  const count = (pred: (r: ShipReport) => boolean) => all.filter(pred).length;
  const checked = all.filter((r) => r.sensor);
  const toApproval = all
    .filter((r) => r.approved_at)
    .map((r) => (new Date(r.approved_at!).getTime() - new Date(r.created_at).getTime()) / 60000)
    .sort((a, b) => a - b);
  const langs = new Map<string, number>();
  for (const r of all) {
    const l = r.transcript?.lang ?? r.form?.lang_original;
    if (l) langs.set(l, (langs.get(l) ?? 0) + 1);
  }
  return {
    total: all.length,
    correct: count((r) => r.correct),
    corrected: count((r) => APPROVED.includes(r.status) && r.corrected),
    mismatch: count((r) => r.sensor?.matches === false),
    action: count((r) => r.severity === 'action'),
    open: count((r) => r.severity === 'open'),
    progress: count((r) => r.severity === 'progress'),
    rejected: count((r) => r.severity === 'rejected'),
    awaiting: count((r) => r.status === 'pending_approval'),
    questions: count((r) => r.status === 'needs_clarification'),
    sensorChecked: checked.length,
    sensorAgree: checked.filter((r) => r.sensor!.matches).length,
    medianApprovalMin: toApproval.length ? toApproval[Math.floor(toApproval.length / 2)] : null,
    langs: [...langs.entries()].sort((a, b) => b[1] - a[1]),
  };
}

/** Statuses where an officer can still decide. */
export const AWAITING_STATUSES: ReportStatus[] = ['transcribed', 'structured', 'needs_clarification', 'clarified', 'pending_approval'];
