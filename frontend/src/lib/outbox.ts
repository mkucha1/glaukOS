// Offline-first outbox: every recording is written to IndexedDB first, then sent.
// Re-sending the same report_id is safe: the server answers 200 or 409 and never duplicates.
import { db, type OutboxItem } from './db';
import { api, HttpError } from './api';
import { bus } from './mqtt';
import { nowIso } from '../config';

const MAX_BACKOFF = 30_000;
let running = false;
let again = false;

export type NewOutboxItem = Omit<OutboxItem, 'status' | 'attempts' | 'created_at'>;

export async function enqueue(item: NewOutboxItem) {
  await db.outbox.put({ ...item, created_at: nowIso(), status: 'pending', attempts: 0 });
  void kick();
}

async function send(item: OutboxItem) {
  switch (item.kind) {
    case 'report_audio':
      await api.uploadReportAudio(item);
      return;
    case 'clarify_audio':
      await api.clarifyAudio(item.target_report_id!, item);
      return;
    case 'clarify_text': {
      const { answer } = JSON.parse(await item.blob.text()) as { answer: string };
      await api.clarifyText(item.target_report_id!, answer, item.actor);
      return;
    }
  }
}

async function processOnce() {
  const now = Date.now();
  const due = (await db.outbox.where('status').equals('pending').sortBy('created_at')).filter(
    (i) => !i.next_attempt_at || i.next_attempt_at <= now,
  );
  for (const item of due) {
    await db.outbox.update(item.report_id, { status: 'sending' });
    try {
      await send(item);
      await db.outbox.update(item.report_id, { status: 'sent', last_error: undefined });
    } catch (err) {
      const permanent = err instanceof HttpError && err.status >= 400 && err.status < 500 && ![408, 429].includes(err.status);
      const attempts = item.attempts + 1;
      await db.outbox.update(item.report_id, {
        status: permanent ? 'failed' : 'pending',
        attempts,
        next_attempt_at: Date.now() + Math.min(MAX_BACKOFF, 1000 * 2 ** attempts),
        last_error: String((err as Error)?.message ?? err),
      });
      if (!permanent) break; // network is down: don't hammer the rest of the queue
    }
  }
}

export async function kick() {
  if (running) {
    again = true;
    return;
  }
  running = true;
  try {
    do {
      again = false;
      await processOnce();
    } while (again);
  } catch (err) {
    console.error('[outbox]', err);
  } finally {
    running = false;
  }
}

/** Connectivity came back: skip the backoff and try right away. */
async function resetBackoff() {
  await db.outbox.where('status').equals('pending').modify({ next_attempt_at: 0 });
  void kick();
}

export async function retryFailed(report_id: string) {
  await db.outbox.update(report_id, { status: 'pending', next_attempt_at: 0 });
  void kick();
}

let started = false;
export async function startOutbox() {
  if (started) return;
  started = true;
  // Anything stuck in "sending" was interrupted by a reload or crash.
  await db.outbox.where('status').equals('sending').modify({ status: 'pending' });
  window.addEventListener('online', () => void resetBackoff());
  bus.onState((s) => s === 'connected' && void resetBackoff());
  setInterval(() => void kick(), 5000);
  void kick();
}
