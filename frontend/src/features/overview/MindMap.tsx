import { cx } from '../../components/ui';

export type Tone = 'cream' | 'steel' | 'alert' | 'warn' | 'ok' | 'muted';

export interface MindNode {
  id: string;
  caption: string;
  label: string;
  tone: Tone;
  onClick?: () => void;
}

const DOT: Record<Tone, string> = {
  cream: 'bg-cream',
  steel: 'bg-steel',
  alert: 'bg-alert',
  warn: 'bg-warn',
  ok: 'bg-ok',
  muted: 'bg-cream/30',
};

const ROW = 46;
const GAP = 6;
const ARM = 36;

/**
 * NotebookLM-style mind map: one root, branches fanning out to the right.
 * Every branch is a door to another view of the same register.
 */
export function MindMap({ root, nodes }: { root: { caption: string; label: string }; nodes: MindNode[] }) {
  const total = Math.max(ROW, nodes.length * ROW + (nodes.length - 1) * GAP);
  const cy = total / 2;

  return (
    <div className="grid items-stretch" style={{ gridTemplateColumns: `minmax(0, 116px) ${ARM}px minmax(0, 1fr)` }}>
      <div className="flex items-center">
        <div className="w-full rounded-2xl bg-cream p-3 text-navy shadow-lg shadow-ink/30">
          <div className="font-mono text-[10px] font-medium uppercase tracking-wider text-navy/60">{root.caption}</div>
          <div className="mt-0.5 line-clamp-3 text-[13px] font-semibold leading-snug">{root.label}</div>
        </div>
      </div>

      <svg width={ARM} height={total} viewBox={`0 0 ${ARM} ${total}`} aria-hidden key={root.label} className="overflow-visible">
        {nodes.map((n, i) => {
          const y = i * (ROW + GAP) + ROW / 2;
          return (
            <path
              key={n.id}
              d={`M0 ${cy}C${ARM * 0.55} ${cy} ${ARM * 0.45} ${y} ${ARM} ${y}`}
              fill="none"
              stroke="var(--color-cream)"
              strokeOpacity="0.35"
              strokeWidth="1.4"
              pathLength={1}
              className="link"
            />
          );
        })}
      </svg>

      <ul className="flex flex-col" style={{ gap: GAP }}>
        {nodes.map((n) => {
          const body = (
            <>
              <span className={cx('h-2 w-2 shrink-0 rounded-full', DOT[n.tone])} />
              <span className="min-w-0 flex-1 text-left">
                <span className="block truncate font-mono text-[10px] uppercase tracking-wider text-cream/50">{n.caption}</span>
                <span className="block truncate text-[13.5px] font-medium leading-tight">{n.label}</span>
              </span>
              {n.onClick && (
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className="shrink-0 text-cream/35">
                  <path d="M4.5 2.5 8 6l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              )}
            </>
          );
          const cls = 'flex w-full items-center gap-2.5 rounded-2xl border border-cream/10 bg-ink/20 px-3';
          return (
            <li key={n.id} style={{ height: ROW }}>
              {n.onClick ? (
                <button onClick={n.onClick} className={cx(cls, 'press h-full hover:border-cream/25 hover:bg-cream/5')}>
                  {body}
                </button>
              ) : (
                <div className={cx(cls, 'h-full')}>{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
