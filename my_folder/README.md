# Warstwa porządkująca tekst: STT → zgłoszenie dla modelu decyzyjnego

```
[Moduł STT] ──POST /parse──▶ [app.py (lokalny LLM)] ──zgłoszenie JSON──▶ [Model decyzyjny (Basal)]
                              porządkuje wypowiedź                      dział, pilność, DPA, osoba
```

To jest „warstwa porządkująca tekst” z `github/backend/decision/README.md`. **Nie podejmuje decyzji.**
Dział, pilność, raport do DPA i osobę ustala model decyzyjny. Tutaj tylko:

- usuwamy wypełniacze, powtórzenia i autokorekty („dwójka, znaczy dwa lewy” → „2 lewy”),
- zamieniamy liczby mówione na cyfry („trzysta osiemdziesiąt wolt” → „380 V”),
- zostawiamy **te same informacje co w nagraniu** jako 1–3 proste zdania: zwykły tekst bez list i formatowania,
  łatwy do przeczytania i do odczytu przez TTS.

Ten tekst trafia do pola `tresc`, które jako **jedyne** czyta model decyzyjny.

## Uruchomienie

```bash
pip install -r requirements.txt
```

Potrzebny jest tylko lokalny LLM (Ollama z modelem `qwen3.5:4b`). Serwera `app.py` nie trzeba uruchamiać.

**Jeden JSON z STT → JSON dla modelu decyzyjnego** (`przetworz.py`):

```bash
python przetworz.py wejscie.json                 # wynik -> wejscie_wynik.json
python przetworz.py wejscie.json -o wynik.json   # wynik -> wynik.json
python przetworz.py - < wejscie.json             # stdin -> stdout (do potoków)
python przetworz.py --text "yyy pompa numer dwa cieknie"
```

Z kodu w Pythonie: `from przetworz import przetworz; wynik = przetworz({"text": "..."})`.

**Cały folder** (`przetworz_folder.py`): każdy `*.json` z `reports/` trafia do `wyniki_reports/` pod tą samą nazwą.

```bash
python przetworz_folder.py                         # reports/ -> wyniki_reports/
python przetworz_folder.py moje_reports -o moje_wyniki
python przetworz_folder.py --pomin-gotowe          # tylko pliki, które nie mają jeszcze wyniku
```

Przykładowe wejścia: `reports/` (63 zgłoszenia z projektu decyzyjnego, pole `tresc` = surowa wypowiedź)
oraz `przyklady_wejscia/` (minimalny JSON z samym `text`).

**Opcjonalnie jako serwer HTTP** (gdy moduł STT ma wysyłać `POST /parse`):

```bash
python app.py                     # port 8010 (8000 zajmuje serwer Basala)
```

Oba skrypty mogą też wysyłać zapytania do działającego serwera: `--url http://127.0.0.1:8010`.

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | serwer zgodny z OpenAI API (Ollama, llama.cpp, vLLM, LM Studio) |
| `LLM_MODEL` | `qwen3.5:4b` | nazwa modelu |
| `LLM_REASONING_EFFORT` | `none` | wyłącza „thinking” (≈1 s zamiast ≈30 s). Pusty = nie wysyłaj parametru |
| `SUMMARY_LANGUAGE` | `auto` | `auto` = język mówiącego (jak `streszczenie_wzorcowe` w projekcie decyzyjnym); `en` / `pl` = wymuś |
| `SHIP_NAME` | – | `statek` w zgłoszeniu, jeśli STT go nie poda |
| `DECISION_URL` | – | jeśli ustawione, każde zgłoszenie jest też wysyłane POST-em do modelu decyzyjnego |
| `LLM_MOCK` | `0` | `1` = bez LLM, proste czyszczenie (testy integracji) |
| `PORT` / `HOST` | `8010` / `0.0.0.0` | |

## Wejście (z modułu STT / aplikacji)

`POST /parse`, JSON. Wymagany jest tylko tekst: `text` (albo `tresc` / `transcript` / `transcription`).

```json
{"text": "kurde znowu kapie z tej pompy chłodzenia, numer dwa, wytarłem i podstawiłem tackę", "stt_confidence": 0.9}
```

Można też wysłać od razu całe zgłoszenie z aplikacji (format projektu decyzyjnego). Metadane
(`id`, `statek`, `czas_utc`, `wachta`, `zglaszajacy`, `lokalizacja`, `kanal`, `urzadzenie`, `nagranie_s`)
przechodzą bez zmian. Brakujące uzupełniamy: `id` generujemy, `czas_utc` to chwila odbioru, `wachta` liczymy z godziny.

Najprostszy STT może wysłać sam tekst: `POST /parse/text`, `Content-Type: text/plain`.

## Wyjście = zgłoszenie dla modelu decyzyjnego (`schema_version` 0.1)

```json
{
  "schema_version": "0.1",
  "id": "REAL-p06",
  "statek": "MV Odra Trader",
  "czas_utc": "2026-11-02T10:26:03+00:00",
  "wachta": "08-12",
  "zglaszajacy": {"id": "C13", "imie_nazwisko": "Piotr Wójcik", "stanowisko": "motorzysta", "dzial": "maszynownia"},
  "lokalizacja": "przedział pomp",
  "kanal": "glos",
  "urzadzenie": "telefon",
  "jezyk": "pl",
  "nagranie_s": 15.8,
  "tresc": "Pompa chłodzenia nr 2: pod spodem powstała kałuża. Wytarto podłogę i podstawiono tackę. Uszczelnienie wymaga sprawdzenia, ponieważ przeciek nasila się.",
  "tresc_surowa": "kurde znowu kapie z tej pompy chłodzenia, numer dwa, pod spodem kałuża, wytarłem i podstawiłem tackę, ale ktoś musi zobaczyć uszczelnienie bo się robi coraz gorzej",
  "niejednoznaczne": false,
  "porzadkowanie": {"wersja": "2.0", "model": "qwen3.5:4b", "czas_ms": 1085, "proby": 1, "stt_pewnosc": null}
}
```

- Pola do `tresc` włącznie mają dokładnie ten format, co zgłoszenia w `github/backend/decision`.
- `tresc_surowa`, `niejednoznaczne` i `porzadkowanie` dodaje ta warstwa. Model decyzyjny ich nie czyta, a jego loader je ignoruje.
- `niejednoznaczne: true` oznacza, że wypowiedź nie ma konkretnej treści („yyy nic, wszystko dobrze”). Wtedy
  `tresc` = „Brak konkretnej treści — dopytać zgłaszającego…”, jak w streszczeniach wzorcowych.
- Pełny JSON Schema: `GET /schema`. Błędy: `422` złe wejście, `502` LLM zwrócił zły JSON, `503` LLM nieosiągalny.

Przykłady: **`przyklady_dla_modelu_decyzyjnego.txt`** zawiera 73 zgłoszenia w tym formacie (tablica JSON):
63 wypowiedzi z `github/backend/decision/data/realistic/utterances.yaml` i 10 z `przyklady_stt.txt`.
Sprawdzone kodem projektu decyzyjnego: `shipdec.contract.decide()` i `shipdec.evaluate.run()` przyjmują je bez zmian.

## Kontrole jakości w kodzie (po odpowiedzi LLM)

Mały model (4B) czasem zmienia sens. Gdy kod wykryje któryś z tych błędów, model dostaje jedną poprawkę z opisem błędu:
- zgubione kluczowe słowo z nagrania (zęza, balast, kingston, maszynownia, trap, chief, kapitan…)
  albo kalka, której nie było w nagraniu („bilgowy”, „zębowy” zamiast „zęzowy”),
- numer urządzenia („nr 10”), którego nikt nie wypowiedział,
- tekst w innym języku niż `jezyk` z STT/metadanych,
- konkretna wypowiedź oznaczona jako „niejednoznaczne”.

Na 63 wypowiedziach z projektu decyzyjnego: 0 naruszeń kontraktu, 0 błędów języka, 0 wymyślonych numerów,
56 z 62 liczb ze streszczeń wzorcowych obecnych w `tresc`. Znane słabości modelu 4B: miejscami kulawa
polszczyzna i pojedyncze pomyłki trybu („wymieniono” zamiast „do wymiany”). Większy model przez `LLM_MODEL` to poprawi.

## Pozostałe pliki

- `dane/realistyczne_wypowiedzi.jsonl`: 63 wypowiedzi z projektu decyzyjnego razem z `streszczenie_wzorcowe`
  (wygenerowane jego funkcją `shipdec.realistic.build()`), do ręcznego porównania jakości `tresc` ze wzorcem.
- `przyklady_stt.txt`: 10 przykładowych wypowiedzi, jedna na linię.

Przy `--url` na Windows używaj `127.0.0.1` zamiast `localhost` (`localhost` dokłada ~2 s do każdego żądania).
