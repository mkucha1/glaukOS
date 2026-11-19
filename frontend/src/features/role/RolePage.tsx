import { useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Btn, Eyebrow, Logo, cx } from '../../components/ui';
import { config } from '../../config';
import { homeFor, ROLES, useProfile } from '../../lib/profile';
import type { Role } from '../../types';

const ROLE_HINT: Record<Role, string> = {
  '2nd_engineer': 'Report by voice, answer questions, accept tasks',
  chief_engineer: 'Report by voice and follow machinery tasks',
  officer: 'Approve reports, assign tasks, run the demo link',
};

export function RolePage() {
  const { profile, setProfile } = useProfile();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next');
  const [name, setName] = useState('');
  const [role, setRole] = useState<Role>('2nd_engineer');

  if (profile) return <Navigate to={next ?? homeFor(profile.role)} replace />;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setProfile({ name: name.trim(), role });
    navigate(next ?? homeFor(role));
  };

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-10 px-5 py-10">
      <div className="enter">
        <Logo size={44} />
        <h1 className="mt-6 text-4xl font-semibold tracking-tight">Ship Brain</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-cream/60">
          Voice reports become approved log entries, tasks and handovers. On board, even without internet.
        </p>
        {config.mock && (
          <span className="mt-4 inline-flex rounded-full bg-warn/15 px-3 py-1 font-mono text-[11px] font-medium uppercase tracking-wider text-warn">
            Mock mode
          </span>
        )}
      </div>
      <form onSubmit={submit} className="flex flex-col gap-7">
        <label className="flex flex-col gap-2.5">
          <Eyebrow>Your name</Eyebrow>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="given-name"
            placeholder="e.g. Mateusz"
            className="min-h-14 rounded-2xl border border-cream/15 bg-ink/25 px-4 text-lg outline-none transition-colors duration-150 placeholder:text-cream/30 focus:border-cream/60"
          />
        </label>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2.5">
            <Eyebrow>Role on board</Eyebrow>
          </legend>
          {ROLES.map((r) => {
            const on = role === r.id;
            return (
              <button
                type="button"
                key={r.id}
                onClick={() => setRole(r.id)}
                aria-pressed={on}
                className={cx(
                  'press flex min-h-16 items-center gap-4 rounded-2xl border px-4 py-3 text-left',
                  on ? 'border-cream bg-cream text-navy' : 'border-cream/15 bg-ink/20 hover:border-cream/30',
                )}
              >
                <span
                  className={cx('grid h-5 w-5 shrink-0 place-items-center rounded-full border-2', on ? 'border-navy' : 'border-cream/30')}
                >
                  {on && <span className="h-2 w-2 rounded-full bg-navy" />}
                </span>
                <span>
                  <span className="block text-base font-semibold">{r.label}</span>
                  <span className={cx('block text-sm', on ? 'text-navy/65' : 'text-cream/50')}>{ROLE_HINT[r.id]}</span>
                </span>
              </button>
            );
          })}
        </fieldset>
        <Btn type="submit" disabled={!name.trim()} className="min-h-14 text-base">
          Continue
        </Btn>
        <Link to="/" className="text-center text-sm text-cream/50 hover:text-cream/80">
          Just look at the ship overview →
        </Link>
      </form>
    </main>
  );
}
