# Basal na surowych vs oczyszczonych wypowiedziach (19.11.2026)

**Pytanie:** czy oczyszczenie wypowiedzi warstwą LLM z gałęzi `moj-llm` (qwen3.5:4b przez Ollamę)
przed modelem decyzyjnym poprawia decyzje Basala?

**Ustawienia**
- Basal 2.0 4.5B MLX-8bit (v2.8.1) na MacBooku. Pytania z `config/questions.yaml`: dział, pilność P1–P3,
  raport DPA, sektor (4 sektory demo), osoba.
- 15 realistycznych wypowiedzi z `config/sample15.yaml`. Pokrywają działy, P1–P3, 3 raporty DPA, 3 role,
  4 sektory, pl/en oraz typowe „brudy” mowy.
- Te same zgłoszenia i etykiety w dwóch wersjach: surowa wypowiedź oraz `tresc` po `przetworz.py`.
  Do qwena trafia tylko tekst i język.
- Uruchomienie: `ENV_DIR=../../../.venv-mlx ./scripts/compare_cleaning_mac.sh`.

## Wyniki

| decyzja | trafność przed | trafność po | automatycznie przed | automatycznie po |
|---|---|---|---|---|
| dział | 80,0% | 66,7% | 60,0% | 60,0% |
| pilność | 60,0% | 66,7% | 100% | 100% |
| raport DPA | 93,3% | 100% | 33,3% | 46,7% |
| sektor | 80,0% | 86,7% | 100% | 100% |
| osoba | 86,7% | 66,7% | 13,3% | 20,0% |
| **razem** | **60/75 (80%)** | **58/75 (77%)** | | |

Oczyszczenie naprawiło 4 decyzje, a zepsuło 6.
- Zgłoszenia w pełni automatyczne: przed 0/15, po 1/15.
- Średnia pewność Basala praktycznie bez zmian.
- Czas: qwen ≈ 4,0 s na zgłoszenie, Basal ≈ 4,4 s (po czyszczeniu 4,6 s).

**Gdzie szkodzi.** Styl urzędowy gubi wskazówki z mowy:
- Wyciek paliwa pod kotłem i raport „trzy rzeczy” trafiły do `deck` zamiast `engine`.
- „Chłopaki skończyli skuwanie rdzy” zmienione na „usunięto rdzę”: zniknęło, kto robi pracę, więc osoba to mechanik zamiast oficera.
- Raz qwen dopisał fakt, którego nie było: „Pilot ladder checked. **No injuries.**”.

**Gdzie pomaga.**
- Wyciek paliwa po czyszczeniu został rozpoznany jako raport DPA.
- Smród rozpuszczalnika w magazynie farb dostał właściwą pilność.
- Puste „nic, wszystko dobrze” oznaczone jako brak treści.

## Wnioski
- Na 15 próbkach różnica (2 decyzje) mieści się w szumie. Czyszczenie nie poprawia decyzji, a kosztuje
  ≈ 4 s na zgłoszenie i potrafi zmienić sens.
- Na teraz Basal dostaje surową wypowiedź. Oczyszczony tekst może służyć ludziom (oficer, TTS,
  dziennik na lądzie), pod warunkiem kontroli dopisanych faktów.
- Do sprawdzenia na pełnym zbiorze: `SETS=realistic` (63 wypowiedzi).
- Niezależnie od czyszczenia: pilność ma tylko 60% trafności, a przy osobie pewność rzadko przekracza próg
  (13–20% automatycznie). To główne miejsca do poprawy pytań i progów.
