import { useEffect, useMemo, useState } from 'react';
import { Btn, Card, PriorityBadge, StatusBadge, cx, shortActor, timeOf } from '../../components/ui';
import { api } from '../../lib/api';
import { useCrew } from '../../lib/crew';
import { DEPARTMENTS, canApproveDept, departmentOfActor } from '../../lib/positions';
import { actorOf, useProfile } from '../../lib/profile';
import { AWAITING, type ReportView } from '../../lib/store';
import type { ReportForm } from '../../types';

const FIELDS: { key: keyof ReportForm; label: string; type?: 'number' | 'text' }[] = [
  { key: 'equipment', label: 'Equipment' },
  { key: 'sfi_code', label: 'SFI code' },
  { key: 'parameter', label: 'Parameter' },
  { key: 'value', label: 'Value', type: 'number' },
  { key: 'unit', label: 'Unit' },
  { key: 'defect', label: 'Defect' },
  { key: 'location', label: 'Location' },
  { key: 'action_taken', label: 'Action taken' },
];

const input =
  'min-h-11 w-full rounded-xl border border-cream/15 bg-ink/30 px-3 text-base outline-none transition-colors duration-150 focus:border-cream/60 disabled:opacity-70';

export function ReportDetail({ report, onBack, knownActors }: { report: ReportView; onBack: () => void; knownActors: string[] }) {
  const { profile } = useProfile();
  const me = actorOf(profile!);
  const [form, setForm] = useState<ReportForm | undefined>(report.form);
  const [dirty, setDirty] = useState(false);
  const [assignee, setAssignee] = useState(report.actor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Take server updates (e.g. form re-structured after clarification) unless the officer is editing.
  useEffect(() => {
    if (!dirty) setForm(report.form);
  }, [report.form, dirty]);

  // Assign within the report's department, people on duty first.
  const roster = useCrew();
  const dept = departmentOfActor(report.actor);
  const crew = useMemo(() => {
    const inDept = roster.filter((c) => departmentOfActor(c.actor) === dept || c.actor === report.actor);
    const list = inDept.length ? inDept : roster;
    const sorted = [...list].sort((a, b) => Number(b.on_duty) - Number(a.on_duty) || a.name.localeCompare(b.name));
    const actors = sorted.map((c) => c.actor);
    if (!actors.includes(report.actor) && !report.actor.startsWith('system')) actors.unshift(report.actor);
    return actors.map((a) => ({ actor: a, resting: sorted.find((c) => c.actor === a)?.on_duty === false }));
  }, [roster, dept, report.actor, knownActors]);
  const allowed = canApproveDept(profile!.position, dept);
  const canDecide = AWAITING.includes(report.status) && !!form && allowed;
  const deptLabel = DEPARTMENTS.find((d) => d.id === dept)?.label.toLowerCase() ?? dept;
  const ready = report.status === 'pending_approval';

  const set = <K extends keyof ReportForm>(k: K, v: ReportForm[K]) => {
    setDirty(true);
    setForm((f) => (f ? { ...f, [k]: v } : f));
  };

  const decide = async (decision: 'approve' | 'reject') => {
    setBusy(true);
    setError(null);
    try {
      await api.approve(report.report_id, decision === 'approve' ? { decision, form, assignee } : { decision }, me);
      setDirty(false);
    } catch (e) {
      setError(`Could not reach the ship server (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={onBack} className="rounded-lg border border-cream/15 px-3 py-2 text-sm md:hidden">
          ← List
        </button>
        <StatusBadge status={report.status} />
        {form && <PriorityBadge p={form.priority} />}
        {form && <span className="font-mono text-sm text-cream/60">SFI {form.sfi_code}</span>}
        <span className="ml-auto text-sm text-cream/60">
          {shortActor(report.actor)} · {timeOf(report.created_at)}
        </span>
      </div>
      <h1 className="text-2xl font-semibold leading-tight tracking-tight">{form?.equipment ?? 'Processing…'}</h1>

      <div className="grid gap-3 lg:grid-cols-2">
        {report.sensor ? (
          <Card className={cx('border-2', report.sensor.matches ? 'border-ok' : 'border-alert')}>
            <div className="text-[13px] font-medium text-cream/55">Sensor check · {report.sensor.tag}</div>
            <div className={cx('mt-1 text-2xl font-semibold', report.sensor.matches ? 'text-ok' : 'text-alert')}>
              {report.sensor.matches ? '✓ Consistent' : '✗ Does not match'}
            </div>
            <div className="mt-1 text-sm text-cream/80">
              Sensor {report.sensor.sensor_value} {report.sensor.unit}
              {form?.value !== undefined && ` · reported ${form.value} ${form.unit ?? ''}`}
            </div>
          </Card>
        ) : (
          <Card>
            <div className="text-[13px] font-medium text-cream/55">Sensor check</div>
            <div className="mt-1 text-cream/45">
              {report.status === 'needs_clarification' ? 'Waiting for crew answer…' : 'Not available'}
            </div>
          </Card>
        )}
        <Card>
          <div className="text-[13px] font-medium text-cream/55">
            Original ({report.transcript?.lang ?? '?'}) {form && <>· confidence {Math.round(form.confidence * 100)}%</>}
          </div>
          <div className="mt-1 italic text-cream">{report.transcript ? `“${report.transcript.text}”` : '…'}</div>
          {report.clarification && <div className="mt-2 text-sm text-steel">Asked crew: {report.clarification.question}</div>}
        </Card>
      </div>

      {form && (
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <h2 className="text-[15px] font-semibold">Log entry (EN)</h2>
            {!!form.missing_fields?.length && (
              <span className="text-xs font-bold text-warn">Missing: {form.missing_fields.join(', ')}</span>
            )}
            {dirty && <span className="ml-auto text-xs font-bold text-warn">Edited</span>}
          </div>
          <label className="mb-3 flex flex-col gap-1">
            <span className="text-xs text-cream/60">Entry text</span>
            <textarea
              value={form.text_en}
              disabled={!canDecide}
              onChange={(e) => set('text_en', e.target.value)}
              rows={3}
              className={cx(input, 'py-2')}
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            {FIELDS.map((f) => (
              <label key={f.key} className="flex flex-col gap-1">
                <span className="text-xs text-cream/60">{f.label}</span>
                <input
                  className={input}
                  disabled={!canDecide}
                  type={f.type ?? 'text'}
                  inputMode={f.type === 'number' ? 'decimal' : undefined}
                  value={(form[f.key] as string | number | undefined) ?? ''}
                  onChange={(e) =>
                    set(
                      f.key,
                      (f.type === 'number' ? (e.target.value === '' ? undefined : Number(e.target.value)) : e.target.value) as never,
                    )
                  }
                />
              </label>
            ))}
            <label className="flex flex-col gap-1">
              <span className="text-xs text-cream/60">Priority (1 = highest)</span>
              <select
                className={input}
                disabled={!canDecide}
                value={form.priority}
                onChange={(e) => set('priority', Number(e.target.value) as ReportForm['priority'])}
              >
                {[1, 2, 3, 4, 5].map((p) => (
                  <option key={p} value={p}>
                    P{p}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </Card>
      )}

      {!allowed && AWAITING.includes(report.status) && (
        <p className="rounded-2xl border border-cream/10 bg-ink/25 px-4 py-3 text-sm text-cream/65">
          Waiting for a decision. Only the captain or the head of the {deptLabel} department can approve this report.
        </p>
      )}
      {canDecide && (
        <Card className="sticky bottom-2 z-10 flex flex-wrap items-end gap-3 border-cream/20 bg-navy-deep/95 backdrop-blur">
          <label className="flex min-w-48 flex-1 flex-col gap-1">
            <span className="text-xs text-cream/60">Assign to</span>
            <select className={input} value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              {crew.map((c) => (
                <option key={c.actor} value={c.actor}>
                  {shortActor(c.actor)}
                  {c.resting ? ' — resting' : ''}
                </option>
              ))}
            </select>
          </label>
          <Btn variant="danger" disabled={busy} onClick={() => decide('reject')}>
            Reject
          </Btn>
          <Btn variant="ok" disabled={busy} onClick={() => decide('approve')} className="min-h-14 px-6 text-lg">
            {ready ? 'Approve & assign' : 'Approve anyway'}
          </Btn>
          {error && <p className="w-full text-sm text-alert">{error}</p>}
        </Card>
      )}
      {report.assignee && (
        <p className="text-cream/80">
          Assigned to <b>{shortActor(report.assignee)}</b>
        </p>
      )}

      <Card>
        <h2 className="mb-2 text-[15px] font-semibold">Timeline</h2>
        <ol className="flex flex-col gap-1.5">
          {report.events.map((e) => (
            <li key={e.event_id} className="flex gap-3 text-sm">
              <span className="w-20 shrink-0 font-mono text-cream/45">{timeOf(e.ts)}</span>
              <span className="font-semibold text-cream">{e.type.replace(/^report\./, '')}</span>
              <span className="truncate text-cream/45">{shortActor(e.actor)}</span>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
