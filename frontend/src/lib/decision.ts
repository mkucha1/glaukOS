// Model decision attached by the ship worker (backend/decision, Basal) to report.structured.
// It travels as an extra `decision` field next to ReportForm, so the shared contract in types.ts stays as it is.
import type { ReportForm } from '../types';

export interface ModelDecision {
  model: string; // "basal"
  department: 'engine' | 'deck' | 'catering';
  approver_position: string; // who approves that department
  position: string; // suggested position to do the work, e.g. "2nd_engineer"
  assignee: string | null; // actor of someone in that position (on duty first), e.g. "2nd_engineer:mateusz"
  dpa_report: boolean; // accident / near miss to report to the DPA
  needs_officer: boolean; // some decision below its confidence threshold
  needs_review: string[]; // which decisions were unsure
  sector?: string;
  confidences: Record<string, number>;
  answers: Record<string, string>;
  timings_s?: Record<string, number>;
}

export const decisionOf = (form?: ReportForm): ModelDecision | undefined =>
  (form as (ReportForm & { decision?: ModelDecision }) | undefined)?.decision;

export const DECISION_LABELS: Record<string, string> = {
  dzial: 'Department',
  pilnosc: 'Priority',
  raport_dpa: 'DPA report',
  sektor: 'Location',
  osoba: 'Assignee',
};
