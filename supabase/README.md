# GlaukOS na Supabase — kontrakt dla backendu

Baza, logowanie i nagrania są w Supabase (projekt `qrmkuongkxopbtulrjev`). Schemat jest w
[`migrations/20261119140000_glaukos_core.sql`](migrations/20261119140000_glaukos_core.sql):
wklej go w SQL Editor albo `supabase db push`.

## Co trzeba włączyć w panelu

1. **Authentication → Sign In / Providers → Allow anonymous sign-ins: ON.** „Logowanie” w aplikacji to imię + stanowisko +
   miejsce pracy; pod spodem każde urządzenie dostaje anonimowego użytkownika Supabase.
2. **Project Settings → API Keys:** frontend potrzebuje `Project URL` i **publishable key** (`sb_publishable_…`).
   Klucz **service role / secret** jest tylko dla backendu, nigdy w przeglądarce ani w repo.

## Tabele

| Tabela | Co | Kto pisze |
| --- | --- | --- |
| `positions` | stanowiska, dział, ranga, które działy zatwierdza | migracja |
| `crew` | kto jest na statku: imię, stanowisko, `actor`, stanowisko pracy (`station`), `on_duty` | każdy swój wiersz |
| `events` | **rejestr**: każde zdarzenie zgłoszenia (`ShipEvent` z `frontend/src/types.ts`) + `department`, `actor_id` | aplikacja (część typów) i backend (reszta) |
| `ship_status` | łącze satelitarne (`link_up`) i `autopilot` | RPC `set_link`, backend |

## Uprawnienia (RLS)

- **Kapitan** widzi i zatwierdza wszystko. **Chief Officer**: dział pokładowy i kuchnia. **Chief Engineer**: maszynownia.
- Pozostali **tylko raportują**, widzą raporty **swojego działu** i zadania przydzielone im osobiście.
- Dział zgłoszenia = dział osoby, która je nagrała (trigger ustawia `department`; kolejne zdarzenia go dziedziczą).
- Klient może wstawić tylko: `report.recorded` (swoje), `report.clarification_answered` (do swojego zgłoszenia),
  `report.approved` / `report.rejected` / `task.assigned` / `task.closed` (jeśli zatwierdza dany dział),
  `task.acknowledged` / `task.closed` (jeśli to jego zadanie). `actor` i `actor_id` ustawia trigger, nie da się ich podrobić.
- **Backend używa klucza service role**, więc RLS go nie dotyczy i może pisać każdy typ zdarzenia.

## Przepływ nagrania (dla mowy → tekst)

1. Telefon zapisuje nagranie najpierw w IndexedDB (działa bez sieci), potem wysyła:
   - plik do Storage: bucket **`recordings`**, ścieżka **`{auth_uid}/{report_id}.webm`** (iOS: `.m4a`, `audio/mp4`),
   - zdarzenie `report.recorded` z `event_id = report_id` (ponowna wysyłka niczego nie dubluje):

   ```json
   { "type": "report.recorded", "report_id": "…", "actor": "2nd_engineer:mateusz",
     "payload": { "audio_path": "<uid>/<report_id>.webm", "mime": "audio/webm;codecs=opus", "station": "engine" } }
   ```

2. **Backend nasłuchuje nowych `report.recorded`** — do wyboru:
   - Supabase Realtime (`postgres_changes`, INSERT na `public.events`, filtr `type=eq.report.recorded`), albo
   - Database Webhook (Database → Webhooks) na INSERT do `events` → POST na wasz FastAPI.
3. Pobiera audio: `supabase.storage.from_("recordings").download(audio_path)` (service role).
4. Dopisuje kolejne zdarzenia z tym samym `report_id` (UUID `event_id`, `actor` np. `system:whisper`):
   `report.transcribed` → `report.structured` → opcjonalnie `report.clarification_requested` → `report.sensor_checked`.
   Payloady jak w sekcji 6.2 `frontend/CLAUDE.md`.
5. **Odpowiedź na pytanie zwrotne** przychodzi jako nowe zdarzenie **`report.clarification_answered`**:
   `{ "answer": "No. 2" }` (przycisk) albo `{ "audio_path": "<uid>/<report_id>-answer-<id>.webm" }` (głos).
   Backend przetwarza je i wstawia `report.clarified`, potem poprawiony `report.structured` i `report.sensor_checked`.
   *To nowy typ zdarzenia — do potwierdzenia przez zespół.*

```python
# szkic konsumenta (Python, supabase-py, klucz service role z env)
from supabase import create_client
sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def on_recorded(event):
    audio = sb.storage.from_("recordings").download(event["payload"]["audio_path"])
    text, lang = transcribe(audio)                      # DeepFilterNet + faster-whisper
    sb.table("events").insert({"event_id": str(uuid4()), "report_id": event["report_id"],
        "type": "report.transcribed", "actor": "system:whisper",
        "payload": {"text": text, "lang": lang}}).execute()
```

## Autopilot (do czasu, aż backend działa)

`ship_status.autopilot = true` sprawia, że po nagraniu funkcja `demo_autopilot` wstawia scenariusz z demo
(pompa → pytanie „nr 1 czy nr 2?” → czujnik), żeby frontend dało się pokazać bez mowy i LLM.
**Gdy wasz backend jest gotowy:** `update public.ship_status set autopilot = false;`

## Zmiana zmiany (dyżur)

`crew.on_duty` przełącza sama osoba („End shift / Start shift”). Mapa statku pokazuje przy każdym przedziale, ile osób
pracuje (●) i odpoczywa (○); po dotknięciu przedziału widać imiona i od kiedy.

## Briefing na zmianę wachty pisany przez LLM (opcjonalnie)

Migracja [`20261119160000_glaukos_briefings.sql`](migrations/20261119160000_glaukos_briefings.sql) dodaje dwie
**nowe** tabele (nic istniejącego się nie zmienia):

- `briefings`: aplikacja wstawia prośbę `{id, watch, window_from, window_to}` (status `requested`), worker statku
  (`backend/decision`: `shipdec worker`) pisze tekst qwenem z rejestru i ustawia `done` + `text` (albo `failed`).
  Każdy czyta tylko swoje prośby. Briefing obejmuje zgłoszenia, które ta osoba może czytać (jak `can_read`).
- `worker_status.last_seen`: heartbeat workera co ~10 s.

Strona (`HandoverPage`) używa briefingu od LLM tylko wtedy, gdy worker dał znak życia w ostatnich 90 s. Inaczej,
albo przy błędzie, robi briefing z szablonu w przeglądarce (`frontend/src/lib/handover.ts`), jak dotąd.
Bez tej migracji wszystko działa po staremu (worker wyłącza wtedy u siebie briefing).
