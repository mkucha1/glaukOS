import { useNavigate } from 'react-router-dom';
import { Card, Eyebrow, cx } from '../../components/ui';
import { db } from '../../lib/db';
import { useCrew } from '../../lib/crew';
import { useLiveQuery, useSyncStatus } from '../../lib/hooks';
import { APPROVED, SECTORS, SEVERITY, metrics, type Focus, type Severity, type ShipReport } from '../../lib/ship';

const LANG: Record<string, string> = { pl: 'Polish', tl: 'Tagalog', en: 'English', uk: 'Ukrainian', ru: 'Russian' };

function Tile({
  label,
  value,
  sub,
  tone,
  onClick,
}: {
  label: string;
  value: React.ReactNode;
  sub: React.ReactNode;
  tone?: 'alert' | 'ok' | 'warn';
  onClick?: () => void;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={cx(
        'flex flex-col gap-1 rounded-3xl border bg-ink/25 p-4 text-left sm:p-5',
        tone === 'alert' ? 'border-alert/40' : 'border-cream/10',
        onClick && 'press hover:border-cream/30 hover:bg-ink/35',
      )}
    >
      <Eyebrow>{label}</Eyebrow>
      <span
        className={cx(
          'text-3xl font-semibold tracking-tight tabular-nums',
          tone === 'alert' && 'text-alert',
          tone === 'ok' && 'text-ok',
          tone === 'warn' && 'text-warn',
        )}
      >
        {value}
      </span>
      <span className="text-xs leading-snug text-cream/55">{sub}</span>
    </Tag>
  );
}

export function Summary({ all, onFocus, part }: { all: ShipReport[]; onFocus: (f: Focus) => void; part: 'register' | 'details' }) {
  const navigate = useNavigate();
  const m = metrics(all);
  const outbox = useLiveQuery(() => db.outbox.where('status').anyOf('pending', 'sending', 'failed').count(), [], 0);
  const { status: sync } = useSyncStatus(3000);
  const crew = useCrew();

  const approved = all.filter((r) => APPROVED.includes(r.status));
  const segments: { key: string; n: number; color: string; label: string; focus?: Focus }[] = [
    { key: 'correct', n: m.correct, color: 'var(--color-ok)', label: 'Filed correctly' },
    { key: 'corrected', n: approved.length - m.correct, color: 'var(--color-steel)', label: 'Approved after correction' },
    { key: 'action', n: m.action, color: 'var(--color-alert)', label: 'Require action', focus: { kind: 'severity', value: 'action' } },
    { key: 'open', n: m.open, color: 'var(--color-warn)', label: 'Open, lower priority', focus: { kind: 'severity', value: 'open' } },
    { key: 'rejected', n: m.rejected, color: 'color-mix(in srgb, var(--color-cream) 30%, transparent)', label: 'Rejected' },
  ];
  const pct = (n: number) => (m.total ? (n / m.total) * 100 : 0);
  const langTotal = m.langs.reduce((s, [, n]) => s + n, 0) || 1;

  const sectors = SECTORS.map((s) => {
    const list = all.filter((r) => r.sector === s.id);
    const c = (v: Severity) => list.filter((r) => r.severity === v).length;
    return { s, total: list.length, action: c('action'), open: c('open'), progress: c('progress'), resolved: c('resolved') };
  })
    .filter((x) => x.total)
    .sort((a, b) => b.action - a.action || b.open - a.open || b.total - a.total);
  const maxTotal = Math.max(1, ...sectors.map((x) => x.total));

  if (part === 'register')
    return (
      <Card className="flex flex-col gap-5 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex items-baseline gap-1">
              <span className="text-5xl font-semibold tracking-tight tabular-nums sm:text-6xl">{m.correct}</span>
              <span className="text-2xl font-medium text-cream/40 tabular-nums sm:text-3xl">/{m.total}</span>
            </div>
            <p className="mt-1 text-[15px] font-medium">reports filed correctly</p>
            <p className="mt-0.5 max-w-md text-sm text-cream/55">
              Approved exactly as structured from the crew's voice, with live sensors in agreement.
            </p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-semibold tabular-nums text-cream/90">
              {m.total ? Math.round((m.correct / m.total) * 100) : 0}%
            </div>
            <div className="text-xs text-cream/50">first-time right</div>
          </div>
        </div>

        <div className="flex h-3 w-full overflow-hidden rounded-full bg-ink/40">
          {segments.map((seg) =>
            seg.n ? (
              <span
                key={seg.key}
                className="bar-grow h-full first:rounded-l-full last:rounded-r-full"
                style={{ width: `${pct(seg.n)}%`, background: seg.color }}
                title={`${seg.label}: ${seg.n}`}
              />
            ) : null,
          )}
        </div>

        <ul className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          {segments.map((seg) => {
            const inner = (
              <>
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: seg.color }} />
                <span className="min-w-0 flex-1 truncate text-left text-cream/70">{seg.label}</span>
                <span className="font-mono font-semibold tabular-nums">{seg.n}</span>
              </>
            );
            return (
              <li key={seg.key}>
                {seg.focus ? (
                  <button
                    onClick={() => onFocus(seg.focus!)}
                    className="press -mx-2 flex w-[calc(100%+1rem)] items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-cream/5"
                  >
                    {inner}
                  </button>
                ) : (
                  <div className="flex items-center gap-2 py-1 text-sm">{inner}</div>
                )}
              </li>
            );
          })}
        </ul>
      </Card>
    );

  return (
    <section className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]" aria-label="Summary">
      <Card className="flex flex-col gap-3 sm:p-6">
        <div className="flex items-baseline justify-between">
          <h2 className="text-[15px] font-semibold">By compartment</h2>
        </div>
        <ul className="flex flex-col gap-1">
          {sectors.map(({ s, total, action, open, progress, resolved }) => (
            <li key={s.id}>
              <button
                onClick={() => onFocus({ kind: 'sector', id: s.id })}
                className="press -mx-2 flex w-[calc(100%+1rem)] items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-cream/5"
              >
                <span className="w-28 shrink-0 truncate text-left text-sm">{s.label}</span>
                <span className="flex h-2 flex-1 overflow-hidden rounded-full bg-ink/30">
                  <span className="flex h-full bar-grow" style={{ width: `${(total / maxTotal) * 100}%` }}>
                    {[
                      [action, SEVERITY.action.color],
                      [open, SEVERITY.open.color],
                      [progress, SEVERITY.progress.color],
                      [resolved, SEVERITY.resolved.color],
                    ].map(([n, c], i) =>
                      n ? (
                        <span key={i} className="h-full" style={{ width: `${((n as number) / total) * 100}%`, background: c as string }} />
                      ) : null,
                    )}
                  </span>
                </span>
                <span className="w-16 shrink-0 text-right font-mono text-xs tabular-nums">
                  {action ? <span className="font-semibold text-alert">{action}! </span> : null}
                  <span className="text-cream/60">{total}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid grid-cols-2 gap-3 self-start lg:grid-cols-2 xl:grid-cols-4">
        <Tile
          label="Require action"
          value={m.action}
          tone={m.action ? 'alert' : 'ok'}
          sub="P1–P2 problems or sensor mismatch, not yet handled"
          onClick={() => onFocus({ kind: 'severity', value: 'action' })}
        />
        <Tile
          label="Awaiting approval"
          value={m.awaiting}
          sub={m.questions ? `${m.questions} more waiting for a crew answer` : 'Ready for an officer to sign'}
          onClick={() => navigate('/officer')}
        />
        <Tile
          label="Sensor agreement"
          value={m.sensorChecked ? `${Math.round((m.sensorAgree / m.sensorChecked) * 100)}%` : '–'}
          tone={m.sensorChecked && m.sensorAgree < m.sensorChecked ? 'warn' : 'ok'}
          sub={`${m.sensorAgree} of ${m.sensorChecked} reports confirmed by live sensors`}
        />
        <Tile
          label="Voice to signed entry"
          value={m.medianApprovalMin !== null ? `${Math.round(m.medianApprovalMin)} min` : '–'}
          sub="Median time from voice report to officer approval"
        />
        <Tile
          label="Languages"
          value={m.langs.length}
          sub={m.langs
            .slice(0, 3)
            .map(([l, n]) => `${LANG[l] ?? l} ${Math.round((n / langTotal) * 100)}%`)
            .join(' · ')}
        />
        <Tile
          label="Offline outbox"
          value={outbox}
          tone={outbox ? 'warn' : undefined}
          sub={outbox ? 'Recordings waiting on this device' : 'Every recording reached the ship server'}
        />
        <Tile
          label="Shore sync"
          value={sync ? sync.queued : '–'}
          tone={sync && !sync.link_up ? 'warn' : undefined}
          sub={
            !sync
              ? 'Ship server unreachable'
              : sync.link_up
                ? 'Satellite link up, events flowing ashore'
                : 'Link down, events held on board'
          }
        />
        <Tile
          label="Crew on duty"
          value={`${crew.filter((c) => c.on_duty).length}/${crew.length}`}
          sub={crew.length ? `${crew.filter((c) => !c.on_duty).length} resting right now` : 'Nobody signed in yet'}
        />
      </div>
    </section>
  );
}
