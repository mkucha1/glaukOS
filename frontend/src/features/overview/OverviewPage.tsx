import { useEffect, useMemo, useRef, useState } from 'react';
import { Card, cx } from '../../components/ui';
import { config } from '../../config';
import { useEvents } from '../../lib/store';
import { useVisibleReports } from '../../lib/visibility';
import { useCrew } from '../../lib/crew';
import { useProfile } from '../../lib/profile';
import { Link } from 'react-router-dom';
import { SEVERITY, enrich, relatedTo, reportsFor, sameFocus, type Focus, type Severity } from '../../lib/ship';
import { FocusPanel } from './FocusPanel';
import { ShipMap } from './ShipMap';
import { Summary } from './Summary';

const FILTERS: Severity[] = ['action', 'open', 'progress', 'resolved'];
const vesselName = config.shipId.replace(/[-_]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export function OverviewPage() {
  const reports = useVisibleReports();
  const events = useEvents();
  const crew = useCrew();
  const { profile } = useProfile();
  const all = useMemo(() => enrich(reports), [reports]);
  const [focus, setFocusRaw] = useState<Focus | null>(null);
  const [shown, setShown] = useState<Set<Severity>>(() => new Set(['action', 'open', 'progress']));
  const panel = useRef<HTMLDivElement>(null);

  const setFocus = (f: Focus | null) => setFocusRaw((cur) => (sameFocus(cur, f) ? null : f));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setFocusRaw(null);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // On narrow screens the panel sits below the map: bring it into view when something is picked.
  useEffect(() => {
    if (!focus || window.innerWidth >= 1024) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    panel.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }, [focus]);

  const { highlight, thread } = useMemo(() => {
    if (!focus) return { highlight: null, thread: [] as { from: string; to: string }[] };
    if (focus.kind === 'report') {
      const r = all.find((x) => x.report_id === focus.id);
      if (!r) return { highlight: null, thread: [] };
      const rel = relatedTo(r, all, 3).map((x) => x.report.report_id);
      return { highlight: new Set([r.report_id, ...rel]), thread: rel.map((to) => ({ from: r.report_id, to })) };
    }
    const list = reportsFor(focus, all).sort((a, b) => a.created_at.localeCompare(b.created_at));
    // People, equipment and systems get a chronological thread; sectors and filters only highlight.
    const chain = focus.kind === 'person' || focus.kind === 'equipment' || focus.kind === 'system';
    const tail = list.slice(-10);
    return {
      highlight: new Set(list.map((r) => r.report_id)),
      thread: chain ? tail.slice(1).map((r, i) => ({ from: tail[i].report_id, to: r.report_id })) : [],
    };
  }, [focus, all]);

  const visible = useMemo(() => all.filter((r) => shown.has(r.severity) || highlight?.has(r.report_id)), [all, shown, highlight]);
  const count = (s: Severity) => all.filter((r) => r.severity === s).length;
  const lastTs = events.length ? events[events.length - 1].ts : null;

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-5 overflow-x-clip px-4 pb-10 pt-5 sm:gap-6 sm:pt-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{vesselName}</h1>
          <p className="mt-1 text-[15px] text-cream/55">
            {all.length} reports on record
            {lastTs && `, last update ${new Date(lastTs).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
          </p>
        </div>
        <div
          className="no-scrollbar -mx-4 flex w-[calc(100%+2rem)] gap-1.5 overflow-x-auto px-4 sm:mx-0 sm:w-auto sm:flex-wrap sm:px-0"
          role="group"
          aria-label="Show pins"
        >
          {FILTERS.map((s) => {
            const on = shown.has(s);
            return (
              <button
                key={s}
                aria-pressed={on}
                onClick={() =>
                  setShown((cur) => {
                    const n = new Set(cur);
                    if (n.has(s)) n.delete(s);
                    else n.add(s);
                    return n;
                  })
                }
                className={cx(
                  'press inline-flex h-10 shrink-0 items-center gap-2 rounded-full border px-3.5 text-sm font-medium',
                  on ? 'border-cream/25 bg-cream/10 text-cream' : 'border-cream/10 text-cream/45 hover:text-cream/70',
                )}
              >
                <span
                  className={cx('h-2.5 w-2.5 rounded-full transition-opacity duration-150', !on && 'opacity-35')}
                  style={{ background: SEVERITY[s].color }}
                />
                {SEVERITY[s].label}
                <span className="font-mono text-xs tabular-nums text-cream/55">{count(s)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {!profile && config.backend === 'supabase' && (
        <Card className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[15px] text-cream/75">Sign in to see the reports of your department.</p>
          <Link to="/role" className="press rounded-2xl bg-cream px-5 py-3 text-[15px] font-semibold text-navy">
            Sign in
          </Link>
        </Card>
      )}
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="overflow-visible p-3 sm:p-6">
            <ShipMap reports={visible} focus={focus} highlight={highlight} thread={thread} onFocus={setFocus} crew={crew} />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-cream/50">
              <span>
                Tap a pin for its connections, or a compartment to see who works there.{' '}
                <span className="whitespace-nowrap">
                  <span className="text-ok">●</span> on duty <span className="ml-1">○</span> resting
                </span>
              </span>
              {focus && (
                <button
                  onClick={() => setFocusRaw(null)}
                  className="press rounded-full border border-cream/15 px-3 py-1 font-medium text-cream/80 hover:border-cream/35"
                >
                  Clear focus · Esc
                </button>
              )}
            </div>
          </Card>
          <div className="hidden lg:block">
            <Summary all={all} onFocus={setFocus} part="register" />
          </div>
        </div>
        <div ref={panel} className="min-w-0 scroll-mt-36 lg:sticky lg:top-20">
          <Card className="sm:p-6">
            <FocusPanel focus={focus} all={all} onFocus={setFocus} />
          </Card>
        </div>
      </div>

      <div className="lg:hidden">
        <Summary all={all} onFocus={setFocus} part="register" />
      </div>
      <Summary all={all} onFocus={setFocus} part="details" />
    </main>
  );
}
