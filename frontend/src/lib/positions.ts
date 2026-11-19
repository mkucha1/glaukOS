// Ranks on board. Mirrors public.positions in supabase/migrations (keep both in sync).
// The database enforces these rules with RLS; the UI uses them only to hide what you cannot do.
import type { SectorId } from './ship';
import { translate } from './i18n';

export type Department = 'command' | 'deck' | 'engine' | 'catering';

export type PositionId =
  | 'captain'
  | 'chief_officer'
  | 'chief_engineer'
  | '2nd_officer'
  | '2nd_engineer'
  | '3rd_officer'
  | '3rd_engineer'
  | 'electrician'
  | 'bosun'
  | 'chief_cook'
  | 'ab'
  | 'oiler'
  | 'motorman'
  | 'messman';

export interface Position {
  id: PositionId;
  label: string;
  department: Department;
  rank: number;
  /** departments whose reports this position may approve */
  approves: Department[];
  station: SectorId;
}

export const POSITIONS: Position[] = [
  {
    id: 'captain',
    label: 'Captain',
    department: 'command',
    rank: 1,
    approves: ['command', 'deck', 'engine', 'catering'],
    station: 'bridge',
  },
  { id: 'chief_officer', label: 'Chief Officer', department: 'deck', rank: 2, approves: ['deck', 'catering'], station: 'bridge' },
  { id: 'chief_engineer', label: 'Chief Engineer', department: 'engine', rank: 2, approves: ['engine'], station: 'ecr' },
  { id: '2nd_officer', label: '2nd Officer', department: 'deck', rank: 3, approves: [], station: 'bridge' },
  { id: '2nd_engineer', label: '2nd Engineer', department: 'engine', rank: 3, approves: [], station: 'engine' },
  { id: '3rd_officer', label: '3rd Officer', department: 'deck', rank: 4, approves: [], station: 'bridge' },
  { id: '3rd_engineer', label: '3rd Engineer', department: 'engine', rank: 4, approves: [], station: 'engine' },
  { id: 'electrician', label: 'Electro-Technical Officer', department: 'engine', rank: 4, approves: [], station: 'ecr' },
  { id: 'bosun', label: 'Bosun', department: 'deck', rank: 5, approves: [], station: 'deck' },
  { id: 'chief_cook', label: 'Chief Cook', department: 'catering', rank: 5, approves: [], station: 'galley' },
  { id: 'ab', label: 'Able Seaman', department: 'deck', rank: 6, approves: [], station: 'deck' },
  { id: 'oiler', label: 'Oiler', department: 'engine', rank: 6, approves: [], station: 'engine' },
  { id: 'motorman', label: 'Motorman', department: 'engine', rank: 6, approves: [], station: 'engine' },
  { id: 'messman', label: 'Messman', department: 'catering', rank: 7, approves: [], station: 'galley' },
];

export const DEPARTMENTS: { id: Department; label: string }[] = [
  { id: 'command', label: 'Command' },
  { id: 'deck', label: 'Deck' },
  { id: 'engine', label: 'Engine' },
  { id: 'catering', label: 'Catering' },
];

export const positionById = (id?: string) => POSITIONS.find((p) => p.id === id);
export const positionLabel = (id?: string) => {
  const p = positionById(id);
  return p ? translate(p.label) : (id ?? '').replace(/_/g, ' ');
};

/** Department of an actor string like "2nd_engineer:mateusz"; unknown positions count as command. */
export const departmentOfActor = (actor?: string): Department => positionById(actor?.split(':')[0])?.department ?? 'command';

export const canApproveDept = (position: string | undefined, dept: Department) => !!positionById(position)?.approves.includes(dept);
export const isApprover = (position?: string) => (positionById(position)?.approves.length ?? 0) > 0;

/** Same department, a department you approve, or a report assigned to you. Mirrors public.can_read(). */
export function canSeeReport(position: string | undefined, me: string, r: { actor: string; assignee?: string }) {
  const pos = positionById(position);
  if (!pos) return false;
  const dept = departmentOfActor(r.actor);
  return dept === pos.department || pos.approves.includes(dept) || r.assignee === me;
}
