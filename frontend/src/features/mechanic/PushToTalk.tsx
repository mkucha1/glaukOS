import { useEffect, useRef, useState } from 'react';
import { cx } from '../../components/ui';
import { recorder, type Recording } from '../../lib/recorder';
import { useT } from '../../lib/i18n';

type Phase = 'idle' | 'starting' | 'recording' | 'saved' | 'too_short' | 'error';

const MIN_MS = 500;

/**
 * Glove-friendly push-to-talk: press anywhere on the big pad, release to finish.
 * No gestures, no double taps. Vibrates on start/stop where supported (not iOS).
 */
export function PushToTalk({
  onStart,
  onRecorded,
  label,
  accent = 'report',
}: {
  onStart: () => void;
  onRecorded: (r: Recording) => void;
  label: string;
  accent?: 'report' | 'question';
}) {
  const [phase, setPhase] = useState<Phase>('idle');
  const t = useT();
  const [micError, setMicError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const pressing = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const initMic = () =>
    recorder
      .ensureStream()
      .then(() => setMicError(null))
      .catch((e: Error) => setMicError(e.message || 'Microphone blocked'));

  useEffect(() => {
    void initMic();
  }, []);

  useEffect(() => {
    if (phase !== 'recording') return;
    const t0 = performance.now();
    const t = setInterval(() => setElapsed(performance.now() - t0), 100);
    return () => clearInterval(t);
  }, [phase]);

  const flash = (p: Phase) => {
    setPhase(p);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setPhase('idle'), 1600);
  };

  const finish = async () => {
    try {
      const rec = await recorder.stop();
      if (rec.durationMs < MIN_MS || rec.blob.size === 0) return flash('too_short');
      navigator.vibrate?.([80, 60, 80]);
      onRecorded(rec);
      flash('saved');
    } catch {
      setPhase('idle');
    }
  };

  const down = async (e: React.PointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    if (pressing.current) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    pressing.current = true;
    setPhase('starting');
    try {
      onStart();
      await recorder.start();
      setMicError(null);
    } catch (err) {
      pressing.current = false;
      setMicError((err as Error).message || 'Microphone blocked');
      setPhase('error');
      return;
    }
    navigator.vibrate?.(40);
    if (!pressing.current) return void finish(); // released while the mic was starting
    setElapsed(0);
    setPhase('recording');
  };

  const up = () => {
    if (!pressing.current) return;
    pressing.current = false;
    if (recorder.recording) void finish();
  };

  const recording = phase === 'recording' || phase === 'starting';
  const base = accent === 'question' ? 'border-steel bg-steel/15 text-cream' : 'border-cream/70 bg-navy-deep text-cream';

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onPointerDown={down}
        onPointerUp={up}
        onPointerCancel={up}
        onLostPointerCapture={up}
        onContextMenu={(e) => e.preventDefault()}
        aria-label={label}
        className={cx(
          'ptt relative flex h-[46dvh] min-h-[220px] w-full touch-none select-none flex-col items-center justify-center gap-3 rounded-[2rem] border-2 text-center shadow-[inset_0_1px_0_rgba(251,249,228,0.06)]',
          recording && 'border-alert bg-alert text-ink',
          phase === 'saved' && 'border-ok bg-ok text-ink',
          phase === 'too_short' && 'border-warn bg-warn/15 text-cream',
          (phase === 'idle' || phase === 'error') && base,
        )}
      >
        {recording ? (
          <>
            <span className="h-5 w-5 animate-pulse rounded-full bg-ink motion-reduce:animate-none" />
            <span className="font-mono text-5xl font-semibold tabular-nums">{(elapsed / 1000).toFixed(1)}s</span>
            <span className="text-lg font-medium">{t('Release to save')}</span>
          </>
        ) : phase === 'saved' ? (
          <>
            <span className="text-6xl font-semibold">✓</span>
            <span className="text-3xl font-semibold tracking-tight">{t('Saved on phone')}</span>
          </>
        ) : phase === 'too_short' ? (
          <span className="text-2xl font-semibold">{t('Hold longer')}</span>
        ) : (
          <>
            <svg viewBox="0 0 24 24" className="h-16 w-16" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
            <span className="text-3xl font-semibold tracking-tight">{label}</span>
          </>
        )}
      </button>
      {micError && (
        <button onClick={initMic} className="rounded-xl border border-alert px-4 py-3 text-left text-sm font-semibold text-alert">
          {t('Microphone unavailable: {e}. Tap to retry.', { e: micError })}
        </button>
      )}
    </div>
  );
}
