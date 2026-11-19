# Mózg statku — serwer pokładowy

Serwer, który działa na jednym laptopie na statku, bez internetu. Przyjmuje zgłoszenia od załogi,
zapisuje każdy krok w rejestrze nie do podrobienia, przekazuje je modułom AI zespołu i powiadamia
właściwe osoby. Gdy jest łącze satelitarne, wysyła na ląd sam tekst (nagrania zostają na statku).

Ten folder to **tylko backend**. Strony i aplikację na telefony robicie osobno, korzystając z API opisanego niżej.

---

## 1. Uruchomienie

Są dwa sposoby. Kod serwera jest w obu ten sam, różni się tylko to, kto może się z nim połączyć.

| | A: sam Python | B: Docker |
|---|---|---|
| Do czego | praca nad kodem, test i pokaz przesyłania offline | demo z telefonami (mikrofon wymaga HTTPS) |
| Co trzeba mieć | Python 3.12 | Docker Desktop (+ Git Bash na Windowsie) |
| Miejsce na dysku | ok. 150 MB | kilka GB |
| Powiadomienia | przez SSE (`/api/stream`) | MQTT (Mosquitto) + SSE |

### A: sam Python (5 minut)

Komendy dla Windowsa (PowerShell). Na Macu i Linuksie zamiast `py` wpisz `python3`.

```powershell
py -m pip install -r server/requirements.txt     # raz

# okno 1 — atrapa armatora na lądzie (port 9000)
cd shore
py app.py

# okno 2 — serwer pokładowy (port 8000)
cd server
$env:MQTT_ENABLED="0"        # Mac/Linux: MQTT_ENABLED=0 python3 -m app
py -m app

# okno 3 — sprawdzenie całości
py scripts/e2e_test.py       # na końcu: "WYNIK: WSZYSTKO OK"
```

### B: Docker (demo z telefonami)

```bash
./start.sh 192.168.8.100     # IP laptopa w sieci Wi-Fi demo (na Windowsie podawaj zawsze)
```

Skrypt tworzy certyfikat HTTPS i uruchamia: serwer, Mosquitto (MQTT), atrapę lądu, symulator czujników
i Caddy (HTTPS). Telefon instaluje certyfikat z `http://<IP>/ca.crt`, potem łączy się z `https://<IP>`.
Zbudowaną aplikację wrzucacie do folderu `pwa-dist/`. Zatrzymanie: `docker compose down`.

Krok po kroku dla osoby, która uruchamia to pierwszy raz: dokument „Jak uruchomić serwer pokładowy — przesyłanie offline”.

---

## 2. Jak to działa

Zasada: **serwer niczego nie nadpisuje, tylko dopisuje zdarzenia do rejestru** (`events.db`).
Stan zgłoszenia, kolejka na ląd i powiadomienia wynikają z tej jednej tabeli.

1. **Telefon** nadaje zgłoszeniu własny identyfikator (UUID) i wysyła nagranie. Bez zasięgu ponawia później z tym samym ID; serwer przyjmie je tylko raz.
2. **Serwer** zapisuje nagranie na dysk i dopisuje `report.recorded`.
3. **Pipeline** po kolei woła moduły zespołu i zapisuje każdy wynik:
   Mateusz (mowa → tekst) → Daniel (przerobienie raportu) → Maciej (formularz po angielsku + sprawdzenie z czujnikami).
4. **Pytanie zwrotne:** gdy czegoś brakuje albo czujnik się nie zgadza, pytanie idzie na telefon zgłaszającego; po odpowiedzi analiza rusza dalej.
5. **Zatwierdzenie:** przy małej pewności raport trafia do oficera; przy wysokiej serwer zatwierdza sam i zapisuje powód.
6. **Ląd:** gdy satelita jest włączona, niewysłane zdarzenia idą na ląd jako mały JSON. Nagrania zostają na statku.

Co z tego wynika:
- **Nic nie ginie:** restart w dowolnym momencie — serwer sam dokończy przerwane zgłoszenia.
- **Nic się nie dubluje:** ponowne wysłanie tego samego zgłoszenia albo kroku nie tworzy drugiego wpisu.
- **Pełna historia pod audyt:** zmiany i usuwanie wpisów są zablokowane, a łańcuch skrótów wykrywa ręczne manipulacje (`GET /api/audit/verify`).

---

## 3. Gdzie zespół wkleja swój kod

Każdy edytuje **tylko swój plik** w `server/plugins/` i nie zmienia nazw ani argumentów funkcji.
Do czasu podmiany działają zaślepki, więc cały przepływ działa od początku.

| Kto | Plik | Funkcja |
|---|---|---|
| Mateusz | `server/plugins/stt.py` | `transcribe(audio_path, lang_hint)` → tekst i język |
| Daniel | `server/plugins/refine.py` | `refine(text, lang, context)` → oczyszczony raport |
| Maciej | `server/plugins/brain.py` | `structure`, `check`, `apply_clarification` → formularz, decyzja, pytanie zwrotne |
| Maciej | `server/config/equipment.json`, `server/sim/sensors.py` | urządzenia demo, symulator czujników |

Po zmianie: w sposobie A zrestartuj okno 2, w sposobie B `docker compose restart api`.
Pakiety modułów AI dopisujcie do `server/requirements-ai.txt`.
Plan B na scenie: `USE_STUBS=stt,refine,brain` wraca do zaślepek bez zmiany kodu.

Pełne kontrakty (pola, tematy MQTT, wzorzec offline dla aplikacji): [docs/CONTRACTS.md](docs/CONTRACTS.md).

---

## 4. API w skrócie

Serwer: `http://localhost:8000` (A) albo `https://<IP>` (B). Ląd: `http://localhost:9000` albo `http://<IP>:9000`.

| Co | Wywołanie |
|---|---|
| Czy serwer żyje | `GET /api/health` |
| Wyślij nagranie | `POST /api/reports/audio` (multipart: `audio`, `report_id`, `crew_id`) |
| Wyślij zgłoszenie tekstem | `POST /api/reports/text` `{"report_id", "crew_id", "text"}` |
| Lista zgłoszeń | `GET /api/reports?status=pending_approval` |
| Jedno zgłoszenie z historią | `GET /api/reports/{id}` |
| Odpowiedź na pytanie zwrotne | `POST /api/reports/{id}/clarify` `{"event_id", "text"}` |
| Zatwierdzenie przez oficera | `POST /api/reports/{id}/approve` `{"officer_id", "decision", "assignee"}` |
| Stan kolejki na ląd | `GET /api/sync/status` |
| Satelita ON/OFF | `POST /api/sync/link` `{"up": true}` / `{"up": false}` |
| Powiadomienia na żywo (SSE) | `GET /api/stream?topics=person/marek,role/+/approve` |
| Kontrola rejestru | `GET /api/audit/verify` |
| Co dotarło na ląd | `GET :9000/api/stats`, `GET :9000/api/reports` |

**Pokaz satelity bez żadnej strony** (Git Bash / Mac / Linux):

```bash
curl -X POST localhost:8000/api/sync/link -H "Content-Type: application/json" -d '{"up":false}'   # satelita OFF
curl -X POST localhost:8000/api/reports/text -H "Content-Type: application/json" \
     -d '{"report_id":"11111111-2222-4333-8444-555555555555","crew_id":"marek","text":"Agregat numer jeden, temperatura spalin 380 stopni, wibracje."}'
curl localhost:8000/api/sync/status          # queue_len rośnie (kolejne zgłoszenie = nowy report_id)
curl -X POST localhost:8000/api/sync/link -H "Content-Type: application/json" -d '{"up":true}'    # satelita ON
curl localhost:8000/api/sync/status          # queue_len = 0
curl localhost:9000/api/reports              # zgłoszenie jest na lądzie, po angielsku
```

W PowerShell to samo przez `Invoke-RestMethod`, np.:
`Invoke-RestMethod -Method Post http://localhost:8000/api/sync/link -ContentType application/json -Body '{"up":false}'`

---

## 5. Ustawienia (`.env` albo zmienne środowiskowe)

| Zmienna | Domyślnie | Co robi |
|---|---|---|
| `SERVER_IP` | — | IP laptopa (sposób B, ustawia `start.sh`) |
| `AUTO_APPROVE_CONFIDENCE` | `0.9` | poniżej tej pewności raport idzie do oficera; `1.1` = zawsze oficer |
| `USE_STUBS` | puste | np. `stt,refine,brain` — wymusza zaślepki |
| `SAT_KBPS` | `0` | symulacja wolnego łącza, np. `64` (kbit/s) |
| `MQTT_ENABLED` | `1` | `0` w sposobie A (bez Mosquitto) |
| `SENSOR_SCENARIO` | `demo` | `mismatch` = czujnik się nie zgadza, serwer dopyta |
| `OLLAMA_URL` | `http://ollama:11434` | gdzie moduły szukają modelu językowego |

---

## 6. Testy

```bash
cd server && py -m pytest -q          # testy rdzenia (rejestr, restart, błędy modułów, kolejka)
py scripts/e2e_test.py                # cały scenariusz przez HTTP, serwer musi działać
```

---

## 7. Struktura

```
start.sh                 start sposobem B (Docker)
docker-compose.yml       usługi: api, mosquitto, shore, sensors, caddy (+ ollama opcjonalnie)
.env.example             wzór ustawień
server/
  app/                   serwer: rejestr, pipeline, API, MQTT/SSE, kolejka na ląd
  plugins/               KOD ZESPOŁU: stt.py, refine.py, brain.py (+ _stubs.py)
  config/                załoga i urządzenia demo
  sim/sensors.py         symulator czujników (zaślepka)
  tests/                 testy rdzenia
shore/app.py             atrapa armatora na lądzie (samo API)
infra/                   Caddyfile (HTTPS), mosquitto.conf
scripts/                 certs.sh, e2e_test.py
docs/CONTRACTS.md        kontrakty dla zespołu
```

---

## 8. Najczęstsze problemy

| Objaw | Co zrobić |
|---|---|
| `py` nie jest rozpoznawane | zainstaluj Pythona z opcją „Add python.exe to PATH” albo użyj `python` |
| `queue_len` nie spada mimo satelity ON | atrapa lądu nie działa (okno 1 albo `docker compose ps`) |
| zgłoszenie ma status `failed` | moduł zgłosił błąd; treść w `GET /api/reports/{id}`, po poprawce `POST /api/reports/{id}/retry` |
| telefon nie łączy się z `https://<IP>` | ta sama sieć Wi-Fi? zapora: porty 80, 443, 9000; certyfikat z `/ca.crt` zaufany? |
| `start.sh`: `\r: command not found` | w Git Bash: `sed -i 's/\r$//' start.sh scripts/*.sh` |

Serwer działa w jednym procesie (pipeline i kolejka są w pamięci tego procesu). Na demo nie ma logowania —
osoba to `crew_id` z `server/config/crew.json`.
