// Shared team contracts (CLAUDE.md section 6). Do not change without team agreement.
// If the backend answers differently, adapt src/lib/api.ts, not these types.

export type EventType =
  | 'report.recorded'
  | 'report.transcribed'
  | 'report.structured'
  | 'report.clarification_requested'
  | 'report.clarification_answered' // proposed: crew answer (text or audio); backend then emits report.clarified
  | 'report.clarified'
  | 'report.sensor_checked'
  | 'report.approved'
  | 'report.rejected'
  | 'task.assigned'
  | 'task.acknowledged'
  | 'task.closed'
  | 'watch.handover_generated'
  | 'sync.sent';

export interface ShipEvent<P = unknown> {
  event_id: string; // UUID
  ts: string; // ISO 8601 UTC
  report_id?: string; // UUID, links the events of one report
  type: EventType;
  actor: string; // e.g. "2nd_engineer:mateusz"
  device?: string;
  payload: P;
  synced_at?: string | null;
}

export interface ReportForm {
  equipment: string;
  sfi_code: string;
  parameter?: string;
  value?: number;
  unit?: string;
  defect?: string;
  priority: 1 | 2 | 3 | 4 | 5;
  location?: string;
  action_taken?: string;
  text_en: string;
  lang_original: string;
  missing_fields: string[];
  confidence: number; // 0–1
}

export interface TranscribedPayload {
  text: string;
  lang: string;
}

export interface ClarificationRequestedPayload {
  question: string;
  options?: string[];
}

export interface SensorCheckedPayload {
  tag: string;
  sensor_value: number;
  unit: string;
  matches: boolean;
}

export interface ApprovedPayload {
  form: ReportForm;
  assignee: string;
}

/** report.recorded as written by the app: where the audio is and where the reporter stands. */
export interface RecordedPayload {
  audio_path?: string; // Supabase Storage path in bucket "recordings"
  mime?: string;
  station?: string;
}

/** report.clarification_answered: one of answer (button) or audio_path (voice). */
export interface ClarificationAnsweredPayload {
  answer?: string;
  audio_path?: string;
  mime?: string;
}

export interface TaskAssignedPayload {
  assignee: string;
  summary: string;
  priority: number;
}

/** Derived on the frontend from the latest event; `queued` = only in local IndexedDB. */
export type ReportStatus =
  | 'queued'
  | 'recorded'
  | 'transcribed'
  | 'structured'
  | 'needs_clarification'
  | 'clarified'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'assigned'
  | 'acknowledged'
  | 'closed';

export interface ApproveRequest {
  decision: 'approve' | 'reject';
  form?: ReportForm;
  assignee?: string;
}

export interface HandoverResponse {
  text: string;
  generated_at: string;
}

export interface SyncStatus {
  link_up: boolean;
  queued: number;
  last_sent_at?: string;
}
