import { useEffect, useMemo, useRef, useState } from 'react';
import { Btn, Card, PriorityBadge, StatusBadge, cx, timeOf } from '../../components/ui';
import { uuid } from '../../config';
import { api } from '../../lib/api';
import { db, type OutboxItem } from '../../lib/db';
import { useLiveQuery } from '../../lib/hooks';
import { enqueue, retryFailed } from '../../lib/outbox';
import { actorOf, deviceId, useProfile } from '../../lib/profile';
import type { Recording } from '../../lib/recorder';
import { speak, speechSupported, toBcp47 } from '../../lib/speech';
import { useReports, type ReportView } from '../../lib/store';
import type { ReportStatus } from '../../types';
import { PushToTalk } from './PushToTalk';

interface Row {
  report_id: string;
  created_at: string;
  status: ReportStatus;
  title: string;
  offline: boolean;
  failed?: string;
  priority?: number;
}

export function MechanicPage() {
  const { profile } = useProfile();
  const me = actorOf(profile!);
  const reports = useReports();
  const outbox = useLiveQuery(() => db.outbox.orderBy('created_at').reverse().toArray(), [], [] as OutboxItem[]);
  const pendingId = useRef<string | null>(null);
  const [acking, setAcking] = useState<string | null>(null);

  const mine = useMemo(() => reports.filter((r) => r.actor === me), [reports, me]);
  const question = mine.find((r) => r.status === 'needs_clarification' && r.clarification);
  const answeredLocally = outbox.some((o) => o.target_report_id === question?.report_id && o.created_at > (question?.updated_at ?? ''));
  const activeQuestion = question && !answeredLocally ? question : undefined;
  const tasks = reports.filter((r) => r.assignee === me && (r.status === 'assigned' || r.status === 'acknowledged'));

  // Read each new question aloud once.
  const spoken = useRef(new Set<string>());
  useEffect(() => {
    const c = activeQuestion?.clarification;
    if (!c || spoken.current.has(c.event_id)) return;
    spoken.current.add(c.event_id);
    navigator.vibrate?.([200, 100, 200]);
    void speak(c.question, toBcp47(activeQuestion.transcript?.lang));
  }, [activeQuestion]);

  // Merge local outbox with server-known reports: queued items show before the server has them.
  const rows: Row[] = useMemo(() => {
    const known = new Map(mine.map((r) => [r.report_id, r]));
    const out: Row[] = mine.map((r) => ({
      report_id: r.report_id,
      created_at: r.created_at,
      status: r.status,
      title: r.form?.equipment ?? r.transcript?.text ?? 'Processing voice report…',
      offline: false,
      priority: r.form?.priority,
    }));
    for (const o of outbox) {
      if (o.kind !== 'report_audio' || known.has(o.report_id)) continue;
      out.push({
        report_id: o.report_id,
        created_at: o.created_at,
        status: o.status === 'sent' ? 'recorded' : 'queued',
        title: o.status === 'sent' ? 'Uploaded, waiting for server…' : 'Voice report saved on phone',
        offline: o.status !== 'sent',
        failed: o.status === 'failed' ? o.last_error : undefined,
      });
    }
    return out.sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 30);
  }, [mine, outbox]);

  const onStart = () => {
    pendingId.current = uuid();
  };

  const onRecorded = (rec: Recording) => {
    const id = pendingId.current ?? uuid();
    pendingId.current = null;
    void enqueue({
      report_id: id,
      kind: activeQuestion ? 'clarify_audio' : 'report_audio',
      target_report_id: activeQuestion?.report_id,
      blob: rec.blob,
      mime: rec.mime,
      actor: me,
      device: deviceId(),
    });
  };

  const answer = (option: string) => {
    if (!activeQuestion) return;
    navigator.vibrate?.(60);
    void enqueue({
      report_id: uuid(),
      kind: 'clarify_text',
      target_report_id: activeQuestion.report_id,
      blob: new Blob([JSON.stringify({ answer: option })], { type: 'application/json' }),
      mime: 'application/json',
      actor: me,
      device: deviceId(),
    });
  };

  const ack = async (r: ReportView) => {
    setAcking(r.report_id);
    try {
      await api.ackTask(r.report_id, me);
    } catch {
      alert('No connection to the ship server. Try again in a moment.');
    } finally {
      setAcking(null);
    }
  };

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-4">
      {activeQuestion?.clarification && (
        <Card className="border-2 border-steel bg-steel/15">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-steel">Question about your report</div>
              <div className="mt-1 text-2xl font-semibold leading-tight">{activeQuestion.clarification.question}</div>
            </div>
            {speechSupported && (
              <Btn
                variant="ghost"
                aria-label="Repeat question"
                onClick={() => speak(activeQuestion.clarification!.question, toBcp47(activeQuestion.transcript?.lang))}
              >
                🔊
              </Btn>
            )}
          </div>
          {!!activeQuestion.clarification.options?.length && (
            <div className="mt-4 grid grid-cols-2 gap-3">
              {activeQuestion.clarification.options.map((o) => (
                <button key={o} onClick={() => answer(o)} className="min-h-20 rounded-2xl bg-steel text-2xl font-bold text-ink">
                  {o}
                </button>
              ))}
            </div>
          )}
          <p className="mt-3 text-sm text-cream/70">…or hold the button below and answer by voice.</p>
        </Card>
      )}

      <PushToTalk
        onStart={onStart}
        onRecorded={onRecorded}
        label={activeQuestion ? 'Hold to answer' : 'Hold to report'}
        accent={activeQuestion ? 'question' : 'report'}
      />

      {tasks.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-cream/55">My tasks</h2>
          {tasks.map((t) => (
            <Card key={t.report_id} className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <PriorityBadge p={t.task?.priority ?? t.form?.priority ?? 3} />
                  <StatusBadge status={t.status} />
                </div>
                <div className="mt-1 font-bold">{t.task?.summary ?? t.form?.text_en}</div>
              </div>
              {t.status === 'assigned' && (
                <Btn variant="ok" className="min-h-14 px-5 text-lg" disabled={acking === t.report_id} onClick={() => ack(t)}>
                  Accept
                </Btn>
              )}
            </Card>
          ))}
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-cream/55">My reports</h2>
        {rows.length === 0 && <p className="text-cream/45">No reports yet. Hold the button and describe what you see.</p>}
        {rows.map((r) => (
          <div
            key={r.report_id}
            className={cx(
              'flex items-center gap-3 rounded-xl border px-3 py-3',
              r.offline ? 'border-warn/50 bg-warn/10' : 'border-cream/10 bg-ink/25',
            )}
          >
            <span className="w-16 shrink-0 font-mono text-xs text-cream/60">{timeOf(r.created_at).slice(0, 5)}</span>
            <div className="min-w-0 flex-1">
              <div className="truncate font-semibold">{r.title}</div>
              {r.failed && (
                <button className="text-xs text-alert underline" onClick={() => retryFailed(r.report_id)}>
                  Rejected by server ({r.failed}). Retry
                </button>
              )}
            </div>
            {r.priority && <PriorityBadge p={r.priority} />}
            <StatusBadge status={r.status} />
          </div>
        ))}
      </section>
    </main>
  );
}
