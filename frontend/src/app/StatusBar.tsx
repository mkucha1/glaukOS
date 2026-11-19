import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { config } from '../config';
import { db } from '../lib/db';
import { useBusState, useLiveQuery, useSyncStatus } from '../lib/hooks';
import { isDeadZone, mockServer, setDeadZone } from '../lib/mock';
import { roleLabel, useProfile } from '../lib/profile';
import { api } from '../lib/api';
import { Avatar, Logo, cx } from '../components/ui';

function Indicator({ tone, label, value }: { tone: 'ok' | 'warn' | 'alert'; label: string; value?: ReactNode }) {
  const dot = { ok: 'bg-ok', warn: 'bg-warn', alert: 'bg-alert' }[tone];
  return (
    <span className="inline-flex h-8 items-center gap-2 rounded-full bg-ink/25 px-3 text-xs font-medium text-cream/80" title={label}>
      <span className={cx('h-2 w-2 rounded-full', dot)} />
      <span className="hidden sm:inline">{label}</span>
      {value !== undefined && <span className="font-mono font-semibold text-cream">{value}</span>}
    </span>
  );
}

/** Origin-aware popover for demo controls; closes on outside press or Escape. */
function DemoMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { status: sync, refresh } = useSyncStatus();
  const [dead, setDead] = useState(isDeadZone());

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const row = 'press flex w-full items-center justify-between gap-4 rounded-xl px-3 py-2.5 text-left text-sm hover:bg-cream/5';

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cx(
          'press inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold',
          open ? 'border-cream bg-cream text-navy' : 'border-cream/20 text-cream/80 hover:border-cream/40',
        )}
      >
        Demo
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          aria-hidden
          className={cx('transition-transform duration-150', open && 'rotate-180')}
        >
          <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div className="popover absolute right-0 top-10 z-40 w-72 rounded-2xl border border-cream/15 bg-navy-deep p-2 shadow-2xl shadow-ink/60">
          <button
            className={row}
            disabled={!sync}
            onClick={async () => {
              if (!sync) return;
              await api.setLink(!sync.link_up).catch(console.error);
              refresh();
            }}
          >
            <span>
              <span className="block font-semibold">Satellite link</span>
              <span className="text-xs text-cream/55">{sync ? `${sync.queued} events queued for shore` : 'Server unreachable'}</span>
            </span>
            <Toggle on={!!sync?.link_up} />
          </button>
          {config.mock && (
            <button
              className={row}
              onClick={() => {
                setDeadZone(!dead);
                setDead(!dead);
              }}
            >
              <span>
                <span className="block font-semibold">Wi-Fi dead zone</span>
                <span className="text-xs text-cream/55">Simulate losing the ship server</span>
              </span>
              <Toggle on={dead} tone="warn" />
            </button>
          )}
          {config.mock && (
            <button
              className={cx(row, 'text-alert')}
              onClick={async () => {
                if (!confirm('Reset the demo register? Mock events and the local cache will be cleared.')) return;
                mockServer.reset();
                await db.delete();
                location.reload();
              }}
            >
              <span className="font-semibold">Reset demo data</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Toggle({ on, tone = 'ok' }: { on: boolean; tone?: 'ok' | 'warn' }) {
  return (
    <span
      className={cx(
        'relative inline-block h-6 w-10 shrink-0 rounded-full transition-colors duration-200',
        on ? (tone === 'ok' ? 'bg-ok' : 'bg-warn') : 'bg-cream/15',
      )}
    >
      <span
        className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-cream shadow transition-transform duration-200"
        style={{ transform: on ? 'translateX(16px)' : 'none', transitionTimingFunction: 'var(--ease-out)' }}
      />
    </span>
  );
}

export function StatusBar() {
  const { profile, setProfile } = useProfile();
  const navigate = useNavigate();
  const busState = useBusState();
  const queued = useLiveQuery(() => db.outbox.where('status').anyOf('pending', 'sending', 'failed').count(), [], 0);
  const { status: sync } = useSyncStatus();

  const tabs: [string, string][] = [
    ['/', 'Ship'],
    ['/mechanic', 'Report'],
    ['/officer', 'Approvals'],
    ['/handover', 'Handover'],
  ];

  return (
    <header
      className="sticky top-0 z-30 border-b border-cream/10 bg-navy/85 backdrop-blur-xl"
      style={{ paddingTop: 'env(safe-area-inset-top)' }}
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
        <Link to="/" className="flex items-center gap-2.5">
          <Logo size={26} />
          <span className="text-[15px] font-semibold tracking-tight">Ship Brain</span>
        </Link>

        <nav className="order-last -mx-1 flex w-full gap-1 overflow-x-auto px-1 md:order-none md:w-auto">
          {tabs.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cx(
                  'press shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium',
                  isActive ? 'bg-cream text-navy' : 'text-cream/70 hover:bg-cream/5 hover:text-cream',
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1.5">
          <Indicator
            tone={busState === 'connected' ? 'ok' : busState === 'connecting' ? 'warn' : 'alert'}
            label={busState === 'connected' ? 'Server' : busState === 'connecting' ? 'Connecting' : 'Offline'}
          />
          <Indicator tone={queued ? 'warn' : 'ok'} label="Outbox" value={queued} />
          <Indicator
            tone={!sync ? 'alert' : sync.link_up ? 'ok' : 'warn'}
            label={sync?.link_up === false ? 'Shore down' : 'Shore'}
            value={sync ? sync.queued : '–'}
          />
          <DemoMenu />
          {profile ? (
            <button
              onClick={() => {
                setProfile(null);
                navigate('/role');
              }}
              title={`${profile.name} · ${roleLabel(profile.role)} — switch user`}
              className="press ml-1 flex items-center gap-2 rounded-full py-0.5 pl-0.5 pr-0.5 hover:bg-cream/5 sm:pr-3"
            >
              <Avatar actor={`x:${profile.name}`} />
              <span className="hidden text-left text-xs leading-tight sm:block">
                <span className="block font-semibold">{profile.name}</span>
                <span className="text-cream/55">{roleLabel(profile.role)}</span>
              </span>
            </button>
          ) : (
            <Link to="/role" className="press ml-1 rounded-full bg-cream px-3.5 py-1.5 text-xs font-semibold text-navy">
              Sign in
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
