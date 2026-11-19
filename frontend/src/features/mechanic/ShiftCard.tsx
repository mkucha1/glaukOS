import { useState } from 'react';
import { cx } from '../../components/ui';
import { api } from '../../lib/api';
import { crewByActor, useCrew } from '../../lib/crew';
import { actorOf, useProfile } from '../../lib/profile';
import { sectorById } from '../../lib/ship';

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/** End or start your shift; everyone sees it on the ship map next to your compartment. */
export function ShiftCard() {
  const { profile } = useProfile();
  const crew = useCrew();
  const me = profile ? crewByActor(crew, actorOf(profile)) : undefined;
  const [busy, setBusy] = useState(false);
  if (!profile) return null;
  const onDuty = me?.on_duty ?? true;
  const colleagues = crew.filter((c) => c.station === profile.station && c.actor !== actorOf(profile) && c.on_duty);

  const toggle = async () => {
    setBusy(true);
    try {
      await api.setOnDuty(!onDuty, profile);
      navigator.vibrate?.(60);
    } catch (e) {
      alert(`Could not update your shift: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={cx(
        'flex items-center gap-3 rounded-3xl border p-3 pl-4',
        onDuty ? 'border-cream/10 bg-ink/25' : 'border-steel/40 bg-steel/10',
      )}
    >
      <span className={cx('h-3 w-3 shrink-0 rounded-full', onDuty ? 'bg-ok' : 'bg-cream/40')} />
      <div className="min-w-0 flex-1">
        <div className="text-[15px] font-semibold">
          {onDuty ? 'On duty' : 'Resting'} · {sectorById(profile.station).label}
        </div>
        <div className="truncate text-[13px] text-cream/55">
          {me ? `Since ${time(me.duty_changed_at)}` : 'Shift started'}
          {colleagues.length > 0 && ` · with ${colleagues.map((c) => c.name).join(', ')}`}
        </div>
      </div>
      <button
        onClick={toggle}
        disabled={busy}
        className={cx(
          'press min-h-14 shrink-0 rounded-2xl px-5 text-[15px] font-semibold disabled:opacity-50',
          onDuty ? 'bg-cream/10 text-cream hover:bg-cream/15' : 'bg-cream text-navy',
        )}
      >
        {onDuty ? 'End shift' : 'Start shift'}
      </button>
    </div>
  );
}
