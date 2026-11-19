// In-browser fake of the ship server for VITE_MOCK=1.
// Events are shared between tabs via BroadcastChannel + localStorage, so a "mechanic" tab
// and an "officer" tab on one laptop see the same register.
import { nowIso, uuid } from '../config';
import { seedEvents } from './seed';
import type {
  ApproveRequest,
  EventType,
  HandoverResponse,
  ReportForm,
  ShipEvent,
  SyncStatus,
} from '../types';

const LOG_KEY = 'shipbrain.mock.events';
const SYNC_KEY = 'shipbrain.mock.sync';
const DEAD_KEY = 'shipbrain.mock.deadzone';
const SYSTEM = 'system:ship-brain';

type Handler = (e: ShipEvent) => void;
const handlers = new Set<Handler>();
const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('ship-brain-mock') : null;
channel?.addEventListener('message', (m) => handlers.forEach((h) => h(m.data as ShipEvent)));

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

const SEEDED_KEY = 'shipbrain.mock.seeded';

/** First run (or after reset): fill the register with realistic history so the overview has a story. */
function readLog(): ShipEvent[] {
  const log = read<ShipEvent[]>(LOG_KEY, []);
  if (read<boolean>(SEEDED_KEY, false)) return log;
  const seeded = [...seedEvents(), ...log].sort((a, b) => a.ts.localeCompare(b.ts));
  write(LOG_KEY, seeded);
  write(SEEDED_KEY, true);
  return seeded;
}
const readSync = () => read<SyncStatus>(SYNC_KEY, { link_up: true, queued: 0 });

function emit(type: EventType, report_id: string | undefined, payload: unknown, actor = SYSTEM) {
  const e: ShipEvent = { event_id: uuid(), ts: nowIso(), report_id, type, actor, device: 'mock-server', payload };
  const log = readLog();
  log.push(e);
  write(LOG_KEY, log.slice(-4000));
  const sync = readSync();
  if (sync.link_up) sync.last_sent_at = e.ts;
  else sync.queued += 1;
  write(SYNC_KEY, sync);
  handlers.forEach((h) => h(e));
  channel?.postMessage(e);
  return e;
}

const later = (ms: number, fn: () => void) => setTimeout(fn, ms);

export const isDeadZone = () => read<boolean>(DEAD_KEY, false);
export const setDeadZone = (on: boolean) => write(DEAD_KEY, on);

function network() {
  if (!navigator.onLine || isDeadZone()) throw new TypeError('Failed to fetch (mock dead zone)');
}

// ---------- demo scenarios ----------

const pumpForm = (no?: 1 | 2): ReportForm => ({
  equipment: no ? `Cooling water pump No. ${no}` : 'Cooling water pump',
  sfi_code: '721',
  parameter: 'discharge pressure',
  value: 1.8,
  unit: 'bar',
  defect: 'leak at mechanical seal',
  priority: 2,
  location: 'Engine room, lower platform',
  text_en: `${no ? `Cooling water pump No. ${no}` : 'Cooling water pump'}: discharge pressure dropping to 1.8 bar, leak at mechanical seal.`,
  lang_original: 'pl',
  missing_fields: no ? [] : ['equipment number'],
  confidence: no ? 0.92 : 0.71,
});

const purifierForm: ReportForm = {
  equipment: 'HFO purifier No. 1',
  sfi_code: '734',
  parameter: 'vibration',
  defect: 'abnormal vibration and noise at bowl',
  priority: 3,
  location: 'Purifier room',
  action_taken: 'Switched to purifier No. 2',
  text_en: 'HFO purifier No. 1: abnormal vibration and noise at bowl. Switched over to purifier No. 2.',
  lang_original: 'pl',
  missing_fields: [],
  confidence: 0.88,
};

function runPipeline(report_id: string, actor: string) {
  const n = new Set(readLog().filter((e) => e.type === 'report.recorded' && e.device !== 'seed').map((e) => e.report_id)).size;
  emit('report.recorded', report_id, {}, actor);
  if (n % 2 === 0) {
    later(1000, () => emit('report.transcribed', report_id, { text: 'Pompa chłodzenia, ciśnienie spada do 1,8 bara, przeciek na uszczelnieniu.', lang: 'pl' }));
    later(1700, () => emit('report.structured', report_id, pumpForm()));
    later(2300, () =>
      emit('report.clarification_requested', report_id, { question: 'Pompa numer jeden czy numer dwa?', options: ['No. 1', 'No. 2'] }),
    );
  } else {
    later(1000, () => emit('report.transcribed', report_id, { text: 'Wirówka paliwa numer jeden, duże wibracje i hałas na bębnie. Przełączyłem na wirówkę numer dwa.', lang: 'pl' }));
    later(1700, () => emit('report.structured', report_id, purifierForm));
    later(2200, () => emit('report.sensor_checked', report_id, { tag: 'PUR1_VIB', sensor_value: 11.4, unit: 'mm/s', matches: true }));
  }
}

function clarify(report_id: string, answer: string) {
  const no: 1 | 2 = /1|one|jed/i.test(answer) && !/2|two|dwa/i.test(answer) ? 1 : 2;
  emit('report.clarified', report_id, { answer });
  later(700, () => emit('report.structured', report_id, pumpForm(no)));
  later(1300, () =>
    emit('report.sensor_checked', report_id, { tag: `CWP${no}_PT`, sensor_value: 1.9, unit: 'bar', matches: true }),
  );
}

// ---------- public surface used by MockApiClient / MockEventBus ----------

export const mockServer = {
  subscribe(h: Handler) {
    handlers.add(h);
    return () => handlers.delete(h);
  },

  events: () => readLog(),

  async uploadAudio(report_id: string, actor: string): Promise<'ok' | 'duplicate'> {
    network();
    await new Promise((r) => setTimeout(r, 250));
    if (readLog().some((e) => e.report_id === report_id && e.type === 'report.recorded')) return 'duplicate';
    later(1000, () => runPipeline(report_id, actor));
    return 'ok';
  },

  async clarify(report_id: string, answer: string | null) {
    network();
    await new Promise((r) => setTimeout(r, 200));
    // Voice answer: pretend Whisper heard "dwa".
    later(800, () => clarify(report_id, answer ?? 'dwa'));
  },

  async approve(report_id: string, req: ApproveRequest, actor: string) {
    network();
    if (req.decision === 'reject') {
      emit('report.rejected', report_id, {}, actor);
      return;
    }
    const form = req.form!;
    const assignee = req.assignee ?? '2nd_engineer:mateusz';
    emit('report.approved', report_id, { form, assignee }, actor);
    later(400, () =>
      emit('task.assigned', report_id, { assignee, summary: `${form.equipment}: ${form.defect ?? form.text_en}`, priority: form.priority }, actor),
    );
  },

  async ack(task_id: string, actor: string) {
    network();
    emit('task.acknowledged', task_id, {}, actor);
  },

  async handover(watch = '00-04'): Promise<HandoverResponse> {
    network();
    await new Promise((r) => setTimeout(r, 900));
    const approved = readLog().filter((e) => e.type === 'task.assigned').length;
    return {
      generated_at: nowIso(),
      text:
        `Watch handover, engine room, ${watch.replace('-', ' to ')}. ` +
        'Main engine running steady at 82 percent load, no alarms active. ' +
        'Cooling water pump number two: discharge pressure dropped to 1.8 bar with a leak at the mechanical seal, confirmed by sensor at 1.9 bar. ' +
        `${approved ? `${approved} task${approved > 1 ? 's' : ''} assigned and open. ` : ''}` +
        'Keep an eye on the pump pressure every hour and have the standby pump ready. ' +
        'HFO purifier number one switched over to number two after abnormal vibration. ' +
        'Nothing else to report. End of handover.',
    };
  },

  async syncStatus(): Promise<SyncStatus> {
    return readSync();
  },

  async setLink(up: boolean) {
    const s = readSync();
    s.link_up = up;
    write(SYNC_KEY, s);
    if (!up) return;
    // Drain the shore queue gradually so the counter visibly falls to zero.
    const t = setInterval(() => {
      const cur = readSync();
      if (!cur.link_up || cur.queued <= 0) return clearInterval(t);
      cur.queued = Math.max(0, cur.queued - 1);
      cur.last_sent_at = nowIso();
      write(SYNC_KEY, cur);
    }, 250);
  },

  reset() {
    write(LOG_KEY, []);
    write(SEEDED_KEY, false);
    write(SYNC_KEY, { link_up: true, queued: 0 });
  },
};
