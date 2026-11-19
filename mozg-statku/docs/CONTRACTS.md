# Kontrakty integracyjne — Mózg statku

Wersja 1.0. Zmiana kontraktu tylko po zgłoszeniu na stand-upie. Wszystkie moduły czytają ten sam rejestr zdarzeń.

## Zasady wspólne

- **Prawda jest w rejestrze (REST), MQTT/SSE to tylko „dzwonek”.** Po każdym ponownym połączeniu klient dociąga stan przez `GET /api/reports…`.
- **ID nadaje urządzenie.** `report_id` i `event_id` to UUID v4 generowane na telefonie *zanim* cokolwiek zostanie wysłane. Ponowienie z tym samym ID nigdy nie tworzy duplikatu (serwer zwraca `200` + `"duplicate": true` zamiast `201`).
- **Czas = czas nagrania.** Telefon wysyła `recorded_at` (ISO 8601); zgłoszenie nagrane w martwej strefie o 10:00 i wysłane o 10:07 ma w rejestrze 10:00.
- Język wpisów: zawsze angielski (`form.text_en`); oryginał zostaje w `transcript.text`.
- Pola formularza zaczynające się od `_` są wewnętrzne — zostają na statku, nie idą na ląd.

---

## Mateusz — `server/plugins/stt.py`

```python
def transcribe(audio_path: str, lang_hint: str | None = None) -> dict:
    return {"text": "Pompa chłodzenia…", "lang": "pl", "duration_s": 3.2, "model": "large-v3-turbo"}
```
- Plik to oryginał z przeglądarki: `webm/opus` (Android) albo `mp4/aac` (iPhone). `plugins.audio_utils.to_wav16k(path)` zwraca WAV 16 kHz mono (ffmpeg jest w obrazie).
- Wywoływana w wątku, raz na nagranie (także dla głosowej odpowiedzi na pytanie zwrotne — pliki `clar-N.*`).
- Wyjątek → 2 ponowienia → zdarzenie `report.failed` (oficer widzi błąd, przycisk „Ponów”).
- Model ładuj leniwie raz (zmienna globalna). Zależności dopisz do `server/requirements-ai.txt`.

## Maciej — `server/plugins/brain.py` + symulator czujników

```python
def structure(text, lang, context) -> dict              # formularz ReportForm (po angielsku)
def check(form, sensors, context) -> dict                # Decision: priority, route_role, checks, clarification
def apply_clarification(form, clarification, answer_text, answer_lang, context) -> dict   # nowy formularz
```
- `context = {"report_id", "crew": {...lang, role}, "equipment": config/equipment.json, "round", "ollama_url"}`
- `sensors.get("CW_PUMP_2_P") -> {"tag","value","unit","ts","age_s"} | None`
- `check()` zwraca `"clarification": {"question", "lang", "question_en", "field"}` → serwer wysyła pytanie na `person/{crew_id}` i czeka. Po odpowiedzi woła `apply_clarification()` i znowu `check()`. Maksymalnie `MAX_CLARIFY_ROUNDS` (2) rund, potem zgłoszenie idzie do oficera z flagą `unresolved_clarification`.
- `route_role` → temat `role/{route_role}/approve`; `priority: 5` → `ship/{id}/bridge/alert`.
- **Oficer tylko przy małej pewności.** Serwer wysyła zgłoszenie do oficera, gdy `form.confidence < AUTO_APPROVE_CONFIDENCE` (domyślnie 0.9), czujnik się nie zgadza (`ok: false`) albo pytanie zostało bez odpowiedzi. W przeciwnym razie zatwierdza automatycznie (`report.approved` z `auto: true`, aktor `system:auto_approve`). `confidence` musi więc naprawdę coś znaczyć. Możesz nadpisać decyzję polem `"needs_officer": true/false` w wyniku `check()`, a `"assignee": "tom"` od razu przydzieli zadanie przy auto-zatwierdzeniu.
- Pełne modele: `server/app/contracts.py`. Tabela urządzeń/tagów: `server/config/equipment.json` (kody SFI ilustracyjne — do weryfikacji).
- **Czujniki:** publikuj na `ship/{SHIP_ID}/sensors/{TAG}` JSON `{"tag","value","unit","ts"}` (retained, QoS 1), broker `localhost:1883`. Zaślepka: `server/sim/sensors.py` (`docker compose stop sensors`, żeby uruchomić swój).

## Daniel — `server/plugins/refine.py` (przerobienie raportu)

```python
def refine(text: str, lang: str, context: dict) -> dict:
    return {"text": "Pompa chłodzenia, ciśnienie spada do 1,8 bara.", "lang": "pl", "changes": ["usunięto wtrącenia"]}
```
- Krok między Mateuszem a Maciejem: `report.transcribed` → `refine()` → `report.refined` → `brain.structure()` dostaje tekst Daniela.
- Wejście to surowa transkrypcja (wtrącenia, powtórzenia, liczby słownie). Wyjście to czysty tekst zgłoszenia; oryginał zostaje w rejestrze pod audyt.
- `context = {"report_id", "crew", "equipment", "ollama_url"}` — słownik urządzeń z `equipment.json` pomaga poprawiać terminy.
- Wywoływana raz na zgłoszenie (odpowiedzi na pytania zwrotne idą bezpośrednio do Macieja).

## Oliwier — PWA

Adres bazowy: `https://<SERVER_IP>` (Caddy: strona, `/api/*`, `wss://<SERVER_IP>/mqtt` — jeden certyfikat).

### HTTP API

| Metoda i ścieżka | Ciało | Odpowiedź |
|---|---|---|
| `POST /api/reports/audio` | multipart: `audio` (plik), `report_id`, `crew_id`, opc. `event_id`, `device`, `recorded_at`, `lang_hint`, `sha256` | `201` nowe / `200` duplikat / `409` ten sam `report_id` z innym nagraniem |
| `POST /api/reports/text` | JSON `{report_id, crew_id, text, lang?, recorded_at?}` | jw. (plan B bez mikrofonu) |
| `GET /api/reports?status=pending_approval&role=chief_engineer&crew_id=` | `status` może być listą po przecinku albo `open` | lista podsumowań |
| `GET /api/reports/{id}` | | pełny stan + `timeline` (oś czasu pod audyt) |
| `GET /api/reports/{id}/audio` | | nagranie (odsłuch dla oficera) |
| `POST /api/reports/{id}/clarify` | JSON `{event_id, text, crew_id?}` albo multipart z `audio` | `201`/`200` duplikat/`409` |
| `POST /api/reports/{id}/approve` | `{event_id, officer_id, decision: "approve"\|"reject", assignee?, note?, form_patch?}` | stan zgłoszenia z `tasks[]` |
| `POST /api/reports/{id}/retry` | | po `failed` |
| `GET /api/tasks?assignee=tom` | | lista zadań |
| `POST /api/tasks/{task_id}/ack` · `/close` | `{event_id, crew_id, note?}` | zadanie |
| `GET /api/sync/status` · `POST /api/sync/link {"up": true}` | | licznik kolejki na ląd, przełącznik satelity |
| `GET /api/crew` · `GET /api/equipment` · `GET /api/sensors` | | dane pomocnicze |
| `GET /api/stream?topics=person/marek,role/+/approve&since_seq=N` | | SSE — fallback dla MQTT |

Statusy zgłoszenia: `recorded → transcribed → refined → structured → (checked → awaiting_clarification → clarified →)* pending_approval → approved/rejected → assigned → in_progress → closed`, plus `failed`. Przy wysokiej pewności `pending_approval` trwa ułamek sekundy i od razu przechodzi w `approved` (`auto_approved: true` w podsumowaniu, powód w `approval_reason`).

### Tematy MQTT (QoS 1)

| Temat | Treść | Kto słucha |
|---|---|---|
| `person/{crew_id}` | `{type:"clarification", report_id, question, lang}` · `{type:"task", task_id, title}` · `{type:"report_update", status}` | telefon tej osoby |
| `role/{rola}/approve` | `{type:"approval_request", report:{…}}` — tylko przy małej pewności | tablet oficera |
| `ship/{id}/eng/new` | `{type:"approval_request"\|"auto_approved", report}` | oficerowie maszynowni |
| `ship/{id}/bridge/alert` | `{type:"alert", report}` (priorytet 5) | mostek |
| `ship/{id}/events` | każde zdarzenie z rejestru | wszystkie widoki |
| `ship/{id}/sync` (retained) | `{link_up, queue_len, sent:{events, bytes_wire}, audio_bytes_aboard}` | licznik kolejki na ląd |

### Wzorzec po stronie telefonu (martwe strefy)

```ts
// 1. Nagranie -> IndexedDB (Dexie) z ID nadanym na urządzeniu
const rec = { report_id: crypto.randomUUID(), crew_id, recorded_at: new Date().toISOString(), blob, mime: blob.type, tries: 0 };
await db.outbox.add(rec);

// 2. Pętla wysyłki: przy starcie, co 5 s, na 'online' i po powrocie z tła
async function flush() {
  for (const r of await db.outbox.toArray()) {
    const fd = new FormData();
    fd.append("audio", r.blob, "rec");             // Content-Type z blob.type (webm / mp4)
    for (const k of ["report_id", "crew_id", "recorded_at"]) fd.append(k, r[k]);
    try {
      const res = await fetch("/api/reports/audio", { method: "POST", body: fd });
      if (res.status === 200 || res.status === 201) await db.outbox.delete(r.report_id);  // 200 = już było, też OK
      else if (res.status === 409 || res.status === 400) await db.outbox.update(r.report_id, { error: await res.text() });
    } catch { /* brak sieci — spróbujemy później z tym samym report_id */ }
  }
}

// 3. MQTT.js: sesja trwała => zaległe pytania zwrotne przyjdą po powrocie zasięgu
const client = mqtt.connect(`wss://${location.host}/mqtt`, {
  clientId: `phone-${crew_id}`, clean: false, protocolVersion: 5,
  properties: { sessionExpiryInterval: 86400 }, reconnectPeriod: 2000 });
client.on("connect", () => { client.subscribe(`person/${crew_id}`, { qos: 1 }); refetchFromRest(); });
```
- Mikrofon i service worker wymagają HTTPS z **zaufanym** certyfikatem: na telefonie zainstaluj CA z `http://<SERVER_IP>/ca.crt`. Plan awaryjny na Androidzie: `chrome://flags/#unsafely-treat-insecure-origin-as-secure` → `http://<SERVER_IP>`.
- iPhone nagrywa `audio/mp4` — serwer to przyjmuje, nie wymuszaj webm.
- Build: `npm run build` → skopiuj `dist/*` do `pwa-dist/`. W trakcie developmentu zamień w `infra/Caddyfile` blok PWA na `reverse_proxy host.docker.internal:5173`.
