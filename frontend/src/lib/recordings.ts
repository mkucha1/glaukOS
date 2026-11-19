import { db } from './db';
import type { ReportView } from './store';

export interface Recording {
  label: string;
  url: string;
}

/** Audio still on this device (demo mode, or a report not yet sent). */
export async function localRecordings(r: ReportView): Promise<Recording[]> {
  const items = await db.outbox.toArray();
  const own = items.filter(
    (i) => (i.kind === 'report_audio' && i.report_id === r.report_id) || (i.kind === 'clarify_audio' && i.target_report_id === r.report_id),
  );
  return own.map((i) => ({ label: i.kind === 'report_audio' ? 'Report' : 'Answer', url: URL.createObjectURL(i.blob) }));
}
