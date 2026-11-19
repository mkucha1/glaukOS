# backend/decision — warstwa decyzyjna (Basal)

Środowisko do sprawdzenia, jak model decyzyjny [Basal 2.0](https://github.com/rkinas/basal) (domyślnie `basal-2.0-4.5B`)
rozdziela zgłoszenia załogi statku: **dział**, **priorytet P1–P3 (1 = najwyższy)**, **czy raport do DPA** i **kto ma się zająć**.

**Cel aplikacji: oszczędzać czas załogi przy codziennych raportach.** Groźne, rzadkie zdarzenia obsługują
alarmy i radio, nie aplikacja. Dlatego dane testowe to w ok. 80% raporty rutynowe (obchody, pomiary, wykonane
prace, zapasy), ok. 15% usterki i ok. 5% zdarzenia do raportu DPA (*Designated Person Ashore* — osoba wyznaczona
na lądzie wg Kodeksu ISM).

Priorytet (P1–P3, jak we frontendzie) decyduje o kolejności obsługi i wysyłki na ląd po złapaniu łącza. Nie wymaga zatwierdzania:
pomyłka oznacza tylko trochę późniejszą wysyłkę, a raporty do DPA kod zawsze stawia na początku kolejki.

To jest szkielet: szablony zgłoszeń, generator, ewaluacja i kolejka. Rozbudowujemy go razem.

## Połączenie z serwerem pokładowym (`mozg-statku/`)

```
POST /api/reports/text|audio ─> stt ─> refine (Daniel) ─> brain.structure ─> brain.check ─> oficer / auto
                                                                               │
                                                     plugins/decision.py ──────┘  POST /v1/systemone
                                                     (Basal: dział, pilność,          basal-serve :8001
                                                      raport DPA, osoba)
```

- **Wpięcie:** `mozg-statku/server/plugins/brain.py: check()` — reguły z zaślepki (czujniki, pytania zwrotne)
  plus `plugins/decision.py`, który pyta Basala o **samą treść** zgłoszenia i wypełnia pola `Decision`
  (`mozg-statku/server/app/contracts.py`). Kontrakty bez zmian.
- **Gdy jest pytanie zwrotne,** Basal czeka na odpowiedź człowieka (potem dostaje treść + odpowiedź).
- **Gdy Basal nie odpowiada,** zostaje decyzja z reguł i notatka `basal unavailable` — zgłoszenie idzie dalej.
- **Jedno źródło reguł:** pytania, progi i mapowania są tutaj (`config/`, `src/shipdec/contract.py`);
  `shipdec export-server-config` zapisuje je do `mozg-statku/server/config/decision.json` (test pilnuje aktualności).

| pole `Decision` | skąd | reguła |
|---|---|---|
| `priority` P1–P3 (1 = najwyższy, jak we frontendzie) | pytanie `pilnosc` | pilne → 1, w najbliższych dniach → 2, rutyna → 3; raport DPA → 1 |
| `alarm` | reguły serwera | `true` tylko przy pożarze/dymie → `ship/{id}/bridge/alert`; wtedy P1 i oficer |
| `dept` | pytanie `dzial` | `engine` (→ temat `ship/{id}/eng/new`) albo `deck` (reszta statku pod oficerem) |
| `route_role` | dział | engine → `chief_engineer`, deck → `officer` (role z frontendu) |
| `assignee` | pytanie `osoba` | rola z frontendu → `crew_id` z `crew.json`: 2nd_engineer → tom, chief_engineer → anna, officer → ivan |
| `form.location` | pytanie `sektor` | jeden z 4 sektorów demo: Engine room, Main deck, Galley & mess, Bridge; wpisywana w `structure()`, gdy pewność ≥ 0,5 i nie rozpoznano konkretnego urządzenia |
| `needs_officer` | pewność | `true`, gdy dział/osoba/DPA poniżej progu, niezgodność z czujnikiem albo alarm |

### Uruchomienie razem z serwerem

```bash
# 1. Basal na Macu (środowisko tworzy raz ./scripts/run_on_mac.sh)
./scripts/serve_mac.sh                 # serwer mozg-statku w Pythonie
DOCKER=1 ./scripts/serve_mac.sh        # serwer mozg-statku w Dockerze (BASAL_URL w docker-compose.yml)

# 2. serwer pokładowy (mozg-statku/README.md, tryb A albo B)

# 3. zgłoszenia testowe do serwera
shipdec realistic && shipdec push --data-dir data/realistic --server http://127.0.0.1:8000
shipdec push --limit 20                # syntetyczne
```

Porty: API serwera **8000**, Basal **8001**, Ollama 11434.

## Statek: sektory i załoga

- **Sektory demo:** zgłoszenia trafiają tylko do 4 sektorów przekroju statku z frontendu —
  `engine` (Engine room, z ECR, wirówkami i maszyną sterową), `deck` (Main deck, z dziobem, ładowniami
  i balastem), `galley` (Galley & mess, z kabinami), `bridge` (Bridge). Lokalizacje w danych są po angielsku
  i szczegółowe; `_meta.sector` i etykieta `sektor` to już jeden z 4 (`src/shipdec/ship.py`: `SECTOR_MERGE`).
- **Role** jak we frontendzie (`frontend/src/types.ts`): `2nd_engineer`, `chief_engineer`, `officer` — tylko
  w nich da się zalogować, więc tylko oni zgłaszają i dostają zadania (`config/roster.yaml`: tom, anna, ivan,
  kapitan; ten sam `role` co w `crew.json` serwera, stopień w polu `rank`). Działy: `engine` i `deck`.
- **Kuchnia** jest na przekroju jako pomieszczenie („Galley & mess”), ale nie ma roli — zgłoszenia z kuchni
  (prowiant, chłodnie, odpady) trafiają do oficera albo, gdy trzeba naprawić sprzęt, do maszynowni.
  Elektryka (ETO) też nie ma: sprawy elektryczne przejmuje 2nd_engineer.
- Zgłoszenia są **niezależne** — dane nie zawierają powiązań między zgłoszeniami.

## Konfiguracja (`.env`)

```bash
cp .env.example .env        # adres serwera Basala, model, SHIP_ID (jak VITE_SHIP_ID we frontendzie)
```

Kolejność: zmienna środowiskowa > `.env` > domyślne. `.env` nie trafia do repozytorium.
Wygenerowane dane (`data/synthetic/`, `data/realistic/reports/`) i `results/` też nie — odtwarza się je
poleceniami `shipdec generate` i `shipdec realistic`.

## Struktura

```
config/questions.yaml        pytania do Basala (dzial, pilnosc P1-P3, raport_dpa, sektor, osoba) + progi pewności
config/crew.yaml             role z frontendu do pytania `osoba` -> crew_id z mozg-statku/server/config/crew.json
config/roster.yaml           kto zgłasza: osoby z crew.json w rolach z frontendu
data/templates/reports.yaml  szablony zgłoszeń (80% rutyna), lokalizacje zgodne z sektorami frontendu
data/realistic/utterances.yaml  63 nieczyste wypowiedzi + wzorcowe streszczenia
src/shipdec/                 generate, realistic, evaluate, queue, backends (Basal/atrapa), cli,
                             contract (-> Decision serwera), ship (sektory), server (push), settings (.env)
scripts/                     run_on_mac.sh (ewaluacja), serve_mac.sh (Basal dla serwera), setup/serve (Linux)
tests/                       testy na atrapie (bez GPU), w tym zgodność z frontendem i serwerem
```

## Realistyczne wypowiedzi (`data/realistic/`)

`data/realistic/utterances.yaml` — 63 „nieczyste” wypowiedzi (38 po polsku, 25 po angielsku jako drugim języku):
wypełniacze, autokorekty, kilka tematów naraz, mieszanie języków, liczby słownie, luki rozpoznawania mowy.
Napisane na wzór prawdziwej mowy z transkrypcji nagrań mostka (VDR, NTSB) i typowych raportów „work done”.
**To nie są nagrania prawdziwych marynarzy** — do zastąpienia, gdy je zdobędziemy.

Każda ma `streszczenie_wzorcowe` (do oceny modelu kompresującego), poprawne decyzje i opis trudności.
Zasada etykiet: dział i osoba = **kto musi działać** (naprawić, zamówić, zdecydować), nie kto zgłasza.

```bash
shipdec realistic                           # -> data/realistic/reports/, labels.jsonl, kompresja.jsonl
DATA=realistic ./scripts/run_on_mac.sh      # Basal na surowych wypowiedziach
```

`kompresja.jsonl` to pary {tresc, streszczenie_wzorcowe} dla modelu, który porządkuje wypowiedzi.

## Format zgłoszenia

Każde zgłoszenie to osobny plik `data/.../reports/<report_id>.json` w formacie wejścia serwera
(`POST /api/reports/text`) + metadane w `_meta` (pola z `_` zostają na statku, nie są wysyłane):

```jsonc
{
  "schema_version": "0.2",
  "report_id": "3f0c…",                     // UUID, nadany „na urządzeniu”
  "crew_id": "marek",
  "text": "yyy zęzy w maszynowni wypompowane do zbiornika zęzowego, …",
  "lang": "pl",
  "recorded_at": "2026-11-03T04:12:55+00:00",
  "device": "phone",
  "_meta": {
    "ship": "MV Demo", "ship_id": "demo", "watch": "04-08",
    "reporter": {"crew_id": "marek", "name": "Marek", "role": "motorman", "dept": "engine"},
    "location": "Engine room, lower platform", "sector": "engine",
    "channel": "voice", "audio_s": 14.2
  }
}
```

**Basal dostaje tylko pole `text`** oraz opcje z `config/questions.yaml` (pilnuje tego test).
Poprawne odpowiedzi są w `labels.jsonl` (nie w plikach zgłoszeń) — to też indeks zbioru.
Osoby i statek są fikcyjne.

## Szybki start bez GPU (atrapa modelu)

Sprawdza, czy potok działa. Wyniki atrapy **nic nie mówią** o jakości modelu.

```bash
cd backend/decision
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
shipdec generate -n 200
shipdec evaluate --backend mock
```

## Z prawdziwym Basalem

**Mac z Apple Silicon (zalecane na start) — jedna komenda:**

```bash
./scripts/run_on_mac.sh
```

Instaluje osobne środowisko `.venv-mlx` (Basal v2.8.1 z MLX, bez torch), uruchamia w tle serwer z modelem
`Remek/basal-2.0-4.5B-MLX-8bit` (8-bitowy, ok. 5–6 GB pamięci, pobierany przy pierwszym starcie),
ocenia 50 zgłoszeń i zatrzymuje serwer. Według autora na M4 Pro jedno pytanie zajmuje ok. 0,6 s,
a kilka pytań o to samo zgłoszenie liczy się razem (stan liczony raz).

- `LIMIT=200 ./scripts/run_on_mac.sh` — cały zbiór
- `MODEL=Remek/basal-2.0-mini-MLX-8bit ./scripts/run_on_mac.sh` — model 1.5B, szybszy, dla Maców z 8 GB RAM
- Terminal musi działać natywnie (arm64), nie pod Rosettą.

**Linux/WSL z kartą NVIDIA:**

```bash
./scripts/setup_basal.sh            # torch (CUDA 12.8) + basal + ten projekt + pobranie wag
./scripts/serve_basal.sh            # terminal 1: serwer na :8001
shipdec evaluate --backend basal    # terminal 2
```

Na karcie Hopper/Blackwell: `MODE=fp8 MODEL=Remek/basal-2.0-4.5B-FP8 ./scripts/serve_basal.sh`.
Serwer może też stać na innym komputerze: `shipdec evaluate --url http://<adres>:8001/v1/systemone`.

## Co mierzymy

**Główna miara — zgłoszenia w pełni automatyczne:** odsetek zgłoszeń, w których wszystkie decyzje mają
pewność powyżej progu, więc oficer nie musi nic klikać. Do tego: średnia liczba decyzji do zatwierdzenia
na zgłoszenie i podział na kategorie (rutyna / usterka / zdarzenie).

Dla każdego pytania:

| kolumna | znaczenie |
|---|---|
| trafność | odsetek poprawnych odpowiedzi |
| próg | minimalna pewność, przy której decyzja idzie automatycznie |
| automat | jaki odsetek decyzji przechodzi bez oficera |
| błąd auto | jaki odsetek automatycznych decyzji jest błędny |

Cel: jak najwięcej zgłoszeń w pełni automatycznych przy błędzie wśród nich poniżej ok. 2%.

Kolejka wysyłki dla wyników ewaluacji (reguła w `src/shipdec/queue.py`):

```bash
shipdec queue --results results/basal_basal-2.0-4.5B-MLX-8bit.jsonl
```

## Ważne o Basalu (z dokumentacji)

- Słabo radzi sobie z arytmetyką i dokładnymi progami liczbowymi. Liczby liczymy w kodzie, model podejmuje decyzję na ich podstawie.
- Złożone reguły lepiej rozbić na kilka prostych pytań.
- Zadaje pytanie w dwóch kolejnościach opcji i uśrednia wynik, co zmniejsza wpływ kolejności opcji.
- Każdy model ma pliki kalibracji, ale progi dobieramy na naszych danych.
- Basal 2.x ma opcję `max_error` (model sam się wstrzymuje poniżej certyfikowanego progu) — do sprawdzenia.

## Do zrobienia (następne kroki)

- [ ] Przykłady prawdziwych codziennych raportów od oficerów (zastąpią część szablonów)
- [ ] Więcej szablonów i wariantów (języki załogi, przypadki graniczne, zgłoszenia niejasne)
- [ ] Wykorzystać metadane w regułach poza modelem (np. zgłoszenie z maszynowni w nocy -> wyższy priorytet eskalacji)
- [ ] Szum jak z rozpoznawania mowy (literówki, brak polskich znaków, wtrącenia)
- [ ] Pytanie "kto" zawężone do ról z wybranego działu (dwa kroki)
- [ ] Dobór progów: krzywa pokrycie/błąd dla różnych progów
- [ ] Zestaw testowy od prawdziwych oficerów (zanonimizowany), osobno od syntetycznego
- [ ] Porównanie z innymi modelami (Jev, Kev, mały LLM) na tym samym zbiorze

## Eksperyment: Basal na surowych vs oczyszczonych wypowiedziach (gałąź `cleaning-eval`)

Warstwa porządkująca tekst jest na gałęzi `moj-llm` (`my_folder/przetworz.py`, Ollama + `qwen3.5:4b`).
Z tamtej gałęzi bierzemy **tylko kod** — dane są nasze: `shipdec clean` robi kopię naszego zbioru
z oczyszczoną treścią (`data/<zbiór>_clean`, te same `report_id`, metadane i etykiety; surowa wypowiedź
w `_meta.cleaning.raw_text`). Do warstwy porządkującej idzie tylko tekst i język.

```bash
# obok glaukOS:  git clone -b moj-llm https://github.com/mkucha1/glaukOS.git moj-llm
ollama pull qwen3.5:4b
./scripts/compare_cleaning_mac.sh          # realistyczne (63) + syntetyczne (SYNTH=100), oba warianty
```

Ręcznie: `shipdec clean --data-dir data/realistic --llm-dir ../../../moj-llm/my_folder`, potem
`shipdec evaluate` na obu folderach i `shipdec compare results/A.jsonl results/B.jsonl`
(trafność każdej decyzji, ile zgłoszeń przechodzi automatycznie, przykłady zmian).

## Potok głosowy: nagranie → STT → qwen → Basal (gałąź `voice-pipeline`)

Łączy trzy części, każdą z jej gałęzi, bez kopiowania kodu (foldery obok siebie w `~/Documents/mari`):
`stt/` (gałąź `stt`, `stt/app/pipeline.py`: ffmpeg → DeepFilterNet → faster-whisper), `moj-llm/`
(porządkowanie qwen) i ta gałąź (Basal). Na Macu STT działa na CPU (int8), bo nie ma CUDA — kod STT
jest ten sam, zmieniają się tylko ustawienia. Basal ocenia tekst z STT i tekst po qwenie.

```bash
cd ~/Documents/mari && git clone -b stt https://github.com/mkucha1/glaukOS.git stt
brew install ffmpeg                                   # jeśli nie ma
cd glaukOS/backend/decision
ENV_DIR=../../../.venv-mlx ./scripts/voice_pipeline_mac.sh     # nagrania z ~/Documents/mari/data
```

Wynik: `results/voice/raport.md` (tekst na każdym etapie, decyzje, pewności, czasy).

## Cała aplikacja na Supabase: strona → nagranie → STT → qwen → Basal → strona (gałąź `full-pipeline`)

Kontrakt z `supabase/README.md`. Telefon wysyła audio do Storage i zdarzenie `report.recorded`, a worker
na Macu (`shipdec worker`) co 2 s pyta o nowe nagrania i dopisuje zdarzenia z tym samym `report_id`:

| zdarzenie | kto | treść |
|---|---|---|
| `report.transcribed` | `system:whisper` | `{text, lang}`: tekst z STT (gałąź `stt`), język z qwena |
| `report.structured` | `system:basal` | `ReportForm`: wpis po angielsku (qwen), priorytet P1–P3, sektor (`location`) i **`decision`** z Basala: dział, sugerowane stanowisko i osoba z `crew` (najpierw na dyżurze), raport DPA, pewności |
| `report.clarification_requested` | system | puste nagranie albo brak treści: prośba o powtórzenie |
| `report.clarified` | `system:basal` | po `report.clarification_answered` (tekst albo głos), potem nowy `report.structured` |

Oficer widzi decyzję modelu w szczegółach zgłoszenia (karta „Model decision”). Podpowiedziana osoba jest
wybrana w „Assign to”, a resztę (zatwierdzenie, przydział) robi frontend jak dotąd. Basal ocenia surowy
tekst z STT (eksperyment `cleaning-eval`), a qwen daje czytelny wpis do dziennika.

Uruchomienie na Macu:

```bash
# backend/decision/.env: SUPABASE_URL i SUPABASE_SECRET_KEY (Project Settings -> API Keys, klucz secret)
cd backend/decision && ENV_DIR=../../../.venv-mlx ./scripts/ship_backend_mac.sh       # STT + Basal + worker

# drugi terminal: strona (frontend/.env.local: VITE_BACKEND=supabase + URL + klucz publishable)
cd frontend && npm install && npm run dev                                             # http://localhost:5173
```

Worker na starcie wyłącza `ship_status.autopilot` (scenariusz demo w bazie), a po Ctrl+C włącza go z powrotem.

Stanowiska i działy są jak we frontendzie (`frontend/src/lib/positions.ts`):
- pytanie `dzial`: `engine` / `deck` / `catering`;
- pytanie `osoba`: `chief_engineer`, `2nd_engineer`, `chief_officer`, `bosun`, `chief_cook`.

Dane są przeetykietowane pod te stanowiska.
`integration/` (stary serwer z gałęzi `offline`) zostaje dla porządku, ale nie pasuje już do nowych stanowisk.

### Briefing na zmianę wachty (qwen)

Worker obsługuje też prośby o briefing z tabeli `briefings` (migracja `supabase/migrations/20261119160000_glaukos_briefings.sql`).
Zbiera zgłoszenia widoczne dla osoby, która pyta: zmienione w czasie wybranej wachty i wszystkie wciąż otwarte
(priorytet, status, sektor, kto ma zadanie albo kogo podpowiada Basal, raport DPA, czujnik). qwen
(`src/shipdec/briefing.py`) pisze z tych faktów tekst do odczytania na głos w mniej niż minutę. Gdy worker nie działa,
strona robi briefing z szablonu jak wcześniej.
