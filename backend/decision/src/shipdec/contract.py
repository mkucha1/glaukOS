"""Most między warstwą decyzyjną a wspólnymi kontraktami zespołu (frontend/CLAUDE.md, sekcja 6; src/types.ts).

Kontraktów NIE zmieniamy. Ten moduł tłumaczy odpowiedzi Basala na pola, które już istnieją:
  - ReportForm.priority (1-5, 1 = najpilniejsze; front traktuje P1-P2 jako "wymaga działania")
  - ApprovedPayload.assignee / TaskAssignedPayload.assignee (string; rola jak w `actor` "{role}:{imię}")

Kolejność w backendzie (plan): report.transcribed -> warstwa porządkująca tekst (osobny moduł)
-> decide() na uporządkowanym tekście -> propozycja priorytetu i osoby -> oficer zatwierdza.

DO POTWIERDZENIA Z ZESPOŁEM: mapowanie pilności 1-3 na priorytet 1-5 i nazwy ról spoza `Role` w types.ts.
"""
from __future__ import annotations

from .config import api_questions, load_questions
from .evaluate import predicted_key
from . import settings

# Nasza pilność 1-3 (3 = pilne) -> ReportForm.priority 1-5 (1 = najpilniejsze).
PRIORITY_FROM_PILNOSC = {3: 1, 2: 3, 1: 5}
DPA_PRIORITY = 1  # raport do DPA zawsze na górę (spójne z shipdec/queue.py)

# Klucze `osoba` z config/crew.yaml -> rola w konwencji actor/assignee.
# Pierwsze trzy istnieją w Role (types.ts); pozostałe to propozycja rozszerzenia.
ROLE_FROM_OSOBA = {
    "drugi_mechanik": "2nd_engineer",
    "starszy_mechanik": "chief_engineer",
    "starszy_oficer": "officer",
    "bosman": "bosun",
    "elektryk": "eto",
    "kucharz": "cook",
}


def decide(text: str, backend, questions: dict | None = None, thresholds: dict | None = None) -> dict:
    """Jedno zgłoszenie (sama treść) -> decyzje Basala + pola do kontraktu.

    `backend` to obiekt z metodą decide(state, questions), np. shipdec.backends.BasalHTTP.
    """
    if questions is None or thresholds is None:
        questions, thresholds = load_questions(settings.questions_path())
    resp = backend.decide(text, questions)
    answers = resp["answers"]
    decisions, needs_review = {}, []
    for name, ans in answers.items():
        key = predicted_key(ans)
        conf = float(ans["confidence"])
        decisions[name] = {"value": key, "confidence": round(conf, 4)}
        if conf < thresholds.get(name, thresholds.get("default", 0.8)):
            needs_review.append(name)

    pilnosc = int(decisions["pilnosc"]["value"]) + 1
    dpa = decisions["raport_dpa"]["value"] == "true"
    return {
        "decisions": decisions,                 # surowe odpowiedzi: dzial, pilnosc (klucz 0-2), raport_dpa, osoba
        "needs_review": needs_review,           # pytania poniżej progu -> do zatwierdzenia przez oficera
        "priority": DPA_PRIORITY if dpa else PRIORITY_FROM_PILNOSC[pilnosc],   # -> ReportForm.priority
        "assignee_role": ROLE_FROM_OSOBA.get(decisions["osoba"]["value"], decisions["osoba"]["value"]),
        "department": decisions["dzial"]["value"],
        "dpa_report": dpa,
        "model": resp.get("model"),
        "latency_ms": resp.get("usage", {}).get("latency_ms"),
    }


__all__ = ["decide", "PRIORITY_FROM_PILNOSC", "ROLE_FROM_OSOBA", "api_questions"]
