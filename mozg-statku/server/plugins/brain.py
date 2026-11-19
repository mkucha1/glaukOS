"""MACIEJ — model decyzyjny: LLM (Ollama) do strukturyzacji + tłumaczenia, reguły w Pythonie.

KONTRAKT (nie zmieniaj sygnatur). Wszystkie funkcje dostają `context`:
    context = {
        "report_id": "...",
        "crew": {"crew_id": "marek", "role": "motorman", "lang": "pl", ...} | {},
        "equipment": <zawartość config/equipment.json>,
        "round": 0,                       # 0 = pierwsza analiza, 1+ = po pytaniu zwrotnym
        "ollama_url": "http://ollama:11434",
    }

1) structure(text, lang, context) -> dict  (formularz, patrz app/contracts.py: ReportForm)
     {"equipment": "Cooling water pump No. 2", "sfi_code": "721", "parameter": "discharge pressure",
      "value": 1.8, "unit": "bar", "defect": "leak at mechanical seal", "priority": 4,
      "location": "...", "action_taken": "none", "text_en": "...", "lang_original": "pl",
      "missing_fields": [], "confidence": 0.86}
     Pola zaczynające się od "_" (np. "_equipment_id") są wewnętrzne: zostają na statku,
     nie idą na ląd — możesz w nich trzymać stan pomocniczy.

2) check(form, sensors, context) -> dict  (decyzja, patrz contracts.Decision)
     sensors.get("CW_PUMP_2_P") -> {"tag", "value", "unit", "ts", "age_s"} | None
     sensors.all() -> {tag: reading}
     {"priority": 4, "route_role": "chief_engineer", "dept": "engine",
      "checks": [{"tag": "CW_PUMP_2_P", "reported": 1.8, "measured": 1.9, "unit": "bar", "tolerance": 0.3, "ok": true}],
      "clarification": None | {"question": "Pompa numer jeden czy numer dwa?", "lang": "pl",
                               "question_en": "Pump number one or two?", "field": "equipment_no"}}
     Gdy jest "clarification" -> serwer wysyła pytanie na person/{crew_id} i czeka na odpowiedź.
     route_role decyduje o temacie role/{route_role}/approve; priority 5 -> alert na mostek.

3) apply_clarification(form, clarification, answer_text, answer_lang, context) -> dict (nowy formularz)
     Po nim serwer automatycznie woła check() jeszcze raz (max MAX_CLARIFY_ROUNDS rund).
"""
from __future__ import annotations

from typing import Any

from plugins import _stubs


def structure(text: str, lang: str, context: dict) -> dict:
    # ====== MACIEJ: tu Ollama + JSON schema (format=ReportForm.model_json_schema()) ======
    return _stubs.brain_structure(text, lang, context)


def check(form: dict, sensors: Any, context: dict) -> dict:
    # ====== MACIEJ: reguły: progi zgodności z czujnikiem, brakujące pola, priorytet, routing ======
    return _stubs.brain_check(form, sensors, context)


def apply_clarification(form: dict, clarification: dict, answer_text: str,
                        answer_lang: str, context: dict) -> dict:
    # ====== MACIEJ: wpleć odpowiedź do formularza (LLM albo reguły) ======
    return _stubs.brain_apply_clarification(form, clarification, answer_text, answer_lang, context)
