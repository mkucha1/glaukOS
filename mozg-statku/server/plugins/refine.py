"""DANIEL — przerobienie raportu: z surowej transkrypcji robi czysty tekst zgłoszenia.

Krok między mową na tekst (Mateusz) a strukturyzacją (Maciej):
    report.transcribed  ->  refine()  ->  report.refined  ->  brain.structure()

KONTRAKT (nie zmieniaj sygnatury):
    refine(text: str, lang: str, context: dict) -> dict
        text     surowa transkrypcja z Whispera, np. "yyy no pompa chłodzenia eee ciśnienie spada do jeden przecinek osiem bara"
        lang     język wykryty przez STT ("pl", "en", ...)
        context  {"report_id", "crew": {...}, "equipment": config/equipment.json, "ollama_url"}
    zwraca:
        {"text": "Pompa chłodzenia, ciśnienie spada do 1,8 bara.", "lang": "pl",
         ... dowolne dodatkowe pola, np. "changes": ["usunięto wtrącenia", "liczby słownie -> cyfry"]}

Pomysły: usunięcie wtrąceń i powtórzeń, liczby słownie -> cyfry, poprawa terminów morskich
(słownik z equipment.json), interpunkcja. Oryginał zostaje w rejestrze (report.transcribed) pod audyt.
Wołane w wątku, raz na zgłoszenie. Wyjątek -> 2 ponowienia -> report.failed.
"""
from __future__ import annotations

from plugins import _stubs


def refine(text: str, lang: str, context: dict) -> dict:
    # ====== DANIEL: zastąp tę linię swoim kodem (reguły albo LLM przez Ollamę) ======
    return _stubs.refine_text(text, lang, context)
