// ApiClient on Supabase: anonymous auth, events table (the register), Storage for audio, RPCs.
// Row-level security in supabase/migrations decides who may read and write what.
import { config, nowIso, uuid } from '../config';
import type { ApiClient, AudioUpload } from './api';
import type { CrewMember } from './crew';
import { HttpError } from './errors';
import { localHandover, watchWindow, type Briefing } from './handover';
import { actorOf, type Profile } from './profile';
import { ensureSession, requireSupabase } from './supabase';
import type { ApproveRequest, HandoverResponse, ShipEvent, SyncStatus } from '../types';

const BUCKET = 'recordings';
const ext = (mime: string) => (mime.includes('mp4') || mime.includes('aac') ? 'm4a' : 'webm');
const baseMime = (mime: string) => mime.split(';')[0].trim() || 'audio/webm';

interface SbError {
  message: string;
  code?: string;
  status?: number | string;
  statusCode?: number | string;
}

/** 4xx means "the server said no" (permanent for the outbox); anything else is worth retrying. */
function fail(error: SbError, status?: number): never {
  const s = Number(status ?? error.status ?? error.statusCode ?? 0);
  if (error.code === '42501') throw new HttpError(403, error.message);
  if (s >= 400 && s < 500) throw new HttpError(s, error.message);
  throw new Error(error.message || 'Network error');
}

const isDuplicate = (e: SbError) => String(e.statusCode ?? e.status) === '409' || /exists|duplicate/i.test(e.message);

export class SupabaseApiClient implements ApiClient {
  private async uid() {
    return (await ensureSession()).user.id;
  }

  private async upload(path: string, blob: Blob, mime: string) {
    const { error } = await requireSupabase()
      .storage.from(BUCKET)
      .upload(path, blob, { contentType: baseMime(mime), upsert: false });
    if (error && !isDuplicate(error as SbError)) fail(error as SbError);
  }

  private async insert(rows: Partial<ShipEvent>[]) {
    const { error, status } = await requireSupabase().from('events').upsert(rows, { onConflict: 'event_id', ignoreDuplicates: true });
    if (error) fail(error, status);
  }

  /** Scripted stand-in for speech + LLM; a no-op once the real backend sets ship_status.autopilot = false. */
  private autopilot(reportId: string, answer?: string) {
    void requireSupabase()
      .rpc('demo_autopilot', { p_report_id: reportId, p_answer: answer ?? null })
      .then(({ error }) => error && console.warn('[autopilot]', error.message));
  }

  async uploadReportAudio(u: AudioUpload): Promise<'ok' | 'duplicate'> {
    const path = `${await this.uid()}/${u.report_id}.${ext(u.mime)}`;
    await this.upload(path, u.blob, u.mime);
    // event_id = report_id: a re-send hits the primary key and is ignored, never duplicated.
    await this.insert([
      {
        event_id: u.report_id,
        report_id: u.report_id,
        ts: u.recorded_at ?? nowIso(),
        type: 'report.recorded',
        actor: u.actor,
        device: u.device,
        payload: { audio_path: path, mime: u.mime, station: u.station },
      },
    ]);
    this.autopilot(u.report_id);
    return 'ok';
  }

  async clarifyAudio(reportId: string, id: string, u: Omit<AudioUpload, 'report_id'>) {
    const path = `${await this.uid()}/${reportId}-answer-${id}.${ext(u.mime)}`;
    await this.upload(path, u.blob, u.mime);
    await this.insert([
      {
        event_id: id,
        report_id: reportId,
        type: 'report.clarification_answered',
        actor: u.actor,
        device: u.device,
        payload: { audio_path: path, mime: u.mime },
      },
    ]);
    this.autopilot(reportId, 'dwa');
  }

  async clarifyText(reportId: string, answer: string, actor: string, id: string) {
    await this.uid();
    await this.insert([{ event_id: id, report_id: reportId, type: 'report.clarification_answered', actor, payload: { answer } }]);
    this.autopilot(reportId, answer);
  }

  async approve(reportId: string, req: ApproveRequest, actor: string) {
    await this.uid();
    if (req.decision === 'reject') {
      await this.insert([{ event_id: uuid(), report_id: reportId, type: 'report.rejected', actor, payload: {} }]);
      return;
    }
    const form = req.form!;
    const assignee = req.assignee!;
    const now = Date.now();
    await this.insert([
      {
        event_id: uuid(),
        report_id: reportId,
        ts: new Date(now).toISOString(),
        type: 'report.approved',
        actor,
        payload: { form, assignee },
      },
      {
        event_id: uuid(),
        report_id: reportId,
        ts: new Date(now + 1).toISOString(),
        type: 'task.assigned',
        actor,
        payload: { assignee, summary: `${form.equipment}: ${form.defect ?? form.text_en}`, priority: form.priority },
      },
    ]);
  }

  async ackTask(taskId: string, actor: string) {
    await this.uid();
    await this.insert([{ event_id: uuid(), report_id: taskId, type: 'task.acknowledged', actor, payload: {} }]);
  }

  async loadEvents(): Promise<ShipEvent[]> {
    const { data, error, status } = await requireSupabase().from('events').select('*').order('ts', { ascending: true }).limit(5000);
    if (error) fail(error, status);
    return (data ?? []) as ShipEvent[];
  }

  async handover(watch = '00-04'): Promise<HandoverResponse> {
    // Daniel's LLM briefing service if configured, otherwise a briefing built from the register.
    if (config.apiUrl) {
      try {
        const res = await fetch(`${config.apiUrl}/api/handover?watch=${encodeURIComponent(watch)}`);
        if (res.ok) return (await res.json()) as HandoverResponse;
      } catch {
        /* fall through to the local briefing */
      }
    }
    try {
      const written = await this.workerBriefing(watch);
      if (written) return written;
    } catch {
      /* fall through to the local briefing */
    }
    return localHandover(watch);
  }

  /** Briefing written by the ship worker's LLM (qwen), if the worker is alive. See supabase/migrations/*briefings.sql. */
  private async workerBriefing(watch: string): Promise<Briefing | null> {
    const sb = requireSupabase();
    await ensureSession();
    const { data: ws, error } = await sb.from('worker_status').select('last_seen').eq('id', 1).maybeSingle();
    if (error || !ws?.last_seen || Date.now() - new Date(ws.last_seen).getTime() > 90_000) return null;
    const id = uuid();
    const [window_from, window_to] = watchWindow(watch);
    const { error: insertError } = await sb.from('briefings').insert({ id, watch, window_from, window_to, lang: 'en' });
    if (insertError) return null;
    for (const deadline = Date.now() + 90_000; Date.now() < deadline; ) {
      await new Promise((r) => setTimeout(r, 1500));
      const { data } = await sb.from('briefings').select('status,text,model,generated_at').eq('id', id).maybeSingle();
      if (data?.status === 'done' && data.text)
        return { text: data.text, generated_at: data.generated_at ?? nowIso(), source: data.model ?? 'llm' };
      if (data?.status === 'failed') return null;
    }
    return null;
  }

  async syncStatus(): Promise<SyncStatus> {
    const { data, error, status } = await requireSupabase().rpc('sync_status');
    if (error) fail(error, status);
    return data as SyncStatus;
  }

  async setLink(up: boolean) {
    const { error, status } = await requireSupabase().rpc('set_link', { p_up: up });
    if (error) fail(error, status);
  }

  async signIn(p: Profile) {
    const id = await this.uid();
    const { error, status } = await requireSupabase()
      .from('crew')
      .upsert({ id, name: p.name, position: p.position, actor: actorOf(p), station: p.station }, { onConflict: 'id' });
    if (error) fail(error, status);
  }

  async signOut() {
    await requireSupabase().auth.signOut();
  }

  async setOnDuty(on: boolean) {
    const id = await this.uid();
    const { error, status } = await requireSupabase().from('crew').update({ on_duty: on }).eq('id', id);
    if (error) fail(error, status);
  }

  async loadCrew(): Promise<CrewMember[]> {
    const { data, error, status } = await requireSupabase().from('crew').select('*').order('name');
    if (error) fail(error, status);
    return (data ?? []) as CrewMember[];
  }
}
