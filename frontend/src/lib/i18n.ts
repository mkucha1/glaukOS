// PL/EN interface language. Keys are the English text, so a missing translation shows English.
// Report content (equipment, log entry text) stays in English: it is the ship's working language.
import { useSyncExternalStore } from 'react';

export type Lang = 'en' | 'pl';
const KEY = 'glaukos.lang';

const PL: Record<string, string> = {
  // navigation & status
  Ship: 'Statek',
  Report: 'Zgłoś',
  Approvals: 'Zatwierdzanie',
  Department: 'Mój dział',
  Handover: 'Przekazanie',
  'Report by voice': 'Zgłoś głosem',
  'Sign in': 'Zaloguj',
  Online: 'Online',
  Offline: 'Offline',
  'Offline · {n} to send': 'Offline · {n} do wysłania',
  'Sending {n}': 'Wysyłam {n}',
  'No shore link': 'Brak łącza z lądem',
  'Connection: {s}': 'Połączenie: {s}',
  'Demo on this device': 'Demo na tym urządzeniu',
  'Ship server': 'Serwer pokładowy',
  'GlaukOS cloud': 'Chmura GlaukOS',
  'Connected over ship Wi-Fi': 'Połączono przez Wi-Fi statku',
  'Reconnecting…': 'Łączę ponownie…',
  'Unreachable. Reports are kept on this phone.': 'Brak połączenia. Zgłoszenia czekają na telefonie.',
  'This device': 'To urządzenie',
  '{n} recording(s) waiting to send': 'Nagrania czekające na wysłanie: {n}',
  'Everything sent': 'Wszystko wysłane',
  'Shore link': 'Łącze z lądem',
  Unknown: 'Nieznane',
  'Up · {n} queued for shore': 'Działa · w kolejce na ląd: {n}',
  'Down · {n} events held on board': 'Zerwane · na statku czeka: {n}',
  'Demo controls': 'Sterowanie demo',
  'Satellite link': 'Łącze satelitarne',
  'Wi-Fi dead zone': 'Martwa strefa Wi-Fi',
  'Reset demo data': 'Wyczyść dane demo',
  'Offline demo mode': 'Tryb demo offline',
  'Plan B: runs on this device without any server': 'Plan B: działa na tym urządzeniu bez serwera',
  Language: 'Język',
  'End my shift': 'Kończę zmianę',
  'Start my shift': 'Zaczynam zmianę',
  'You are on duty': 'Jesteś na zmianie',
  'You are resting': 'Odpoczywasz',
  ' since {t}': ' od {t}',
  'Switch user': 'Zmień użytkownika',
  'Could not update your shift: {e}': 'Nie udało się zmienić zmiany: {e}',

  // sign-in
  'Voice reports become approved log entries, tasks and handovers. On board, even without internet.':
    'Zgłoszenia głosowe stają się zatwierdzonymi wpisami, zadaniami i przekazaniem wachty. Na statku, także bez internetu.',
  'Demo mode': 'Tryb demo',
  'Your name': 'Imię',
  'e.g. Mateusz': 'np. Mateusz',
  Position: 'Stanowisko',
  'Where you work': 'Miejsce pracy',
  'Start shift': 'Zaczynam zmianę',
  'Signing in…': 'Loguję…',
  'Just look at the ship overview →': 'Tylko podgląd statku →',
  'Sees every report and approves everything on board': 'Widzi wszystkie zgłoszenia i zatwierdza wszystko na statku',
  'Approves and assigns {d} reports': 'Zatwierdza i przydziela zgłoszenia: {d}',
  "Reports by voice and sees the {d} department's reports": 'Zgłasza głosem i widzi zgłoszenia działu: {d}',
  'Could not sign in: {e}': 'Nie udało się zalogować: {e}',
  'Sign-in is switched off on the server. Enable anonymous sign-ins in Supabase (Authentication → Sign In / Providers).':
    'Logowanie jest wyłączone na serwerze. Włącz anonimowe logowanie w Supabase (Authentication → Sign In / Providers).',
  command: 'dowodzenie',
  deck: 'pokład',
  engine: 'maszynownia',
  catering: 'kuchnia',
  Command: 'Dowodzenie',
  Deck: 'Pokład',
  Engine: 'Maszynownia',
  Catering: 'Kuchnia',
  ' and ': ' i ',

  // positions
  Captain: 'Kapitan',
  'Chief Officer': 'Starszy oficer',
  'Chief Engineer': 'Starszy mechanik',
  '2nd Officer': 'II oficer',
  '2nd Engineer': 'II mechanik',
  '3rd Officer': 'III oficer',
  '3rd Engineer': 'III mechanik',
  'Electro-Technical Officer': 'Elektryk okrętowy',
  Bosun: 'Bosman',
  'Chief Cook': 'Szef kuchni',
  'Able Seaman': 'Starszy marynarz',
  Oiler: 'Motorzysta',
  Motorman: 'Motorzysta',
  Messman: 'Steward',

  // sectors
  'Engine room': 'Maszynownia',
  'Cargo holds': 'Ładownie',
  'Main deck': 'Pokład główny',
  'Bow & mooring': 'Dziób i cumowanie',
  'Ballast & tanks': 'Balast i zbiorniki',
  Steering: 'Maszyna sterowa',
  Purifiers: 'Wirówki',
  ECR: 'CMK',
  'Galley & mess': 'Kuchnia i mesa',
  Cabins: 'Kabiny',
  Bridge: 'Mostek',

  // statuses & severities
  'Queued offline': 'W kolejce offline',
  Recorded: 'Nagrane',
  Transcribed: 'Spisane',
  Structured: 'Ustrukturyzowane',
  Question: 'Pytanie',
  Clarified: 'Doprecyzowane',
  'Awaiting approval': 'Czeka na zatwierdzenie',
  Approved: 'Zatwierdzone',
  Rejected: 'Odrzucone',
  Assigned: 'Przydzielone',
  'In progress': 'W realizacji',
  Resolved: 'Rozwiązane',
  'Action required': 'Wymaga działania',
  Open: 'Otwarte',

  // report screen
  'Question about your report': 'Pytanie do Twojego zgłoszenia',
  'Repeat question': 'Powtórz pytanie',
  '…or hold the button below and answer by voice.': '…albo przytrzymaj przycisk niżej i odpowiedz głosem.',
  'Hold to answer': 'Przytrzymaj, aby odpowiedzieć',
  'Hold to report': 'Przytrzymaj, aby zgłosić',
  'Release to save': 'Puść, aby zapisać',
  'Saved on phone': 'Zapisane w telefonie',
  'Hold longer': 'Przytrzymaj dłużej',
  'Microphone unavailable: {e}. Tap to retry.': 'Mikrofon niedostępny: {e}. Dotknij, aby spróbować ponownie.',
  'My tasks': 'Moje zadania',
  Accept: 'Przyjmuję',
  'My reports': 'Moje zgłoszenia',
  'No reports yet. Hold the button and describe what you see.': 'Brak zgłoszeń. Przytrzymaj przycisk i opisz, co widzisz.',
  'Processing voice report…': 'Przetwarzam zgłoszenie głosowe…',
  'Voice report saved on phone': 'Zgłoszenie zapisane w telefonie',
  'Uploaded, waiting for server…': 'Wysłane, czekam na serwer…',
  'Rejected by server ({e}). Retry': 'Serwer odrzucił ({e}). Ponów',
  'No connection to the ship server. Try again in a moment.': 'Brak połączenia z serwerem statku. Spróbuj za chwilę.',
  'On duty': 'Na zmianie',
  Resting: 'Odpoczywa',
  'Since {t}': 'Od {t}',
  'Shift started': 'Zmiana rozpoczęta',
  ' · with {names}': ' · razem z: {names}',
  'End shift': 'Kończę zmianę',

  // approvals
  Decided: 'Rozpatrzone',
  'Nothing waiting. New voice reports appear here live.': 'Nic nie czeka. Nowe zgłoszenia pojawiają się tu na żywo.',
  'Select a report': 'Wybierz zgłoszenie',
  'New voice report…': 'Nowe zgłoszenie głosowe…',
  'sensor agrees': 'czujnik zgodny',
  'sensor DISAGREES': 'czujnik NIEZGODNY',
  '← List': '← Lista',
  'Processing…': 'Przetwarzanie…',
  'Sensor check': 'Weryfikacja czujnikiem',
  'Sensor check · {tag}': 'Weryfikacja czujnikiem · {tag}',
  '✓ Consistent': '✓ Zgodne',
  '✗ Does not match': '✗ Niezgodne',
  'Sensor {v} {u}': 'Czujnik {v} {u}',
  ' · reported {v} {u}': ' · zgłoszono {v} {u}',
  'Waiting for crew answer…': 'Czekam na odpowiedź załogi…',
  'Not available': 'Brak danych',
  'Original ({lang})': 'Oryginał ({lang})',
  ' · confidence {n}%': ' · pewność {n}%',
  'Asked crew: {q}': 'Pytanie do załogi: {q}',
  'Log entry (EN)': 'Wpis do dziennika (EN)',
  'Missing: {f}': 'Brakuje: {f}',
  Edited: 'Edytowane',
  'Entry text': 'Treść wpisu',
  Equipment: 'Urządzenie',
  'SFI code': 'Kod SFI',
  Parameter: 'Parametr',
  Value: 'Wartość',
  Unit: 'Jednostka',
  Defect: 'Usterka',
  Location: 'Lokalizacja',
  'Action taken': 'Podjęte działanie',
  'Priority (1 = highest)': 'Priorytet (1 = najwyższy)',
  'Assign to': 'Przydziel',
  Reject: 'Odrzuć',
  'Approve & assign': 'Zatwierdź i przydziel',
  'Approve anyway': 'Zatwierdź mimo to',
  'Assigned to {who}': 'Przydzielono: {who}',
  Timeline: 'Historia zgłoszenia',
  ' — resting': ' — odpoczywa',
  ' — suggested': ' — sugerowane',
  'Waiting for a decision. Only the captain or the head of the {d} department can approve this report.':
    'Czeka na decyzję. Zatwierdzić może tylko kapitan albo szef działu: {d}.',
  'Could not reach the ship server ({e}).': 'Brak połączenia z serwerem statku ({e}).',
  'Model decision': 'Decyzja modelu',
  'DPA report': 'Raport do DPA',
  'Check: {f}': 'Sprawdź: {f}',
  'Confident — ready to approve': 'Pewne — gotowe do zatwierdzenia',
  'approves {p}': 'zatwierdza {p}',
  'nobody signed in': 'nikt nie jest zalogowany',
  Priority: 'Priorytet',
  Assignee: 'Wykonawca',
  Recording: 'Nagranie',
  Answer: 'Odpowiedź',
  'The recording could not be loaded.': 'Nie udało się wczytać nagrania.',

  // overview
  '{n} reports on record': 'Zgłoszeń w rejestrze: {n}',
  ', last update {t}': ', ostatnia zmiana {t}',
  'Sign in to see the reports of your department.': 'Zaloguj się, aby zobaczyć zgłoszenia swojego działu.',
  'Tap a pin for its connections, or a compartment to see who works there.':
    'Dotknij pinezki, aby zobaczyć powiązania, albo przedziału, aby zobaczyć, kto tam pracuje.',
  'on duty': 'na zmianie',
  resting: 'odpoczywa',
  'Clear focus · Esc': 'Wyczyść · Esc',
  'Needs attention': 'Wymaga uwagi',
  'Tap a report, pin or compartment to see what it connects to.': 'Dotknij zgłoszenia, pinezki lub przedziału, aby zobaczyć powiązania.',
  'All clear. Nothing requires action.': 'Wszystko w porządku. Nic nie wymaga działania.',
  Connections: 'Powiązania',
  'Connected reports': 'Powiązane zgłoszenia',
  'Crew here': 'Załoga w tym miejscu',
  'Nobody is stationed here.': 'Nikt tu nie pracuje.',
  'No reports here.': 'Brak zgłoszeń.',
  '+ {n} older reports': '+ {n} starszych zgłoszeń',
  'Reported by': 'Zgłosił(a)',
  'Located in': 'Miejsce',
  'Spoken in': 'Język zgłoszenia',
  '{l} → English log': '{l} → dziennik po angielsku',
  'Approved by': 'Zatwierdził(a)',
  'Approved with corrections by': 'Zatwierdził(a) z poprawkami',
  'Rejected by': 'Odrzucił(a)',
  'Assigned to': 'Przydzielono',
  'Review & approve': 'Sprawdź i zatwierdź',
  'Open in approvals': 'Otwórz w zatwierdzaniu',
  'agrees with report': 'zgodny ze zgłoszeniem',
  'does NOT match': 'NIEZGODNY',
  Sector: 'Przedział',
  Filter: 'Filtr',
  'Equipment history': 'Historia urządzenia',
  'SFI group {g}': 'Grupa SFI {g}',
  'reports filed correctly': 'zgłoszeń przyjętych bez poprawek',
  "Approved exactly as structured from the crew's voice, with live sensors in agreement.":
    'Zatwierdzone dokładnie tak, jak powstały z głosu załogi, zgodne z czujnikami.',
  'first-time right': 'za pierwszym razem',
  'Filed correctly': 'Bez poprawek',
  'Approved after correction': 'Zatwierdzone po poprawce',
  'Require action': 'Wymaga działania',
  'Open, lower priority': 'Otwarte, niższy priorytet',
  'By compartment': 'Według przedziałów',
  'P1–P2 problems or sensor mismatch, not yet handled': 'Problemy P1–P2 lub niezgodność z czujnikiem, jeszcze nieobsłużone',
  '{n} more waiting for a crew answer': 'Kolejne {n} czeka na odpowiedź załogi',
  'Ready for an officer to sign': 'Gotowe do podpisu oficera',
  'Sensor agreement': 'Zgodność z czujnikami',
  '{a} of {c} reports confirmed by live sensors': '{a} z {c} zgłoszeń potwierdzonych przez czujniki',
  'Voice to signed entry': 'Od głosu do podpisu',
  'Median time from voice report to officer approval': 'Mediana czasu od zgłoszenia do zatwierdzenia',
  Languages: 'Języki',
  'Offline outbox': 'Kolejka offline',
  'Recordings waiting on this device': 'Nagrania czekają na tym urządzeniu',
  'Every recording reached the ship server': 'Każde nagranie dotarło na serwer',
  'Shore sync': 'Synchronizacja z lądem',
  'Ship server unreachable': 'Brak połączenia z serwerem',
  'Satellite link up, events flowing ashore': 'Łącze działa, zdarzenia płyną na ląd',
  'Link down, events held on board': 'Brak łącza, zdarzenia czekają na statku',
  'Crew on duty': 'Załoga na zmianie',
  '{n} resting right now': 'Teraz odpoczywa: {n}',
  'Nobody signed in yet': 'Nikt się jeszcze nie zalogował',
  'just now': 'przed chwilą',
  '{n} min ago': '{n} min temu',
  '{n} h ago': '{n} godz. temu',
  '{n} d ago': '{n} dni temu',
  Polish: 'polski',
  Tagalog: 'tagalski',
  English: 'angielski',

  // handover
  'Watch handover': 'Przekazanie wachty',
  'A one-minute spoken summary for the next watch.': 'Minutowe podsumowanie głosowe dla następnej wachty.',
  'Reading the register…': 'Czytam rejestr…',
  'Regenerate briefing': 'Wygeneruj ponownie',
  'Generate briefing': 'Generuj briefing',
  'Stop reading': 'Zatrzymaj',
  'Read aloud': 'Odczytaj',
  'Could not generate the briefing: {e}': 'Nie udało się wygenerować briefingu: {e}',
  'Watch {w} · generated {t}': 'Wachta {w} · wygenerowano {t}',
  'The briefing is written from the event register: open problems, sensor checks, tasks and who holds them.':
    'Briefing powstaje z rejestru zdarzeń: otwarte problemy, weryfikacje czujnikami, zadania i kto je ma.',
};

const DICTS: Record<Lang, Record<string, string>> = { en: {}, pl: PL };

/** English until the PL/EN switch ships; a saved choice only exists once that toggle does. */
function initial(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'en' || saved === 'pl') return saved;
  } catch {
    /* ignore */
  }
  return 'en';
}

let lang: Lang = initial();
const listeners = new Set<() => void>();

export function setLang(l: Lang) {
  lang = l;
  try {
    localStorage.setItem(KEY, l);
  } catch {
    /* ignore */
  }
  if (typeof document !== 'undefined') document.documentElement.lang = l;
  listeners.forEach((f) => f());
}
if (typeof document !== 'undefined') document.documentElement.lang = lang;

export const getLang = () => lang;

/** Translate an English UI string; `{name}` placeholders are filled from vars. */
export function translate(key: string, vars?: Record<string, string | number>) {
  let s = DICTS[lang][key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

const subscribe = (f: () => void) => {
  listeners.add(f);
  return () => listeners.delete(f);
};

export function useLang(): Lang {
  return useSyncExternalStore(subscribe, () => lang);
}

/** Hook form: re-renders the component when the language changes. */
export function useT() {
  useLang();
  return translate;
}
