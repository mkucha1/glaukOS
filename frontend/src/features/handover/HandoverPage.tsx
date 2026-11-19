import { useEffect, useState } from 'react';
import { Btn, Card, Eyebrow, cx, timeOf } from '../../components/ui';
import { api } from '../../lib/api';
import { speak, speechSupported, stopSpeaking } from '../../lib/speech';
import type { HandoverResponse } from '../../types';

const WATCHES = ['00-04', '04-08', '08-12', '12-16', '16-20', '20-24'];
const currentWatch = () => WATCHES[Math.floor(new Date().getHours() / 4)];

export function HandoverPage() {
  const [watch, setWatch] = useState(currentWatch);
  const [data, setData] = useState<HandoverResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => () => stopSpeaking(), []);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.handover(watch));
    } catch (e) {
      setError(`Could not generate the briefing: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const read = async () => {
    if (!data) return;
    if (speaking) {
      stopSpeaking();
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    await speak(data.text, 'en-GB');
    setSpeaking(false);
  };

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 pb-20 pt-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Watch handover</h1>
        <p className="mt-1 text-[15px] text-cream/55">A one-minute spoken summary for the next watch.</p>
      </div>

      <div className="grid grid-cols-3 gap-1 rounded-2xl bg-ink/25 p-1 sm:grid-cols-6" role="radiogroup" aria-label="Watch">
        {WATCHES.map((w) => (
          <button
            key={w}
            role="radio"
            aria-checked={w === watch}
            onClick={() => setWatch(w)}
            className={cx(
              'press min-h-11 rounded-xl font-mono text-sm font-medium',
              w === watch ? 'bg-cream text-navy' : 'text-cream/65 hover:bg-cream/5 hover:text-cream',
            )}
          >
            {w}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Btn onClick={generate} disabled={loading} className="min-h-14 flex-1 text-base">
          {loading ? 'Reading the register…' : data ? 'Regenerate briefing' : 'Generate briefing'}
        </Btn>
        {data && speechSupported && (
          <Btn variant={speaking ? 'danger' : 'secondary'} onClick={read} className="min-h-14 flex-1 text-base">
            {speaking ? 'Stop reading' : 'Read aloud'}
          </Btn>
        )}
      </div>
      {error && <p className="rounded-2xl border border-alert/40 bg-alert/10 p-4 text-sm text-alert">{error}</p>}

      {data ? (
        <Card className="enter sm:p-7" key={data.generated_at}>
          <Eyebrow className="mb-4">
            Watch {watch} · generated {timeOf(data.generated_at)}
          </Eyebrow>
          <p className="whitespace-pre-line text-lg leading-relaxed text-cream/90 sm:text-xl">{data.text}</p>
        </Card>
      ) : (
        !loading && (
          <div className="rounded-3xl border border-dashed border-cream/15 p-8 text-center text-sm text-cream/50">
            The briefing is written from the event register: open problems, sensor checks, tasks and who holds them.
          </div>
        )
      )}
    </main>
  );
}
