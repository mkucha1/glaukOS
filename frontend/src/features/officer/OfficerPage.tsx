import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Card, PriorityBadge, StatusBadge, cx, shortActor, timeOf } from '../../components/ui';
import { AWAITING, type ReportView } from '../../lib/store';
import { useVisibleReports } from '../../lib/visibility';
import { ReportDetail } from './ReportDetail';

function Row({ r, active, fresh, onClick }: { r: ReportView; active: boolean; fresh: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cx(
        'press flex w-full flex-col gap-1.5 rounded-2xl border px-3.5 py-3 text-left',
        active ? 'border-cream/70 bg-cream/10' : 'border-cream/10 bg-ink/25 hover:border-cream/25',
        fresh && 'ring-2 ring-steel',
      )}
    >
      <div className="flex items-center gap-2">
        {r.form && <PriorityBadge p={r.form.priority} />}
        <StatusBadge status={r.status} />
        <span className="ml-auto font-mono text-xs text-cream/60">{timeOf(r.updated_at).slice(0, 5)}</span>
      </div>
      <div className="truncate font-semibold">{r.form?.equipment ?? r.transcript?.text ?? 'New voice report…'}</div>
      <div className="truncate text-xs text-cream/60">
        {shortActor(r.actor)}
        {r.sensor && (
          <span className={r.sensor.matches ? 'text-ok' : 'text-alert'}> · sensor {r.sensor.matches ? 'agrees' : 'DISAGREES'}</span>
        )}
      </div>
    </button>
  );
}

export function OfficerPage() {
  const reports = useVisibleReports();
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get('report'));

  const awaiting = useMemo(
    () =>
      reports
        .filter((r) => AWAITING.includes(r.status))
        .sort((a, b) => Number(b.status === 'pending_approval') - Number(a.status === 'pending_approval')),
    [reports],
  );
  const decided = useMemo(() => reports.filter((r) => !AWAITING.includes(r.status) && r.status !== 'recorded').slice(0, 20), [reports]);

  // Highlight reports that just became ready for approval.
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    const ready = reports.filter((r) => r.status === 'pending_approval').map((r) => r.report_id);
    if (!reports.length) return; // wait for the cache, or everything looks "new"
    if (!seen.current) {
      seen.current = new Set(ready);
      return;
    }
    const newOnes = ready.filter((id) => !seen.current!.has(id));
    if (!newOnes.length) return;
    newOnes.forEach((id) => seen.current!.add(id));
    navigator.vibrate?.(150);
    setFresh((f) => new Set([...f, ...newOnes]));
    setSelected((s) => s ?? newOnes[0]);
  }, [reports]);

  const current = reports.find((r) => r.report_id === selected) ?? null;
  const select = (id: string) => {
    setSelected(id);
    setFresh((f) => {
      const n = new Set(f);
      n.delete(id);
      return n;
    });
  };

  return (
    <main className="mx-auto grid max-w-6xl gap-4 px-4 py-4 md:grid-cols-[minmax(280px,360px)_1fr]">
      <aside className={cx('flex flex-col gap-4', current && 'hidden md:flex')}>
        <section className="flex flex-col gap-2">
          <h2 className="text-[15px] font-semibold">
            Awaiting approval <span className="text-steel">{awaiting.filter((r) => r.status === 'pending_approval').length}</span>
          </h2>
          {awaiting.length === 0 && <p className="text-cream/45">Nothing waiting. New voice reports appear here live.</p>}
          {awaiting.map((r) => (
            <Row
              key={r.report_id}
              r={r}
              active={r.report_id === selected}
              fresh={fresh.has(r.report_id)}
              onClick={() => select(r.report_id)}
            />
          ))}
        </section>
        {decided.length > 0 && (
          <section className="flex flex-col gap-2">
            <h2 className="text-[15px] font-semibold">Decided</h2>
            {decided.map((r) => (
              <Row key={r.report_id} r={r} active={r.report_id === selected} fresh={false} onClick={() => select(r.report_id)} />
            ))}
          </section>
        )}
      </aside>
      <section className={cx(!current && 'hidden md:block')}>
        {current ? (
          <ReportDetail
            key={current.report_id}
            report={current}
            onBack={() => setSelected(null)}
            knownActors={reports.map((r) => r.actor)}
          />
        ) : (
          <Card className="grid h-64 place-items-center text-cream/45">Select a report</Card>
        )}
      </section>
    </main>
  );
}
