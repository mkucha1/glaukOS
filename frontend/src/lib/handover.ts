// Local watch briefing built straight from the register. Used when no briefing service
// (Daniel's LLM endpoint, VITE_API_URL) is configured and the ship worker (qwen) is not running.
import { enrich, sectorById, type ShipReport } from './ship';
import { buildReports, getEvents } from './store';
import type { HandoverResponse } from '../types';

const fmt = (r: ShipReport) => `${r.form?.equipment ?? 'an unstructured voice report'}${r.form?.defect ? `, ${r.form.defect}` : ''}`;

/** Briefing plus where it came from: the LLM model name, or "register" for the local template. */
export type Briefing = HandoverResponse & { source?: string };

/** The most recent occurrence of a watch like "08-12", in local time: [from, to] as ISO strings. */
export function watchWindow(watch: string, now = new Date()): [string, string] {
  const [h1, h2] = watch.split('-').map(Number);
  const from = new Date(now);
  from.setHours(h1, 0, 0, 0);
  if (from > now) from.setDate(from.getDate() - 1);
  const to = new Date(from);
  to.setHours(from.getHours() + ((h2 - h1 + 24) % 24 || 24));
  return [from.toISOString(), to.toISOString()];
}

export function localHandover(watch: string): Briefing {
  const all = enrich(buildReports(getEvents()));
  const since = Date.now() - 4 * 3600_000;
  const recent = all.filter((r) => new Date(r.updated_at).getTime() >= since);
  const action = all.filter((r) => r.severity === 'action');
  const open = all.filter((r) => r.severity === 'open');
  const progress = all.filter((r) => r.severity === 'progress');
  const mismatch = all.filter((r) => r.sensor?.matches === false);

  const parts: string[] = [`Watch handover, ${watch.replace('-', ' to ')}.`];
  parts.push(
    recent.length
      ? `${recent.length} report${recent.length > 1 ? 's' : ''} changed during this watch.`
      : 'No new reports during this watch.',
  );
  if (action.length) {
    parts.push(
      `${action.length} need${action.length === 1 ? 's' : ''} action: ` +
        action
          .slice(0, 4)
          .map((r) => `${fmt(r)} in the ${sectorById(r.sector).label.toLowerCase()}`)
          .join('; ') +
        '.',
    );
  } else parts.push('Nothing requires immediate action.');
  if (mismatch.length)
    parts.push(`Sensor readings disagree with ${mismatch.length} report${mismatch.length > 1 ? 's' : ''}; check them on site.`);
  if (progress.length) parts.push(`${progress.length} task${progress.length > 1 ? 's are' : ' is'} being worked on.`);
  if (open.length) parts.push(`${open.length} lower-priority item${open.length > 1 ? 's remain' : ' remains'} open.`);
  parts.push('End of handover.');
  return { text: parts.join(' '), generated_at: new Date().toISOString(), source: 'register' };
}
