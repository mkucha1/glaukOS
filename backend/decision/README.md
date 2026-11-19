# backend/decision — warstwa decyzyjna (Basal)

Środowisko do sprawdzenia, jak model decyzyjny [Basal 2.0](https://github.com/rkinas/basal) (domyślnie `basal-2.0-4.5B`)
rozdziela zgłoszenia załogi statku: **dział**, **pilność (1–3)**, **czy raport do DPA** i **kto ma się zająć**.

**Cel aplikacji: oszczędzać czas załogi przy codziennych raportach.** Groźne, rzadkie zdarzenia obsługują
alarmy i radio, nie aplikacja. Dlatego dane testowe to w ok. 80% raporty rutynowe (obchody, pomiary, wykonane
prace, zapasy), ok. 15% usterki i ok. 5% zdarzenia do raportu DPA (*Designated Person Ashore* — osoba wyznaczona
na lądzie wg Kodeksu ISM).

Pilność (1–3) decyduje o kolejności obsługi i wysyłki na ląd po złapaniu łącza. Nie wymaga zatwierdzania:
pomyłka oznacza tylko trochę późniejszą wysyłkę, a raporty do DPA kod zawsze stawia na początku kolejki.

To jest szkielet: szablony zgłoszeń, generator, ewaluacja i kolejka. Rozbudowujemy go razem.

## Miejsce w systemie Mózg statku

```
report.transcribed ──> warstwa porządkująca tekst ──> decide() (ten moduł) ──> propozycja dla oficera
   (speech/)            (osobny moduł backendu)        dział, pilność,         ReportForm.priority,
                                                       raport DPA, osoba       assignee
```

Model dostaje **tylko treść** zgłoszenia i zamkniętą listę opcji; zwraca wybór i pewność.
Poniżej progu pewności decyzja trafia do zatwierdzenia przez oficera (`needs_review`).
Wspólnych kontraktów (`frontend/CLAUDE.md` sekcja 6, `frontend/src/types.ts`) nie zmieniamy —
tłumaczy na nie `src/shipdec/contract.py`:

| nasze pole | kontrakt | mapowanie (do potwierdzenia z zespołem) |
|---|---|---|
| pilność 1–3 (3 = pilne) | `ReportForm.priority` 1–5 (1 = najpilniejsze) | 3→1, 2→3, 1→5; raport DPA → 1 |
| osoba | `assignee` (rola jak w `actor`) | drugi_mechanik→`2nd_engineer`, starszy_mechanik→`chief_engineer`, starszy_oficer→`officer`, bosman→`bosun`, elektryk→`eto`, kucharz→`cook` |

```python
from shipdec.backends import get_backend
from shipdec.contract import decide
out = decide("Pompa chłodzenia nr 2, przeciek na uszczelnieniu", get_backend("basal"))
# out["priority"], out["assignee_role"], out["needs_review"], out["decisions"]
```

## Konfiguracja (`.env`)

```bash
cp .env.example .env        # adres serwera Basala, model, SHIP_ID (jak VITE_SHIP_ID we frontendzie)
```

Kolejność: zmienna środowiskowa > `.env` > domyślne. `.env` nie trafia do repozytorium.
Wygenerowane dane (`data/synthetic/`, `data/realistic/reports/`) i `results/` też nie — odtwarza się je
poleceniami `shipdec generate` i `shipdec realistic`.

## Struktura

```
config/questions.yaml        pytania do modelu (format API /v1/systemone) + progi pewności
config/crew.yaml             role na statku (odpowiedzi na pytanie "kto")
config/roster.yaml           fikcyjna załoga i statek (źródło metadanych "kto zgłosił")
data/templates/reports.yaml  szablony zgłoszeń z poprawnymi odpowiedziami (gold)
data/synthetic/reports/      wygenerowane zgłoszenia, jeden plik JSON na zgłoszenie
data/synthetic/labels.jsonl  poprawne odpowiedzi do ewaluacji (osobno od zgłoszeń)
results/                     wyniki modelu + podsumowanie
src/shipdec/                 generator, backendy (Basal / atrapa), ewaluacja, CLI
scripts/                     instalacja i start serwera Basala
tests/                       testy potoku na atrapie (bez GPU)
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

Każde zgłoszenie to osobny plik `data/synthetic/reports/<id>.json`, tak jakby przyszło z aplikacji:

```json
{
  "schema_version": "0.1",
  "id": "ZGL-20261110-0018",
  "statek": "MV Odra Trader",
  "czas_utc": "2026-11-10T18:17:57+00:00",
  "wachta": "16-20",
  "zglaszajacy": {"id": "C04", "imie_nazwisko": "Rajesh Nair", "stanowisko": "trzeci oficer", "dzial": "pokład"},
  "lokalizacja": "pokład rufowy",
  "kanal": "glos",
  "urzadzenie": "telefon",
  "jezyk": "en",
  "nagranie_s": 6.2,
  "tresc": "Mooring line on the stern is badly worn, it almost snapped during berthing."
}
```

**Basal dostaje tylko pole `tresc`** oraz opcje z `config/questions.yaml`. Metadane nie trafiają do modelu
(pilnuje tego test `test_model_gets_only_report_text`). Poprawne odpowiedzi są w `labels.jsonl`, nie w plikach
zgłoszeń — ten plik jest też indeksem: ewaluacja bierze tylko zgłoszenia w nim wymienione.
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
./scripts/serve_basal.sh            # terminal 1: serwer na :8000
shipdec evaluate --backend basal    # terminal 2
```

Na karcie Hopper/Blackwell: `MODE=fp8 MODEL=Remek/basal-2.0-4.5B-FP8 ./scripts/serve_basal.sh`.
Serwer może też stać na innym komputerze: `shipdec evaluate --url http://<adres>:8000/v1/systemone`.

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
