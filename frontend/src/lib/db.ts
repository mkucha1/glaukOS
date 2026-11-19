import Dexie, { type Table } from 'dexie';
import type { ShipEvent } from '../types';

export interface OutboxItem {
  report_id: string; // generated when recording starts; primary key
  created_at: string;
  kind: 'report_audio' | 'clarify_audio' | 'clarify_text';
  target_report_id?: string; // for clarify_*
  blob: Blob; // audio, or JSON {answer} for clarify_text
  mime: string;
  status: 'pending' | 'sending' | 'sent' | 'failed';
  attempts: number;
  // local-only extras (not part of the team contract)
  actor: string;
  device: string;
  next_attempt_at?: number;
  last_error?: string;
}

class ShipDB extends Dexie {
  outbox!: Table<OutboxItem, string>;
  events!: Table<ShipEvent, string>;

  constructor() {
    super('ship-brain');
    this.version(1).stores({
      outbox: 'report_id, status, created_at',
      events: 'event_id, report_id, ts',
    });
  }
}

export const db = new ShipDB();
