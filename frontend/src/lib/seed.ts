// Realistic register history for mock mode: ~two watches of reports across the whole ship,
// in several languages, at every stage of the pipeline. Deterministic for a given anchor time.
import type { EventType, ReportForm, ShipEvent } from '../types';

interface Template {
  equipment: string;
  sfi: string;
  location: string;
  defect: string;
  priority: ReportForm['priority'];
  parameter?: string;
  value?: number;
  unit?: string;
  sensor?: string;
  crew: 'engine' | 'deck' | 'galley' | 'bridge';
  said?: { lang: string; text: string };
}

const T: Template[] = [
  { equipment: 'Main engine cyl. No. 3 exhaust', sfi: '601', location: 'Engine room, ME top platform', defect: 'exhaust temperature high', priority: 2, parameter: 'exhaust gas temperature', value: 455, unit: '°C', sensor: 'ME_EXH_T3', crew: 'engine', said: { lang: 'pl', text: 'Cylinder trzy, temperatura spalin wysoka, czterysta pięćdziesiąt pięć stopni.' } },
  { equipment: 'Lube oil filter', sfi: '711', location: 'Engine room, lower platform', defect: 'filter clogging, high differential pressure', priority: 3, parameter: 'differential pressure', value: 1.4, unit: 'bar', sensor: 'LO_FLT_DP', crew: 'engine' },
  { equipment: 'Cooling water pump No. 1', sfi: '721', location: 'Engine room, lower platform', defect: 'bearing noise', priority: 3, parameter: 'discharge pressure', value: 2.4, unit: 'bar', sensor: 'CWP1_PT', crew: 'engine', said: { lang: 'pl', text: 'Pompa chłodzenia numer jeden, hałas na łożysku, ciśnienie dwa i cztery.' } },
  { equipment: 'Fuel oil supply line', sfi: '731', location: 'Engine room, ME fuel rail', defect: 'leak at flange, fuel on floor plates', priority: 1, crew: 'engine', said: { lang: 'tl', text: 'May tagas sa flange ng fuel line, may langis sa sahig.' } },
  { equipment: 'Aux. engine No. 2', sfi: '651', location: 'Engine room, generator flat', defect: 'jacket water temperature high', priority: 3, parameter: 'jacket water temperature', value: 92, unit: '°C', sensor: 'AE2_JW_T', crew: 'engine' },
  { equipment: 'Bilge well, engine room', sfi: '801', location: 'Engine room, aft bilge', defect: 'high bilge level alarm', priority: 2, parameter: 'level', value: 78, unit: '%', sensor: 'ER_BILGE_L', crew: 'engine' },
  { equipment: 'Air compressor No. 1', sfi: '751', location: 'Engine room, compressor flat', defect: 'safety valve lifting', priority: 3, crew: 'engine', said: { lang: 'pl', text: 'Sprężarka numer jeden, zawór bezpieczeństwa puszcza.' } },
  { equipment: 'HFO purifier No. 1', sfi: '734', location: 'Purifier room', defect: 'abnormal vibration at bowl', priority: 3, parameter: 'vibration', value: 11.4, unit: 'mm/s', sensor: 'PUR1_VIB', crew: 'engine' },
  { equipment: 'LO purifier', sfi: '735', location: 'Purifier room', defect: 'sludge discharge failure', priority: 3, crew: 'engine', said: { lang: 'tl', text: 'Hindi naglalabas ng sludge ang LO purifier.' } },
  { equipment: 'Main switchboard', sfi: '871', location: 'Engine control room', defect: 'low insulation alarm on 440 V bus', priority: 2, parameter: 'insulation resistance', value: 0.8, unit: 'MΩ', sensor: 'MSB_INS', crew: 'engine' },
  { equipment: 'Alarm panel', sfi: '881', location: 'Engine control room', defect: 'two indicators failed lamp test', priority: 4, crew: 'engine' },
  { equipment: 'Steering gear hydraulic unit', sfi: '662', location: 'Steering gear room', defect: 'hydraulic oil level low', priority: 2, parameter: 'oil level', value: 62, unit: '%', sensor: 'SG_OIL_L', crew: 'engine', said: { lang: 'pl', text: 'Maszyna sterowa, niski poziom oleju hydraulicznego, sześćdziesiąt dwa procent.' } },
  { equipment: 'X-band radar', sfi: '421', location: 'Bridge', defect: 'intermittent picture loss', priority: 2, crew: 'bridge' },
  { equipment: 'Gyro compass', sfi: '411', location: 'Bridge', defect: 'heading error against GPS', priority: 3, parameter: 'heading error', value: 1.5, unit: '°', sensor: 'GYRO_ERR', crew: 'bridge' },
  { equipment: 'ECDIS No. 2', sfi: '412', location: 'Bridge', defect: 'chart update failed', priority: 4, crew: 'bridge' },
  { equipment: 'VHF radio, bridge wing', sfi: '431', location: 'Bridge wing, starboard', defect: 'no transmit', priority: 3, crew: 'bridge' },
  { equipment: 'AC unit, accommodation', sfi: '571', location: 'Accommodation deck B', defect: 'insufficient cooling', priority: 4, parameter: 'supply air temperature', value: 19, unit: '°C', sensor: 'HVAC_SUP_T', crew: 'deck' },
  { equipment: 'Cabin 204 shower', sfi: '541', location: 'Cabin 204, accommodation deck B', defect: 'water leaking to deck below', priority: 3, crew: 'deck', said: { lang: 'tl', text: 'Tumutulo ang tubig mula sa shower ng cabin 204.' } },
  { equipment: 'Fire door, deck C', sfi: '511', location: 'Accommodation deck C', defect: 'door closer broken, door does not self-close', priority: 2, crew: 'deck' },
  { equipment: 'Provision cold room', sfi: '561', location: 'Galley, provision store', defect: 'temperature rising', priority: 2, parameter: 'room temperature', value: 6.5, unit: '°C', sensor: 'COLD_RM_T', crew: 'galley' },
  { equipment: 'Galley exhaust fan', sfi: '562', location: 'Galley', defect: 'belt slipping, loud noise', priority: 4, crew: 'galley' },
  { equipment: 'Hatch cover No. 3', sfi: '311', location: 'Main deck, hatch 3', defect: 'hydraulic leak at jack', priority: 3, crew: 'deck', said: { lang: 'pl', text: 'Pokrywa luku trzy, wyciek hydrauliki na siłowniku.' } },
  { equipment: 'Deck crane No. 2', sfi: '321', location: 'Main deck, crane 2', defect: 'slewing brake noise', priority: 3, crew: 'deck' },
  { equipment: 'Lifeboat davit, port', sfi: '505', location: 'Boat deck, port side', defect: 'winch brake lining worn', priority: 2, crew: 'deck' },
  { equipment: 'Cargo hold No. 2 bilge', sfi: '341', location: 'Cargo hold 2', defect: 'bilge high level alarm', priority: 2, parameter: 'level', value: 64, unit: '%', sensor: 'H2_BILGE_L', crew: 'deck' },
  { equipment: 'Hold No. 4 ventilation fan', sfi: '342', location: 'Cargo hold 4', defect: 'fan not starting', priority: 4, crew: 'deck' },
  { equipment: 'Bow thruster', sfi: '631', location: 'Bow thruster room', defect: 'motor overheating', priority: 2, parameter: 'motor temperature', value: 88, unit: '°C', sensor: 'BT_MOT_T', crew: 'engine' },
  { equipment: 'Anchor windlass', sfi: '451', location: 'Forecastle', defect: 'brake lining worn', priority: 3, crew: 'deck' },
  { equipment: 'Ballast pump No. 1', sfi: '821', location: 'Ballast system, pump room', defect: 'low suction pressure', priority: 3, parameter: 'suction pressure', value: -0.4, unit: 'bar', sensor: 'BP1_SUC_P', crew: 'engine' },
  { equipment: 'Ballast tank 3P', sfi: '211', location: 'Double bottom, ballast tank 3P', defect: 'level sensor reading erratic', priority: 4, crew: 'deck' },
];

const CREW = {
  engine: ['2nd_engineer:mateusz', '3rd_engineer:rodel', 'oiler:jun', 'chief_engineer:piotr', 'motorman:andriy'],
  deck: ['bosun:tomasz', 'ab:marco', 'ab:jayson', '2nd_officer:lena'],
  galley: ['cook:ana', 'messman:joel'],
  bridge: ['2nd_officer:lena', '3rd_officer:kai', 'chief_officer:anna'],
};
const APPROVER = { engine: 'chief_engineer:piotr', deck: 'officer:anna', galley: 'officer:anna', bridge: 'officer:anna' };

type Final =
  | 'closed'
  | 'acknowledged'
  | 'assigned'
  | 'approved'
  | 'pending_approval'
  | 'needs_clarification'
  | 'structured'
  | 'rejected';

// 64 reports: mostly resolved history, a handful open right now.
const PLAN: [Final, number][] = [
  ['closed', 33],
  ['acknowledged', 9],
  ['assigned', 5],
  ['approved', 2],
  ['pending_approval', 6],
  ['needs_clarification', 2],
  ['structured', 2],
  ['rejected', 5],
];

function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seededId(rand: () => number) {
  const h = Array.from({ length: 32 }, () => Math.floor(rand() * 16).toString(16)).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20)}`;
}

export function seedEvents(now = Date.now()): ShipEvent[] {
  const rand = rng(20261119);
  const pick = <X,>(xs: X[]) => xs[Math.floor(rand() * xs.length)];
  const finals: Final[] = PLAN.flatMap(([f, n]) => Array<Final>(n).fill(f));
  // Older reports are resolved; the open ones are recent.
  const order: Final[] = ['closed', 'rejected', 'acknowledged', 'approved', 'assigned', 'structured', 'needs_clarification', 'pending_approval'];
  finals.sort((a, b) => order.indexOf(a) - order.indexOf(b) || rand() - 0.5);

  // Walk a shuffled template list so open items (the newest) are all different equipment.
  const deck = [...T].sort(() => rand() - 0.5);
  const events: ShipEvent[] = [];
  const total = finals.length;
  const span = 22 * 3600_000;

  finals.forEach((final, i) => {
    const tpl = deck[(total - 1 - i) % deck.length];
    const report_id = seededId(rand);
    const reporter = pick(CREW[tpl.crew]);
    const approver = APPROVER[tpl.crew];
    // spread over the last 22 h, open items towards now
    let t = now - span + (span * (i + rand() * 0.6)) / total - 20 * 60_000;
    const ev = (type: EventType, payload: unknown, actor = 'system:ship-brain', dt = 15_000 + rand() * 30_000) => {
      t += dt;
      events.push({ event_id: seededId(rand), ts: new Date(Math.min(t, now - 5_000)).toISOString(), report_id, type, actor, device: 'seed', payload });
    };

    const said = tpl.said ?? { lang: 'en', text: `${tpl.equipment}, ${tpl.defect}${tpl.value !== undefined ? `, ${tpl.value} ${tpl.unit}` : ''}.` };
    const form: ReportForm = {
      equipment: tpl.equipment,
      sfi_code: tpl.sfi,
      parameter: tpl.parameter,
      value: tpl.value,
      unit: tpl.unit,
      defect: tpl.defect,
      priority: tpl.priority,
      location: tpl.location,
      text_en: `${tpl.equipment}: ${tpl.defect}${tpl.value !== undefined ? ` (${tpl.parameter} ${tpl.value} ${tpl.unit})` : ''}.`,
      lang_original: said.lang,
      missing_fields: final === 'structured' ? ['location detail'] : [],
      confidence: Math.round((0.72 + rand() * 0.26) * 100) / 100,
    };

    ev('report.recorded', {}, reporter, 0);
    ev('report.transcribed', { text: said.text, lang: said.lang });
    ev('report.structured', form);
    if (final === 'structured') return;
    if (final === 'needs_clarification') {
      ev('report.clarification_requested', { question: `Which unit exactly: ${tpl.equipment.replace(/No\. \d/, '')} No. 1 or No. 2?`, options: ['No. 1', 'No. 2'] });
      return;
    }
    const mismatch = !!tpl.sensor && rand() < 0.08;
    if (tpl.sensor && tpl.value !== undefined) {
      const sv = mismatch ? Math.round(tpl.value * 0.55 * 10) / 10 : Math.round(tpl.value * (0.96 + rand() * 0.08) * 10) / 10;
      ev('report.sensor_checked', { tag: tpl.sensor, sensor_value: sv, unit: tpl.unit, matches: !mismatch });
    }
    if (final === 'pending_approval') return;
    if (final === 'rejected') {
      ev('report.rejected', {}, approver, 4 * 60_000 + rand() * 20 * 60_000);
      return;
    }
    const corrected = rand() < 0.22;
    const approvedForm: ReportForm = corrected
      ? { ...form, priority: Math.max(1, Math.min(5, form.priority + (rand() < 0.5 ? -1 : 1))) as ReportForm['priority'], text_en: `${form.text_en} Verified on site.` }
      : form;
    const assignee = tpl.crew === 'engine' ? pick(CREW.engine.filter((c) => !c.startsWith('chief'))) : reporter;
    ev('report.approved', { form: approvedForm, assignee }, approver, 3 * 60_000 + rand() * 25 * 60_000);
    if (final === 'approved') return;
    ev('task.assigned', { assignee, summary: `${approvedForm.equipment}: ${approvedForm.defect}`, priority: approvedForm.priority }, approver, 5_000);
    if (final === 'assigned') return;
    ev('task.acknowledged', {}, assignee, 2 * 60_000 + rand() * 10 * 60_000);
    if (final === 'acknowledged') return;
    ev('task.closed', {}, assignee, 30 * 60_000 + rand() * 120 * 60_000);
  });

  return events.sort((a, b) => a.ts.localeCompare(b.ts));
}
