// ApiClient: real HTTP or the in-browser mock, chosen by VITE_MOCK.
// If the backend answers differently than section 6.5, adapt it here, not in types.ts.
import { config } from '../config';
import { mockServer } from './mock';
import type { ApproveRequest, HandoverResponse, ShipEvent, SyncStatus } from '../types';

export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface AudioUpload {
  report_id: string;
  actor: string;
  device: string;
  blob: Blob;
  mime: string;
}

export interface ApiClient {
  /** Idempotent per report_id. Resolves 'duplicate' on 409. */
  uploadReportAudio(u: AudioUpload): Promise<'ok' | 'duplicate'>;
  clarifyAudio(reportId: string, u: Omit<AudioUpload, 'report_id'>): Promise<void>;
  clarifyText(reportId: string, answer: string, actor: string): Promise<void>;
  approve(reportId: string, req: ApproveRequest, actor: string): Promise<void>;
  ackTask(taskId: string, actor: string): Promise<void>;
  /** Everything the server knows, as raw events, for catch-up after (re)connect. */
  loadEvents(): Promise<ShipEvent[]>;
  handover(watch?: string): Promise<HandoverResponse>;
  syncStatus(): Promise<SyncStatus>;
  setLink(up: boolean): Promise<void>;
}

const extFor = (mime: string) => (mime.includes('mp4') || mime.includes('aac') ? 'm4a' : 'webm');

async function request(path: string, init: RequestInit = {}, timeoutMs = 15000): Promise<Response> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${config.apiUrl}${path}`, { ...init, signal: ctrl.signal });
    if (!res.ok && res.status !== 409) throw new HttpError(res.status, `${res.status} ${res.statusText}`);
    return res;
  } finally {
    clearTimeout(t);
  }
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

class HttpApiClient implements ApiClient {
  async uploadReportAudio(u: AudioUpload) {
    const fd = new FormData();
    fd.append('report_id', u.report_id);
    fd.append('actor', u.actor);
    fd.append('device', u.device);
    fd.append('audio', u.blob, `${u.report_id}.${extFor(u.mime)}`);
    const res = await request('/api/reports/audio', { method: 'POST', body: fd }, 60000);
    return res.status === 409 ? 'duplicate' : 'ok';
  }

  async clarifyAudio(reportId: string, u: Omit<AudioUpload, 'report_id'>) {
    const fd = new FormData();
    fd.append('actor', u.actor);
    fd.append('device', u.device);
    fd.append('audio', u.blob, `clarify.${extFor(u.mime)}`);
    await request(`/api/reports/${reportId}/clarify`, { method: 'POST', body: fd }, 60000);
  }

  async clarifyText(reportId: string, answer: string, actor: string) {
    await request(`/api/reports/${reportId}/clarify`, json({ answer, actor }));
  }

  async approve(reportId: string, req: ApproveRequest, actor: string) {
    await request(`/api/reports/${reportId}/approve`, json({ ...req, actor }));
  }

  async ackTask(taskId: string, actor: string) {
    await request(`/api/tasks/${taskId}/ack`, json({ actor }));
  }

  async loadEvents(): Promise<ShipEvent[]> {
    const res = await request('/api/reports');
    const body = await res.json();
    const list: unknown[] = Array.isArray(body) ? body : (body?.reports ?? body?.items ?? []);
    const ids = list
      .map((r) => (r as { report_id?: string; id?: string }).report_id ?? (r as { id?: string }).id)
      .filter((x): x is string => typeof x === 'string');
    const chunks = await Promise.all(
      ids.map((id) =>
        request(`/api/reports/${id}/events`)
          .then((r) => r.json())
          .then((b) => (Array.isArray(b) ? b : (b?.events ?? [])) as ShipEvent[])
          .catch(() => [] as ShipEvent[]),
      ),
    );
    return chunks.flat();
  }

  async handover(watch?: string) {
    const q = watch ? `?watch=${encodeURIComponent(watch)}` : '';
    return (await (await request(`/api/handover${q}`, {}, 120000)).json()) as HandoverResponse;
  }

  async syncStatus() {
    return (await (await request('/api/sync/status', {}, 4000)).json()) as SyncStatus;
  }

  async setLink(up: boolean) {
    await request('/api/sync/link', json({ up }));
  }
}

class MockApiClient implements ApiClient {
  uploadReportAudio(u: AudioUpload) {
    return mockServer.uploadAudio(u.report_id, u.actor);
  }
  clarifyAudio(reportId: string) {
    return mockServer.clarify(reportId, null);
  }
  clarifyText(reportId: string, answer: string) {
    return mockServer.clarify(reportId, answer);
  }
  approve(reportId: string, req: ApproveRequest, actor: string) {
    return mockServer.approve(reportId, req, actor);
  }
  ackTask(taskId: string, actor: string) {
    return mockServer.ack(taskId, actor);
  }
  async loadEvents() {
    return mockServer.events();
  }
  handover(watch?: string) {
    return mockServer.handover(watch);
  }
  syncStatus() {
    return mockServer.syncStatus();
  }
  setLink(up: boolean) {
    return mockServer.setLink(up);
  }
}

export const api: ApiClient = config.mock ? new MockApiClient() : new HttpApiClient();
