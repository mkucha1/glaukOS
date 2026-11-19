// Single source of truth: every event from MQTT, REST or the cache lands here, deduped by event_id.
import { useMemo, useSyncExternalStore } from 'react';
import { db } from './db';
import type {
  ApprovedPayload,
  ClarificationRequestedPayload,
  ReportForm,
  ReportStatus,
  SensorCheckedPayload,
  ShipEvent,
  TaskAssignedPayload,
  TranscribedPayload,
} from '../types';

const byId = new Map<string, ShipEvent>();
let snapshot: ShipEvent[] = [];
const listeners = new Set<() => void>();

function isShipEvent(x: unknown): x is ShipEvent {
  const e = x as ShipEvent;
  return !!e && typeof e.event_id === 'string' && typeof e.type === 'string' && typeof e.ts === 'string';
}

export function ingest(input: unknown | unknown[], opts: { persist?: boolean } = {}) {
  const list = Array.isArray(input) ? input : [input];
  const added: ShipEvent[] = [];
  for (const e of list) {
    if (!isShipEvent(e) || byId.has(e.event_id)) continue;
    byId.set(e.event_id, e);
    added.push(e);
  }
  if (!added.length) return;
  // Array.sort is stable, so same-ms events keep arrival order.
  snapshot = [...byId.values()].sort((a, b) => a.ts.localeCompare(b.ts));
  listeners.forEach((l) => l());
  if (opts.persist !== false) db.events.bulkPut(added).catch(console.error);
}

export async function loadCachedEvents() {
  ingest(await db.events.toArray(), { persist: false });
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export const useEvents = () => useSyncExternalStore(subscribe, () => snapshot);

// ---------- derived report view ----------

export interface ReportView {
  report_id: string;
  actor: string;
  created_at: string;
  updated_at: string;
  status: ReportStatus;
  events: ShipEvent[];
  form?: ReportForm;
  transcript?: TranscribedPayload;
  sensor?: SensorCheckedPayload;
  /** Set only while status is needs_clarification. */
  clarification?: ClarificationRequestedPayload & { event_id: string };
  task?: TaskAssignedPayload;
  assignee?: string;
  /** Form as last proposed by the LLM, before any officer edits. */
  aiForm?: ReportForm;
  approver?: string;
  approved_at?: string;
  closed_at?: string;
}

const DONE: ReportStatus[] = ['approved', 'rejected', 'assigned', 'acknowledged', 'closed'];

export function buildReport(report_id: string, events: ShipEvent[]): ReportView {
  const recorded = events.find((e) => e.type === 'report.recorded');
  const v: ReportView = {
    report_id,
    actor: (recorded ?? events[0]).actor,
    created_at: events[0].ts,
    updated_at: events[events.length - 1].ts,
    status: 'recorded',
    events,
  };
  let lastQuestion: ReportView['clarification'];

  for (const e of events) {
    switch (e.type) {
      case 'report.recorded':
        v.status = 'recorded';
        break;
      case 'report.transcribed':
        v.transcript = e.payload as TranscribedPayload;
        if (!DONE.includes(v.status)) v.status = 'transcribed';
        break;
      case 'report.structured': {
        v.form = e.payload as ReportForm;
        v.aiForm = v.form;
        if (!DONE.includes(v.status))
          v.status = v.form.missing_fields?.length ? 'structured' : 'pending_approval';
        break;
      }
      case 'report.clarification_requested':
        lastQuestion = { ...(e.payload as ClarificationRequestedPayload), event_id: e.event_id };
        if (!DONE.includes(v.status)) v.status = 'needs_clarification';
        break;
      case 'report.clarified':
        if (!DONE.includes(v.status)) v.status = 'clarified';
        break;
      case 'report.sensor_checked':
        v.sensor = e.payload as SensorCheckedPayload;
        if (!DONE.includes(v.status)) v.status = 'pending_approval';
        break;
      case 'report.approved': {
        const p = e.payload as ApprovedPayload;
        if (p?.form) v.form = p.form;
        v.assignee = p?.assignee;
        v.approver = e.actor;
        v.approved_at = e.ts;
        v.status = 'approved';
        break;
      }
      case 'report.rejected':
        v.approver = e.actor;
        v.status = 'rejected';
        break;
      case 'task.assigned':
        v.task = e.payload as TaskAssignedPayload;
        v.assignee = v.task.assignee;
        v.status = 'assigned';
        break;
      case 'task.acknowledged':
        v.status = 'acknowledged';
        break;
      case 'task.closed':
        v.closed_at = e.ts;
        v.status = 'closed';
        break;
      default:
        break;
    }
  }
  if (v.status === 'needs_clarification') v.clarification = lastQuestion;
  return v;
}

export function buildReports(events: ShipEvent[]): ReportView[] {
  const groups = new Map<string, ShipEvent[]>();
  for (const e of events) {
    if (!e.report_id) continue;
    const g = groups.get(e.report_id);
    if (g) g.push(e);
    else groups.set(e.report_id, [e]);
  }
  return [...groups.entries()]
    .map(([id, evts]) => buildReport(id, evts))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function useReports(): ReportView[] {
  const events = useEvents();
  return useMemo(() => buildReports(events), [events]);
}

export const AWAITING: ReportStatus[] = [
  'transcribed',
  'structured',
  'needs_clarification',
  'clarified',
  'pending_approval',
];
