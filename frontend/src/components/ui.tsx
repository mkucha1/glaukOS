import type { ButtonHTMLAttributes, ReactNode } from 'react';
import type { ReportStatus } from '../types';

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ');

const STATUS: Record<ReportStatus, { label: string; cls: string }> = {
  queued: { label: 'Queued offline', cls: 'bg-warn text-ink' },
  recorded: { label: 'Recorded', cls: 'bg-cream/10 text-cream/75' },
  transcribed: { label: 'Transcribed', cls: 'bg-cream/10 text-cream/75' },
  structured: { label: 'Structured', cls: 'bg-steel/25 text-cream' },
  needs_clarification: { label: 'Question', cls: 'bg-steel text-ink' },
  clarified: { label: 'Clarified', cls: 'bg-steel/25 text-cream' },
  pending_approval: { label: 'Awaiting approval', cls: 'bg-cream text-navy' },
  approved: { label: 'Approved', cls: 'bg-ok/20 text-ok' },
  rejected: { label: 'Rejected', cls: 'bg-cream/10 text-cream/55 line-through decoration-cream/30' },
  assigned: { label: 'Assigned', cls: 'bg-ok/20 text-ok' },
  acknowledged: { label: 'In progress', cls: 'bg-steel/25 text-cream' },
  closed: { label: 'Resolved', cls: 'bg-ok/15 text-ok/90' },
};

export function StatusBadge({ status }: { status: ReportStatus }) {
  const s = STATUS[status];
  return (
    <span className={cx('inline-flex h-6 items-center whitespace-nowrap rounded-full px-2.5 text-xs font-medium', s.cls)}>
      {s.label}
    </span>
  );
}

export function PriorityBadge({ p }: { p: number }) {
  const cls =
    p <= 1 ? 'bg-alert text-ink' : p === 2 ? 'bg-alert/20 text-alert' : p === 3 ? 'bg-warn/20 text-warn' : 'bg-cream/10 text-cream/70';
  return <span className={cx('inline-flex h-6 items-center rounded-full px-2 font-mono text-[11px] font-bold', cls)}>P{p}</span>;
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('rounded-3xl border border-cream/10 bg-ink/25 p-5', className)}>{children}</div>;
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('text-[13px] font-medium text-cream/55', className)}>{children}</div>;
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'ok' };

export function Btn({ variant = 'primary', className, ...rest }: BtnProps) {
  const v = {
    primary: 'bg-cream text-navy hover:bg-white',
    secondary: 'bg-steel text-ink hover:bg-[#6b97c0]',
    ok: 'bg-ok text-ink hover:brightness-105',
    danger: 'bg-alert text-ink hover:brightness-105',
    ghost: 'bg-cream/5 text-cream hover:bg-cream/10 border border-cream/15',
  }[variant];
  return (
    <button
      {...rest}
      className={cx(
        'press inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl px-5 text-[15px] font-semibold disabled:cursor-not-allowed disabled:opacity-40',
        v,
        className,
      )}
    />
  );
}

export const timeOf = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

export const shortActor = (actor?: string) => {
  if (!actor) return '';
  const [role, name] = actor.split(':');
  if (!name) return actor;
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} · ${role.replace(/_/g, ' ')}`;
};

export function Avatar({ actor, size = 28 }: { actor?: string; size?: number }) {
  const name = actor?.split(':')[1] ?? actor ?? '?';
  return (
    <span
      className="inline-grid shrink-0 place-items-center rounded-full bg-steel font-semibold text-ink"
      style={{ width: size, height: size, fontSize: size * 0.42 }}
      aria-hidden
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

export function Logo({ size = 28 }: { size?: number }) {
  return <img src="/logo.png" width={size} height={size} alt="" aria-hidden className="shrink-0 object-contain" style={{ width: size, height: size }} />;
}
