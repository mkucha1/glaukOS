import { useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Btn, Eyebrow, Logo, cx } from '../../components/ui';
import { config } from '../../config';
import { DEPARTMENTS, POSITIONS, positionById, type PositionId } from '../../lib/positions';
import { homeFor, useProfile } from '../../lib/profile';
import { SECTORS, type SectorId } from '../../lib/ship';

const RIGHTS = (id: PositionId) => {
  const p = positionById(id)!;
  if (p.id === 'captain') return 'Sees every report and approves everything on board';
  if (p.approves.length) return `Approves and assigns ${p.approves.join(' and ')} reports`;
  return `Reports by voice and sees the ${p.department} department's reports`;
};

export function RolePage() {
  const { profile, setProfile } = useProfile();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next');
  const [name, setName] = useState('');
  const [position, setPosition] = useState<PositionId>('2nd_engineer');
  const [station, setStation] = useState<SectorId>('engine');
  const [stationTouched, setStationTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (profile) return <Navigate to={next ?? homeFor(profile)} replace />;

  const pick = (id: PositionId) => {
    setPosition(id);
    if (!stationTouched) setStation(positionById(id)!.station);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await setProfile({ name: name.trim(), position, station });
      navigate(next ?? homeFor({ position }));
    } catch (err) {
      const msg = (err as Error).message ?? String(err);
      setError(
        /anonymous/i.test(msg)
          ? 'Sign-in is switched off on the server. Enable anonymous sign-ins in Supabase (Authentication → Sign In / Providers).'
          : `Could not sign in: ${msg}`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-dvh max-w-lg flex-col justify-center gap-8 px-5 py-10">
      <div className="enter">
        <Logo size={88} />
        <h1 className="mt-6 text-4xl font-semibold tracking-tight">GlaukOS</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-cream/60">
          Voice reports become approved log entries, tasks and handovers. On board, even without internet.
        </p>
        {config.mock && <span className="mt-4 inline-flex rounded-full bg-warn/15 px-3 py-1 text-xs font-medium text-warn">Demo mode</span>}
      </div>

      <form onSubmit={submit} className="flex flex-col gap-7">
        <label className="flex flex-col gap-2.5">
          <Eyebrow>Your name</Eyebrow>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="given-name"
            placeholder="e.g. Mateusz"
            maxLength={40}
            className="min-h-14 rounded-2xl border border-cream/15 bg-ink/25 px-4 text-lg outline-none transition-colors duration-150 placeholder:text-cream/30 focus:border-cream/60"
          />
        </label>

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-2.5">
            <Eyebrow>Position</Eyebrow>
          </legend>
          {DEPARTMENTS.map((d) => (
            <div key={d.id}>
              <div className="mb-2 text-[13px] text-cream/45">{d.label}</div>
              <div className="flex flex-wrap gap-2">
                {POSITIONS.filter((p) => p.department === d.id).map((p) => {
                  const on = position === p.id;
                  return (
                    <button
                      type="button"
                      key={p.id}
                      aria-pressed={on}
                      onClick={() => pick(p.id)}
                      className={cx(
                        'press min-h-12 rounded-2xl border px-4 text-[15px] font-medium',
                        on ? 'border-cream bg-cream text-navy' : 'border-cream/15 bg-ink/20 hover:border-cream/30',
                      )}
                    >
                      {p.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          <p className="rounded-2xl bg-ink/25 px-4 py-3 text-sm text-cream/70">{RIGHTS(position)}</p>
        </fieldset>

        <label className="flex flex-col gap-2.5">
          <Eyebrow>Where you work</Eyebrow>
          <select
            value={station}
            onChange={(e) => {
              setStation(e.target.value as SectorId);
              setStationTouched(true);
            }}
            className="min-h-14 rounded-2xl border border-cream/15 bg-ink/25 px-4 text-lg outline-none focus:border-cream/60"
          >
            {SECTORS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        {error && <p className="rounded-2xl border border-alert/40 bg-alert/10 p-4 text-sm text-alert">{error}</p>}

        <Btn type="submit" disabled={!name.trim() || busy} className="min-h-14 text-base">
          {busy ? 'Signing in…' : 'Start shift'}
        </Btn>
        <Link to="/" className="text-center text-sm text-cream/50 hover:text-cream/80">
          Just look at the ship overview →
        </Link>
      </form>
    </main>
  );
}
