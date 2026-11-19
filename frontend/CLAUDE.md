# GlaukOS (Mózg statku) — kontekst projektu dla Claude Code

> Hackathon Kongsberg Maritime × Wydział Informatyki, 7 godzin. Ten plik opisuje cały projekt, ale szczegółowo tylko moją część: **aplikację PWA (frontend)**. Backend, mowa, LLM i synchronizację robią inne osoby; poniższe kontrakty są wspólne i nie zmieniamy ich bez uzgodnienia z zespołem.
>
> Pełny plan zespołu: https://claude.ai/artifact/DWQEoaMqsj4YqVeUoXZKfX

---

## 1. Produkt w jednym zdaniu

**Mózg statku to pokładowy rejestr zdarzeń, który zamienia głos załogi w zatwierdzone wpisy, zadania i briefingi, także bez internetu.**

Każda informacja na statku (zgłoszenie głosowe, odczyt czujnika, decyzja oficera, przekazanie wachty) to zdarzenie zapisane lokalnie na jednym serwerze. Wszystkie moduły to różne widoki tego samego rejestru.

## 2. Problem i propozycja wartości

- **Maszynownia:** hałas do 110 dB(A), rękawice, brudne ręce. Raporty powstają z pamięci po obchodzie. Zwykłe rozpoznawanie mowy w takim hałasie zawodzi.
- **Biurokracja i zmęczenie:** marynarze uważają, że dokumentacji jest za dużo i że się powtarza. Rejestry czasu odpoczynku są często fikcyjne. Mniej papierów to więcej snu i większe bezpieczeństwo.
- **Wielonarodowe załogi:** zgłoszenie po tagalsku czy polsku musi trafić do dziennika po angielsku (morskim angielskim).
- **Łączność:** Starlink szybko się upowszechnia, ale nie jest wszędzie i nie zawsze. Rozwiązanie jest **offline-first**: działa w pełni na statku, a z lądem synchronizuje się, gdy jest łącze.
- **Regulacje:** MARPOL dopuszcza elektroniczne księgi zapisów zatwierdzone przez banderę, więc wpis głosowy może trafić do legalnego dziennika, jeśli ma ścieżkę audytu i podpis oficera.

**Wyróżnik:** nikt nie łączy w jednym produkcie głosu w hałasie, strukturyzacji do formularza, weryfikacji z danymi z czujników i pracy offline. Produkt **uzupełnia** ekosystem Kongsberga (K-Fleet Logbook, Vessel Insight) jako warstwa „ostatniej mili”, a nie z nim konkuruje.

**Czego system NIE robi:** nie steruje maszynami, nie podejmuje decyzji bez człowieka, nie wysyła danych poza statek bez potrzeby, nie zastępuje alarmów ani rozkładu alarmowego.

## 3. Scenariusz demo (90 s) — wszystko, co budujemy, musi go przejść

1. Slajd z problemem.
2. Mechanik trzyma przycisk i mówi po polsku: „Pompa chłodzenia, ciśnienie spada do 1,8 bara, przeciek na uszczelnieniu”.
3. Telefon zadaje głosem pytanie zwrotne: „Pompa nr 1 czy nr 2?”. Mechanik odpowiada: „Dwa”.
4. System pokazuje, że czujnik pompy nr 2 ma 1,9 bara (zgodne). Formularz jest po angielsku, z kodem SFI i priorytetem.
5. Tablet oficera dostaje zgłoszenie. Oficer zatwierdza i przydziela zadanie.
6. Wyłączamy „łącze satelitarne”. Kolejne zgłoszenie wciąż powstaje, licznik kolejki na ląd rośnie, a po włączeniu łącza spada do zera.
7. Jedno kliknięcie: 60-sekundowy briefing przekazania wachty, odczytany głosem.

## 4. Architektura

```
┌──────────── Urządzenia załogi: jedna aplikacja PWA ────────────┐
│  Telefon mechanika        Tablet oficera        Ekran briefingu │
└───────────────┬────────────────────────────────────────────────┘
                │ HTTPS (REST) + MQTT przez WebSocket, Wi-Fi statku, bez internetu
┌───────────────▼──── Serwer pokładowy (laptop, Docker Compose) ─┐
│  FastAPI + reguły    Rejestr zdarzeń (SQLite)    LLM (Ollama)   │
│  Mosquitto (MQTT)    Mowa (DeepFilterNet+Whisper) Kolejka na ląd│
└──────▲──────────────────────────────────────────────────┬──────┘
       │ tylko odczyt                                      │ gdy jest łącze
 Symulator czujników                                  Atrapa „lądu” armatora
```

Kluczowe zasady:
- **Jeden serwer jest centrum.** Urządzenia nie rozmawiają ze sobą bezpośrednio, tylko przez serwer.
- **MQTT zamiast pushy.** Firebase i APNs wymagają internetu. Własny broker Mosquitto działa bez niego.
- **Aplikacja zapisuje najpierw lokalnie.** Nagranie i zgłoszenie dostają UUID na telefonie i czekają w IndexedDB, aż będzie sieć. Stalowe grodzie tłumią Wi-Fi.
- **Rejestr zdarzeń zamiast nadpisywania.** Stan zgłoszenia to ostatnie zdarzenie dla danego `report_id`.
- **Człowiek zatwierdza.** LLM tylko proponuje formularz, a oficer go zatwierdza.

## 5. Stack całego zespołu

| Warstwa | Technologia | Właściciel |
| --- | --- | --- |
| Aplikacja PWA | React + Vite + TypeScript, vite-plugin-pwa, Tailwind, Dexie (IndexedDB), MQTT.js, MediaRecorder, speechSynthesis | **Oliwier (ja)** |
| Mowa na tekst | DeepFilterNet + faster-whisper; opcjonalnie ElevenLabs Scribe, gdy jest łącze | Mateusz |
| Formularz, tłumaczenie, reguły | Ollama (Qwen2.5 7B / Llama 3.1 8B), wyjście w schemacie JSON, Pydantic, reguły w Pythonie, symulator czujników | Maciej |
| Briefing wachty, slajdy | LLM nad rejestrem zdarzeń | Daniel |
| Backend, broker, sync | FastAPI, Mosquitto, SQLite (WAL), kolejka na ląd, Docker Compose | Szymon |

## 6. Wspólne kontrakty (nie zmieniać bez uzgodnienia)

Kod: `src/types.ts`.

### 6.1 Koperta zdarzenia (REST i MQTT)

```ts
type EventType =
  | 'report.recorded' | 'report.transcribed' | 'report.structured'
  | 'report.clarification_requested' | 'report.clarified' | 'report.sensor_checked'
  | 'report.approved' | 'report.rejected'
  | 'task.assigned' | 'task.acknowledged' | 'task.closed'
  | 'watch.handover_generated' | 'sync.sent';

interface ShipEvent<P = unknown> {
  event_id: string;      // UUID
  ts: string;            // ISO 8601 UTC
  report_id?: string;    // UUID, wiąże zdarzenia jednego zgłoszenia
  type: EventType;
  actor: string;         // np. "2nd_engineer:mateusz"
  device?: string;
  payload: P;
  synced_at?: string | null;
}
```

### 6.2 Formularz zgłoszenia (wyjście LLM, `payload` zdarzenia `report.structured`)

```ts
interface ReportForm {
  equipment: string;        // "Cooling water pump No. 2"
  sfi_code: string;         // "721" (kody z tabeli urządzeń demo)
  parameter?: string;       // "discharge pressure"
  value?: number;           // 1.8
  unit?: string;            // "bar"
  defect?: string;          // "leak at mechanical seal"
  priority: 1 | 2 | 3 | 4 | 5;
  location?: string;
  action_taken?: string;
  text_en: string;          // pełne zdanie po angielsku
  lang_original: string;    // "pl", "tl", "en"...
  missing_fields: string[];
  confidence: number;       // 0–1
}
```

Inne payloady:
- `report.transcribed`: `{ text: string, lang: string }`
- `report.clarification_requested`: `{ question: string, options?: string[] }` (np. `["No. 1", "No. 2"]`)
- `report.sensor_checked`: `{ tag: string, sensor_value: number, unit: string, matches: boolean }`
- `report.approved`: `{ form: ReportForm, assignee: string }`
- `task.assigned`: `{ assignee: string, summary: string, priority: number }`

### 6.3 Status zgłoszenia (wyliczany na froncie z ostatniego zdarzenia)

`recorded` → `transcribed` → `structured` → (`needs_clarification` ↔ `clarified`) → `pending_approval` → `approved` / `rejected` → `assigned` → `acknowledged` → `closed`

Lokalnie, przed wysyłką: `queued` (w IndexedDB, jeszcze nie na serwerze).

### 6.4 Tematy MQTT

| Temat | Kto subskrybuje |
| --- | --- |
| `ship/{shipId}/events` | wszystkie widoki (strumień wszystkich zdarzeń) |
| `role/{role}/approve` | tablet oficera z daną rolą |
| `person/{crewId}` | telefon danej osoby: pytania zwrotne, przydzielone zadania |
| `ship/{shipId}/sensors/{tag}` | backend (frontend opcjonalnie do podglądu) |

QoS 1, sesje trwałe (`clean: false`, stały `clientId` per urządzenie). Wiadomość to `ShipEvent` w JSON.

### 6.5 API HTTP

| Metoda i ścieżka | Opis |
| --- | --- |
| `POST /api/reports/audio` | multipart: `report_id`, `actor`, `device`, `audio` (webm/opus lub mp4/aac). **Idempotentne:** ponowna wysyłka tego samego `report_id` zwraca 200 lub 409 i niczego nie dubluje |
| `POST /api/reports/{id}/clarify` | multipart z `audio` albo JSON `{ answer: string }` |
| `POST /api/reports/{id}/approve` | JSON `{ decision: 'approve' \| 'reject', form?: ReportForm, assignee?: string }` |
| `POST /api/tasks/{id}/ack` | potwierdzenie przyjęcia zadania |
| `GET /api/reports?status=` | lista zgłoszeń z ostatnim stanem i formularzem |
| `GET /api/reports/{id}/events` | chronologia zgłoszenia |
| `GET /api/handover?watch=` | `{ text: string, generated_at: string }` |
| `GET /api/sync/status` | `{ link_up: boolean, queued: number, last_sent_at?: string }` |
| `POST /api/sync/link` | `{ up: boolean }` — przełącznik „łącza satelitarnego” na demo |

## 7. Moja część: aplikacja PWA — specyfikacja

### 7.1 Ekrany

1. **Wybór roli** (`/`): imię + rola (`2nd_engineer`, `chief_engineer`, `officer`), zapis w localStorage. To nasz „login” na demo.
2. **Mechanik** (`/mechanic`):
   - Duży przycisk push-to-talk na pół ekranu: nagrywa przy `pointerdown`, kończy przy `pointerup`/`pointercancel`. Musi działać w rękawicach, więc minimum ~200 px i bez gestów.
   - Potwierdzenie końca nagrania: `navigator.vibrate(...)` na Androidzie i wyraźna zmiana stanu na ekranie (iOS nie ma wibracji).
   - Lista moich zgłoszeń ze statusem i znacznikiem „w kolejce offline”.
   - **Pytanie zwrotne:** po zdarzeniu `report.clarification_requested` na `person/{crewId}` aplikacja czyta pytanie przez `speechSynthesis` (`lang: 'en-US'` lub język mówiącego), pokazuje duże przyciski z `options`, jeśli są, i pozwala odpowiedzieć głosem tym samym przyciskiem.
   - Przydzielone mi zadania z przyciskiem „Przyjmuję”.
3. **Oficer** (`/officer`):
   - Lista zgłoszeń `pending_approval`, aktualizowana na żywo przez MQTT.
   - Szczegóły: formularz z możliwością edycji pól, oryginalna transkrypcja, wynik weryfikacji z czujnikiem (zgodne/niezgodne), chronologia zdarzeń.
   - Przyciski „Zatwierdź i przydziel” (wybór osoby) i „Odrzuć”.
4. **Briefing wachty** (`/handover`): przycisk „Generuj briefing”, tekst, przycisk „Odczytaj” (`speechSynthesis`).
5. **Pasek stanu** na każdym ekranie: połączenie z serwerem (MQTT), liczba zgłoszeń w lokalnej kolejce, stan łącza na ląd + przełącznik łącza (tylko na demo, np. na ekranie oficera).

Wygląd: Tailwind, **ciemny motyw domyślnie** (praca nocą i w ECR), wysoki kontrast, duże elementy dotykowe. Teksty interfejsu po angielsku (język pracy na statku); można dodać przełącznik PL.

### 7.2 Kolejka offline (najważniejsza logika)

Dexie, tabela `outbox` (kod: `src/lib/db.ts`, `src/lib/outbox.ts`).

Zasady:
- Nagranie **najpierw** trafia do IndexedDB, dopiero potem próbujemy wysłać.
- Pętla wysyłki uruchamia się po `online`, po połączeniu MQTT, co 5 s i po każdym nowym nagraniu.
- Wysyłka z tym samym `report_id`; odpowiedź 200 lub 409 oznacza `sent`. Błąd sieci: `pending`, `attempts++`, backoff do 30 s.
- Po restarcie aplikacji kolejka wznawia się sama.
- Test martwej strefy: nagraj z wyłączonym Wi-Fi, włącz Wi-Fi, zgłoszenie dociera bez duplikatu.

### 7.3 MQTT w przeglądarce

- `mqtt` (MQTT.js) przez `wss://` (Mosquitto z listenerem WebSocket; port ustala Szymon, adres w `.env`).
- `clientId` = stały per urządzenie (localStorage), `clean: false`, QoS 1, automatyczne ponowne łączenie.
- Subskrypcje zależne od roli: `ship/{shipId}/events`, `person/{crewId}`, `role/{role}/approve`.
- Jedno źródło stanu: zdarzenia z MQTT i REST trafiają do jednego store'u z kluczem `report_id`. Deduplikacja po `event_id`.

### 7.4 Nagrywanie

- `getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })`.
- `MediaRecorder`: na Chrome/Android `audio/webm;codecs=opus`, na iOS Safari `audio/mp4`. Sprawdzaj `MediaRecorder.isTypeSupported` i wysyłaj faktyczny `mime`.
- Strumień mikrofonu otwieraj raz i trzymaj, żeby nagrywanie startowało bez opóźnienia.

### 7.5 PWA

- `vite-plugin-pwa`, `registerType: 'autoUpdate'`, manifest `name: 'GlaukOS'`, `short_name: 'GlaukOS'`, `display: 'standalone'`, ciemne `theme_color`, ikony 192 i 512.
- Workbox cache'uje app shell. **Nie** cache'ujemy odpowiedzi API (stan jest w IndexedDB i MQTT).
- **HTTPS jest wymagany** dla mikrofonu i service workera poza `localhost` (mkcert, patrz README).
- Offline testujemy na buildzie: `npm run build && npm run preview`.
- iOS: instalacja przez Safari, Udostępnij, „Do ekranu początkowego”.

### 7.6 Tryb atrap

`VITE_MOCK=1` przełącza klienta API i MQTT na lokalną atrapę (`src/lib/mock.ts`). Transport jest za interfejsami `ApiClient` (`src/lib/api.ts`) i `EventBus` (`src/lib/mqtt.ts`), więc przełączenie na prawdziwy backend to tylko zmiana `.env.local`.

## 8. Plan na 7 godzin

| Czas | Zadania | Bramka zespołu |
| --- | --- | --- |
| 0:00–0:30 | Szkielet, routing, `types.ts`, szkic 3 ekranów | 0:30 kontrakty zamrożone |
| 0:30–2:30 | Ekran mechanika: PTT, recorder, outbox, atrapy, lista zgłoszeń | 2:30 każdy moduł działa na atrapach |
| 2:30–4:00 | Ekran oficera; prawdziwe MQTT.js i API zamiast atrap | **4:00 end-to-end działa** |
| 4:00–5:30 | Pytanie zwrotne, briefing, pasek stanu | 5:30 zamrożenie kodu |
| 5:30–7:00 | HTTPS (mkcert), PWA na 2 telefonach, test martwej strefy, poprawki | prezentacja |

Jeśli o 4:00 przepływ nie działa: najpierw wycinam ekran briefingu, potem przełącznik łącza. Pytanie zwrotne i zatwierdzanie zostają.

## 9. Definicja „gotowe”

- [ ] Scenariusz z sekcji 3 przechodzi na dwóch telefonach i laptopie 2 razy z rzędu bez restartu.
- [ ] Zgłoszenie nagrane bez Wi-Fi dociera po przywróceniu sieci, bez duplikatu.
- [ ] Aplikacja zainstalowana jako PWA otwiera się bez połączenia z serwerem.
- [ ] Mikrofon działa na telefonach przez HTTPS.
- [ ] Ciemny motyw, przyciski czytelne z odległości ramienia.

## 10. Poza zakresem (roadmapa, nie kodujemy)

Eskalacja czasowa, ekran mostka, OpenBridge, tarcza odpoczynku i rejestr czasu pracy, Zero Waste Galley, Smart Kabina i HVAC, rezerwacje siłowni i pralni, filtrowanie alarmów K-Chief, RAG „zapytaj starszego mechanika”, NFC/QR i OCR manometrów, urządzenia ATEX, certyfikaty urządzeń.

## 11. Wskazówki dla Claude Code

- Wszystko ma działać z `VITE_MOCK=1`, zanim backend będzie gotowy.
- Proste rozwiązania zamiast frameworków: żadnego Reduxa ani bibliotek UI cięższych niż Tailwind.
- Każda zmiana kontraktu z sekcji 6 wymaga zgody zespołu. Jeśli backend odpowiada inaczej, dopasuj adapter w `src/lib/api.ts`, a nie typy.
- Testuj offline na buildzie produkcyjnym, nie w `vite dev`.
- Commity tylko po akceptacji Oliwiera.

## 12. Decyzje implementacyjne (do potwierdzenia z backendem)

- `crewId` w `person/{crewId}` = `actor`, czyli `"{role}:{imię}"`, np. `person/2nd_engineer:mateusz`.
- Id zadania w `POST /api/tasks/{id}/ack` = `report_id` zgłoszenia, z którego powstało.
- Front dokleja `actor` do JSON-ów `clarify`, `approve` i `ack` (dodatkowe pole, backend może je ignorować).
- `GET /api/reports` może zwrócić tablicę albo `{ reports: [...] }`; front bierze z każdej pozycji `report_id` (lub `id`) i dociąga `/api/reports/{id}/events`.
- Status: `report.structured` z pustym `missing_fields` daje od razu `pending_approval`; `report.sensor_checked` też przesuwa do `pending_approval`.
- Odpowiedź przyciskiem z `options` jest kolejkowana w outbox jako `clarify_text` (JSON `{answer}`), tak jak nagrania.

## 13. Ekran główny i wygląd (stan po iteracji UI)

- `/` to **przekrój statku** (`src/features/overview/`): sektory (mostek, kabiny, kuchnia, siłownia, ECR, wirówki, maszyna sterowa, pokład, ładownie, dziób, zbiorniki), pinezki zgłoszeń z poziomem pilności (czerwona z „!” = wymaga działania: P1–P2 albo niezgodność z czujnikiem i jeszcze niezamknięte), panel powiązań w stylu mapy myśli (osoba, sektor, urządzenie/SFI, czujnik, język, zatwierdzający, powiązane zgłoszenia) i łuki na mapie między powiązanymi zgłoszeniami. Pod spodem podsumowanie: „X/Y zgłoszeń poprawnie” (zatwierdzone bez poprawek, czujnik zgodny), wymagające działania, oczekujące, zgodność z czujnikami, czas do zatwierdzenia, języki, kolejki.
- Logowanie przeniesione na `/role` (`?next=` wraca na stronę docelową). Przegląd i briefing działają bez logowania.
- Przypisanie zgłoszenia do sektora: `src/lib/ship.ts` (`sectorOf`: słowa kluczowe z `location`/`equipment`, potem pierwsza cyfra SFI).
- Paleta: `#122C4F` (navy, tło), `#FBF9E4` (cream, tekst i główne akcje), `#000000` (ink, studnie/cienie), `#5B88B2` (steel, drugorzędny); tokeny w `src/index.css` (`@theme`). Kolory semantyczne: alert / warn / ok.
- Ruch wg zasad Emila Kowalskiego: brak animacji przy częstych akcjach (zakładki), `ease-out` z własną krzywą, `scale(0.97)` przy wciśnięciu (`.press`), popover skaluje od przycisku, hover tylko dla `(hover: hover)`, `prefers-reduced-motion` usuwa ruch.
- W trybie atrap rejestr startuje z historią ~64 zgłoszeń (`src/lib/seed.ts`); „Reset demo data” w menu Demo generuje ją od nowa.

## 14. Supabase (fullstack) — stan po iteracji

- Backend wybiera `VITE_BACKEND`: `mock` (atrapa w przeglądarce), `supabase` (baza + logowanie + nagrania), `http` (FastAPI + MQTT, pierwotny plan).
- Schemat, rangi i RLS: `../supabase/migrations/`; kontrakt dla backendu mowy: `../supabase/README.md`.
- Logowanie = imię + stanowisko (`src/lib/positions.ts`, lustro tabeli `positions`) + miejsce pracy (przedział statku). Pod spodem anonimowy użytkownik Supabase i wiersz w `crew`.
- Uprawnienia: kapitan wszystko; Chief Officer zatwierdza dział pokładowy i kuchnię; Chief Engineer maszynownię; reszta tylko raportuje i widzi swój dział + zadania przydzielone sobie. Baza egzekwuje to RLS-em, UI tylko chowa przyciski (`useVisibleReports`, `canApproveDept`).
- Nagranie: outbox → Storage `recordings/{uid}/{report_id}.webm` → zdarzenie `report.recorded` z `event_id = report_id` (idempotentne).
- Nowy typ zdarzenia (propozycja, do potwierdzenia z zespołem): `report.clarification_answered` — odpowiedź załogi (tekst lub audio); backend odpowiada `report.clarified`.
- Dyżury: `crew.on_duty`, przełącznik „End shift / Start shift” na ekranie Report i w menu konta; na mapie ● pracuje / ○ odpoczywa przy każdym przedziale.
- Uwaga architektoniczna: Supabase jest w chmurze, więc bez łącza ze światem telefon nadal nagrywa (outbox), ale zatwierdzanie i podgląd innych wymagają internetu. Pierwotny plan offline (serwer pokładowy) pozostaje w trybie `http`.
