"""Most między warstwą decyzyjną a serwerem pokładowym (mozg-statku/server, gałąź offline).

Serwer woła plugin `server/plugins/brain.py: check(form, sensors, context) -> Decision`
(model: mozg-statku/server/app/contracts.py). Basal wypełnia w nim:
  - priority     1-3 jak we frontendzie: 1 = najwyższy (P1). Raport do DPA zawsze P1.
                 Alarm na mostek to osobna flaga `alarm` z reguł (pożar, dym), nie priorytet.
  - dept         "engine" (-> temat ship/{id}/eng/new) albo "deck" (reszta statku pod oficerem)
  - route_role   kto zatwierdza -> temat role/{route_role}/approve; role z frontendu
  - assignee     crew_id z server/config/crew.json — komu przydzielić zadanie przy auto-zatwierdzeniu
  - needs_officer True, gdy któraś decyzja ma pewność poniżej progu (priorytet nie jest bramkowany)

Ten moduł jest jedynym źródłem tych reguł: `shipdec export-server-config` zapisuje je do
mozg-statku/server/config/decision.json, który czyta plugin serwera (bez zależności od tego pakietu).

"""
from __future__ import annotations

import json
from pathlib import Path

from .ship import MAIN_SECTORS, SECTOR_LABELS
from . import settings
from .config import ROOT, api_questions, load_crew, load_questions
from .evaluate import predicted_key

# Poziom ze skali Basala (pytanie `pilnosc`, 1 = najniższy) -> priorytet P (1 = najwyższy, jak we frontendzie).
PRIORITY_FROM_LEVEL = {1: 3, 2: 2, 3: 1}
DPA_PRIORITY = 1                     # raport do DPA na górę kolejki (ale to nie alarm na mostek)
# Kto zatwierdza dział (positions.approves w Supabase): kuchnię zatwierdza chief_officer.
ROUTE_ROLE = {"engine": "chief_engineer", "deck": "chief_officer", "catering": "chief_officer"}
SECTOR_MIN_CONF = 0.5   # od tej pewności serwer wpisuje sektor do formularza (location), inaczej zostaje z reguł
# Serwer zespołu (gałąź `offline`) — gdy go nie ma w repo, kopia w integration/mozg-statku/.
_SERVER_CONFIG_DIR = ROOT.parents[1] / "mozg-statku" / "server" / "config"
SERVER_CONFIG = (_SERVER_CONFIG_DIR if _SERVER_CONFIG_DIR.is_dir() else ROOT / "integration" / "mozg-statku") / "decision.json"


def assignees() -> dict[str, str]:
    """rola (klucz pytania `osoba`) -> crew_id."""
    return {role: d["crew_id"] for role, d in load_crew().items() if d.get("crew_id")}


def to_decision(answers: dict, thresholds: dict, assignee_by_role: dict[str, str] | None = None) -> dict:
    """Odpowiedzi Basala (`answers` z /v1/systemone) -> pola Decision serwera."""
    assignee_by_role = assignee_by_role or assignees()
    picked, needs_review = {}, []
    for name, ans in answers.items():
        key = predicted_key(ans)
        conf = float(ans["confidence"])
        picked[name] = {"value": key, "confidence": round(conf, 4)}
        if conf < thresholds.get(name, thresholds.get("default", 0.8)):
            needs_review.append(name)
    dept = picked["dzial"]["value"]
    level = int(picked["pilnosc"]["value"]) + 1
    dpa = picked["raport_dpa"]["value"] == "true"
    role = picked["osoba"]["value"]
    return {
        "priority": DPA_PRIORITY if dpa else PRIORITY_FROM_LEVEL[level],
        "dept": dept,
        "route_role": ROUTE_ROLE.get(dept, "chief_engineer"),
        "assignee": assignee_by_role.get(role),
        "sector": picked["sektor"]["value"] if "sektor" in picked else None,
        "needs_officer": bool(needs_review),
        "notes": [f"basal: {n}={v['value']} ({v['confidence']:.2f})" for n, v in picked.items()],
        "_basal": {"decisions": picked, "needs_review": needs_review, "dpa_report": dpa, "assignee_role": role},
    }


def decide(text: str, backend, questions: dict | None = None, thresholds: dict | None = None) -> dict:
    """Jedno zgłoszenie (sama treść) -> pola Decision. `backend` ma metodę decide(state, questions)."""
    if questions is None or thresholds is None:
        questions, thresholds = load_questions(settings.questions_path())
    return to_decision(backend.decide(text, questions)["answers"], thresholds)


def server_config() -> dict:
    questions, thresholds = load_questions(settings.questions_path())
    return {
        "_note": "Wygenerowane: cd backend/decision && shipdec export-server-config. Nie edytuj ręcznie.",
        "questions": api_questions(questions),
        "thresholds": thresholds,
        "priority_from_level": {str(k): v for k, v in PRIORITY_FROM_LEVEL.items()},
        "dpa_priority": DPA_PRIORITY,
        "route_role": ROUTE_ROLE,
        "assignee": assignees(),
        "sector_labels": {k: SECTOR_LABELS[k] for k in MAIN_SECTORS},
        "sector_min_conf": SECTOR_MIN_CONF,
    }


def export_server_config(path: str | Path = SERVER_CONFIG) -> Path:
    path = Path(path)
    path.write_text(json.dumps(server_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
