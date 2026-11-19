import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { config, switchBackend } from '../config';
import { clearEvents } from '../lib/store';
import { db } from '../lib/db';
import { useBusState, useLiveQuery, useSyncStatus } from '../lib/hooks';
import { isDeadZone, mockServer, setDeadZone } from '../lib/mock';
import { crewByActor, useCrew } from '../lib/crew';
import { isApprover } from '../lib/positions';
import { actorOf, roleLabel, useProfile } from '../lib/profile';
import { sectorLabel } from '../lib/ship';
import { api } from '../lib/api';
import { Avatar, Logo, cx } from '../components/ui';

// ---------- icons (24px, 1.8 stroke) ----------

const Icon = ({ d, className }: { d: ReactNode; className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    width="24"
    height="24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    className={className}
  >
    {d}
  </svg>
);
const ShipIcon = () => (
  <Icon
    d={
      <>
        <path d="M3 15h18l-2.5 5h-13z" />
        <path d="M6 15V9h12v6M9 9V5h4v4" />
      </>
    }
  />
);
const ApproveIcon = () => (
  <Icon
    d={
      <>
        <rect x="4" y="3.5" width="16" height="17" rx="2.5" />
        <path d="m8.5 12 2.5 2.5 4.5-5" />
      </>
    }
  />
);
const HandoverIcon = () => (
  <Icon
    d={
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 7.5V12l3 2" />
      </>
    }
  />
);
const MicIcon = ({ size = 30 }: { size?: number }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
    <rect x="9" y="3" width="6" height="11.5" rx="3" />
    <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
  </svg>
);

// ---------- shared popover behaviour ----------

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
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
  return { open, setOpen, ref };
}

function Toggle({ on, tone = 'ok' }: { on: boolean; tone?: 'ok' | 'warn' }) {
  return (
    <span
      className={cx(
        'relative inline-block h-7 w-12 shrink-0 rounded-full transition-colors duration-200',
        on ? (tone === 'ok' ? 'bg-ok' : 'bg-warn') : 'bg-cream/15',
      )}
    >
      <span
        className="absolute left-0.5 top-0.5 h-6 w-6 rounded-full bg-cream shadow transition-transform duration-200"
        style={{ transform: on ? 'translateX(20px)' : 'none', transitionTimingFunction: 'var(--ease-out)' }}
      />
    </span>
  );
}

// ---------- one status button instead of a row of chips ----------

function useConnectivity() {
  const bus = useBusState();
  const outbox = useLiveQuery(() => db.outbox.where('status').anyOf('pending', 'sending', 'failed').count(), [], 0);
  const { status: sync, refresh } = useSyncStatus();
  let tone: 'ok' | 'warn' | 'alert' = 'ok';
  let label = 'Online';
  if (bus !== 'connected') [tone, label] = ['alert', outbox ? `Offline · ${outbox} to send` : 'Offline'];
  else if (outbox) [tone, label] = ['warn', `Sending ${outbox}`];
  else if (sync && !sync.link_up) [tone, label] = ['warn', 'No shore link'];
  return { bus, outbox, sync, refresh, tone, label };
}

function StatusButton() {
  const { open, setOpen, ref } = usePopover();
  const c = useConnectivity();
  const [dead, setDead] = useState(isDeadZone());
  const dot = { ok: 'bg-ok', warn: 'bg-warn', alert: 'bg-alert' }[c.tone];

  const row = (title: string, detail: string, tone: 'ok' | 'warn' | 'alert') => (
    <div className="flex items-center gap-3 px-3 py-2.5">
      <span className={cx('h-2.5 w-2.5 shrink-0 rounded-full', { ok: 'bg-ok', warn: 'bg-warn', alert: 'bg-alert' }[tone])} />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{title}</span>
        <span className="block text-[13px] text-cream/55">{detail}</span>
      </span>
    </div>
  );
  const action = 'press flex min-h-14 w-full items-center justify-between gap-4 rounded-xl px-3 text-left text-sm hover:bg-cream/5';

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={`Connection: ${c.label}`}
        className={cx(
          'press inline-flex h-10 items-center gap-2 rounded-full border px-3.5 text-sm font-medium',
          open ? 'border-cream bg-cream text-navy' : 'border-cream/15 bg-ink/20 hover:border-cream/30',
        )}
      >
        <span className={cx('h-2 w-2 rounded-full', dot)} />
        {c.label}
      </button>
      {open && (
        <div className="popover absolute right-0 top-12 z-50 w-[min(320px,calc(100vw-2rem))] rounded-2xl border border-cream/15 bg-navy-deep p-1.5 shadow-2xl shadow-ink/60">
          {row(
            config.mock
              ? 'Demo on this device'
              : config.overridden
                ? 'Ship server'
                : config.backend === 'supabase'
                  ? 'GlaukOS cloud'
                  : 'Ship server',
            c.bus === 'connected'
              ? 'Connected over ship Wi-Fi'
              : c.bus === 'connecting'
                ? 'Reconnecting…'
                : 'Unreachable. Reports are kept on this phone.',
            c.bus === 'connected' ? 'ok' : c.bus === 'connecting' ? 'warn' : 'alert',
          )}
          {row(
            'This device',
            c.outbox ? `${c.outbox} recording${c.outbox > 1 ? 's' : ''} waiting to send` : 'Everything sent',
            c.outbox ? 'warn' : 'ok',
          )}
          {row(
            'Shore link',
            !c.sync
              ? 'Unknown'
              : c.sync.link_up
                ? `Up · ${c.sync.queued} queued for shore`
                : `Down · ${c.sync.queued} events held on board`,
            !c.sync ? 'alert' : c.sync.link_up ? 'ok' : 'warn',
          )}
          <div className="my-1.5 h-px bg-cream/10" />
          <div className="px-3 pb-1 pt-1 text-xs font-medium text-cream/45">Demo controls</div>
          <button
            className={action}
            disabled={!c.sync}
            onClick={async () => {
              if (!c.sync) return;
              await api.setLink(!c.sync.link_up).catch(console.error);
              c.refresh();
            }}
          >
            <span className="font-medium">Satellite link</span>
            <Toggle on={!!c.sync?.link_up} />
          </button>
          {config.mock && (
            <button
              className={action}
              onClick={() => {
                setDeadZone(!dead);
                setDead(!dead);
              }}
            >
              <span className="font-medium">Wi-Fi dead zone</span>
              <Toggle on={dead} tone="warn" />
            </button>
          )}
          {config.mock && (
            <button
              className={cx(action, 'text-alert')}
              onClick={async () => {
                if (!confirm('Reset the demo register? Mock events and the local cache will be cleared.')) return;
                mockServer.reset();
                await db.delete();
                location.reload();
              }}
            >
              <span className="font-medium">Reset demo data</span>
            </button>
          )}
          {(config.builtBackend !== 'mock' || config.overridden) && (
            <button
              className={action}
              onClick={async () => {
                // Plan B: the whole scenario runs in this browser, no network needed.
                switchBackend(config.mock ? null : { backend: 'mock' });
                await clearEvents();
                location.reload();
              }}
            >
              <span>
                <span className="block font-medium">Offline demo mode</span>
                <span className="block text-[13px] text-cream/55">Plan B: runs on this device without any server</span>
              </span>
              <Toggle on={config.mock} tone="warn" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function AccountButton({ variant }: { variant: 'top' | 'tab' }) {
  const { profile, setProfile } = useProfile();
  const navigate = useNavigate();
  const { open, setOpen, ref } = usePopover();
  const crew = useCrew();
  const me = profile ? crewByActor(crew, actorOf(profile)) : undefined;
  const onDuty = me?.on_duty ?? true;
  const [busy, setBusy] = useState(false);

  if (!profile)
    return variant === 'top' ? (
      <Link to="/role" className="press rounded-full bg-cream px-4 py-2 text-sm font-semibold text-navy">
        Sign in
      </Link>
    ) : (
      <NavLink to="/role" className="press flex h-full flex-col items-center justify-center gap-1 text-cream/60">
        <Avatar actor="x:?" size={26} />
        <span className="text-[11px] font-medium">Sign in</span>
      </NavLink>
    );

  return (
    <div ref={ref} className={cx('relative', variant === 'tab' && 'h-full')}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={`${profile.name}, ${roleLabel(profile.position)}`}
        className={cx(
          'press flex items-center',
          variant === 'top' ? 'gap-2 rounded-full py-1 pl-1 pr-3 hover:bg-cream/5' : 'h-full w-full flex-col justify-center gap-1',
          variant === 'tab' && (open ? 'text-cream' : 'text-cream/60'),
        )}
      >
        <span className="relative">
          <Avatar actor={`x:${profile.name}`} size={variant === 'top' ? 30 : 26} />
          <span
            className={cx('absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-navy', onDuty ? 'bg-ok' : 'bg-cream/40')}
            title={onDuty ? 'On duty' : 'Resting'}
          />
        </span>
        {variant === 'top' ? (
          <span className="text-left text-xs leading-tight">
            <span className="block font-semibold">{profile.name}</span>
            <span className="text-cream/55">{roleLabel(profile.position)}</span>
          </span>
        ) : (
          <span className="text-[11px] font-medium">{profile.name.split(' ')[0]}</span>
        )}
      </button>
      {open && (
        <div
          className={cx(
            'popover absolute z-50 w-64 rounded-2xl border border-cream/15 bg-navy-deep p-1.5 shadow-2xl shadow-ink/60',
            variant === 'top' ? 'right-0 top-12' : 'bottom-[calc(100%+12px)] right-1 origin-bottom-right',
          )}
          style={variant === 'tab' ? { transformOrigin: 'bottom right' } : undefined}
        >
          <div className="px-3 py-2.5">
            <div className="font-semibold">{profile.name}</div>
            <div className="text-[13px] text-cream/55">
              {roleLabel(profile.position)} · {sectorLabel(profile.station)}
            </div>
          </div>
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await api.setOnDuty(!onDuty, profile).catch((e) => alert(`Could not update your shift: ${(e as Error).message}`));
              setBusy(false);
            }}
            className="press flex min-h-14 w-full items-center justify-between rounded-xl px-3 text-left text-sm hover:bg-cream/5"
          >
            <span>
              <span className="block font-medium">{onDuty ? 'End my shift' : 'Start my shift'}</span>
              <span className="block text-[13px] text-cream/55">
                {onDuty ? 'You are on duty' : 'You are resting'}
                {me && ` since ${new Date(me.duty_changed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
              </span>
            </span>
            <Toggle on={onDuty} />
          </button>
          <button
            onClick={async () => {
              setOpen(false);
              await setProfile(null);
              navigate('/role');
            }}
            className="press flex min-h-14 w-full items-center rounded-xl px-3 text-left text-sm font-medium hover:bg-cream/5"
          >
            Switch user
          </button>
        </div>
      )}
    </div>
  );
}

// ---------- top bar: full nav on desktop, slim on phones ----------

/** Approvers see an approval queue; everyone else sees their department's reports. */
const useTeamLabel = () => {
  const { profile } = useProfile();
  return isApprover(profile?.position) ? 'Approvals' : 'Department';
};

export function TopBar() {
  const team = useTeamLabel();
  const TABS: [string, string][] = [
    ['/', 'Ship'],
    ['/mechanic', 'Report'],
    ['/officer', team],
    ['/handover', 'Handover'],
  ];
  return (
    <header
      className="sticky top-0 z-30 border-b border-cream/10 bg-navy/90 backdrop-blur-xl"
      style={{ paddingTop: 'env(safe-area-inset-top)' }}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4">
        <Link to="/" className="flex items-center gap-2.5">
          <Logo size={34} />
          <span className="text-[15px] font-semibold tracking-tight">GlaukOS</span>
        </Link>
        <nav className="hidden gap-1 md:flex">
          {TABS.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cx(
                  'press rounded-full px-4 py-2 text-sm font-medium',
                  isActive ? 'bg-cream text-navy' : 'text-cream/70 hover:bg-cream/5 hover:text-cream',
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <StatusButton />
          <div className="hidden md:block">
            <AccountButton variant="top" />
          </div>
        </div>
      </div>
    </header>
  );
}

// ---------- bottom tab bar on phones, big mic in the middle ----------

export function BottomNav() {
  const { pathname } = useLocation();
  const team = useTeamLabel();
  const tab = (to: string, label: string, icon: ReactNode) => (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        cx('press flex h-full flex-col items-center justify-center gap-1', isActive ? 'text-cream' : 'text-cream/55')
      }
    >
      {icon}
      <span className="text-[11px] font-medium">{label}</span>
    </NavLink>
  );
  const recording = pathname === '/mechanic';

  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-cream/10 bg-navy-deep/95 backdrop-blur-xl md:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="mx-auto grid h-[68px] max-w-md grid-cols-5 items-stretch px-2">
        {tab('/', 'Ship', <ShipIcon />)}
        {tab('/officer', team, <ApproveIcon />)}
        <div className="relative flex justify-center">
          <NavLink
            to="/mechanic"
            aria-label="Report by voice"
            className={cx(
              'press absolute -top-6 grid h-[72px] w-[72px] place-items-center rounded-full border-[5px] border-navy-deep shadow-lg shadow-ink/50',
              recording ? 'bg-steel text-ink' : 'bg-cream text-navy',
            )}
          >
            <MicIcon />
          </NavLink>
          <span className={cx('mt-auto pb-2 text-[11px] font-medium', recording ? 'text-cream' : 'text-cream/55')}>Report</span>
        </div>
        {tab('/handover', 'Handover', <HandoverIcon />)}
        <AccountButton variant="tab" />
      </div>
    </nav>
  );
}
