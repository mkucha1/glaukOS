import { useEffect, useState } from 'react';
import { api, type Recording } from '../lib/api';
import type { ReportView } from '../lib/store';
import { useT } from '../lib/i18n';

/** The crew member's own voice, for the officer to check what was actually said. */
export function RecordingPlayer({ report }: { report: ReportView }) {
  const t = useT();
  const [items, setItems] = useState<Recording[]>([]);
  const [failed, setFailed] = useState(false);
  const audioEvents = report.events.filter((e) => e.type === 'report.recorded' || e.type === 'report.clarification_answered').length;

  useEffect(() => {
    let alive = true;
    let made: Recording[] = [];
    setFailed(false);
    api
      .recordings(report)
      .then((r) => {
        made = r;
        if (alive) setItems(r);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      for (const r of made) if (r.url.startsWith('blob:')) URL.revokeObjectURL(r.url);
    };
    // Re-fetch only when a new recording event arrives, not on every status change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report.report_id, audioEvents]);

  if (!items.length && !failed) return null;

  return (
    <div className="flex flex-col gap-2.5 rounded-3xl border border-cream/10 bg-ink/25 p-4">
      <div className="text-[13px] font-medium text-cream/55">{t('Recording')}</div>
      {failed && <p className="text-sm text-cream/55">{t('The recording could not be loaded.')}</p>}
      {items.map((r, i) => (
        <div key={r.url} className="flex flex-col gap-1">
          {items.length > 1 && (
            <span className="text-xs text-cream/50">
              {t(r.label === 'Report' ? 'Report' : 'Answer')}
              {items.length > 2 ? ` ${i}` : ''}
            </span>
          )}
          {/* Native controls: large, keyboard-accessible, and they work with gloves on a tablet. */}
          <audio controls preload="metadata" src={r.url} className="h-11 w-full [color-scheme:dark]" />
        </div>
      ))}
    </div>
  );
}
