"""MACIEJ — warstwa decyzyjna: model Basal (https://github.com/rkinas/basal) jako "semantyczny if".

Dla treści zgłoszenia pyta lokalny serwer `basal-serve` (POST /v1/systemone) o dział, pilność,
raport do DPA, sektor statku i osobę. Sektor trafia do formularza (`location` = etykieta sektora
z frontendu, gdy nie rozpoznano konkretnego urządzenia), reszta do pól Decision (app/contracts.py).
Basal jest pytany raz, w structure(); check() używa tych samych odpowiedzi, dopóki treść się nie zmieni
(po pytaniu zwrotnym pyta ponownie).
Reguły i pytania: config/decision.json — generowane z backend/decision (`shipdec export-server-config`),
żeby ewaluacja i serwer używały dokładnie tego samego.

Zmienne środowiskowe:
  BASAL_URL          domyślnie http://127.0.0.1:8001/v1/systemone (basal-serve na 8001, bo API serwera to 8000)
                     Docker na Macu/Windowsie: http://host.docker.internal:8001/v1/systemone
  BASAL_TIMEOUT      sekundy, domyślnie 30
  DECISION_ENABLED   "0" wyłącza warstwę (zostaje decyzja z zaślepki)

Tylko biblioteka standardowa — obraz serwera nie potrzebuje nowych pakietów.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(os.getenv("CONFIG_DIR", Path(__file__).resolve().parents[1] / "config")) / "decision.json"
_config: dict | None = None


def config() -> dict:
    global _config
    if _config is None:
        _config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return _config


def enabled() -> bool:
    return os.getenv("DECISION_ENABLED", "1") != "0" and CONFIG_PATH.exists()


def ask_basal(text: str) -> dict:
    """Zwraca `answers` z Basala: {pytanie: {"probabilities": {...}, "confidence": p, ...}}."""
    url = os.getenv("BASAL_URL", "http://127.0.0.1:8001/v1/systemone")
    body = json.dumps({"state": text, "questions": config()["questions"]}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=float(os.getenv("BASAL_TIMEOUT", "30"))) as r:
        return json.loads(r.read())["answers"]


def to_decision(answers: dict) -> dict:
    """Te same reguły co backend/decision/src/shipdec/contract.py: to_decision()."""
    cfg = config()
    thr = cfg["thresholds"]
    picked, needs_review = {}, []
    for name, ans in answers.items():
        probs = ans["probabilities"]
        key = max(probs, key=probs.get)
        conf = float(ans["confidence"])
        picked[name] = {"value": key, "confidence": round(conf, 4)}
        if conf < thr.get(name, thr.get("default", 0.8)):
            needs_review.append(name)
    dept = picked["dzial"]["value"]
    level = int(picked["pilnosc"]["value"]) + 1          # poziom Basala 1..3 (1 = najniższy)
    dpa = picked["raport_dpa"]["value"] == "true"
    role = picked["osoba"]["value"]
    return {
        "priority": cfg["dpa_priority"] if dpa else cfg["priority_from_level"][str(level)],  # P1 = najwyższy
        "dept": dept,
        "route_role": cfg["route_role"].get(dept, "chief_engineer"),
        "assignee": cfg["assignee"].get(role),
        "sector": picked["sektor"]["value"] if "sektor" in picked else None,
        "needs_officer": bool(needs_review),
        "notes": [f"basal: {n}={v['value']} ({v['confidence']:.2f})" for n, v in picked.items()],
        "_basal": {"decisions": picked, "needs_review": needs_review, "dpa_report": dpa, "assignee_role": role},
    }


def annotate_form(form: dict) -> dict:
    """Pyta Basala o treść formularza i zapamiętuje odpowiedzi w polach wewnętrznych (zostają na statku).

    Sektor: gdy reguły nie rozpoznały konkretnego urządzenia (`_equipment_id`), a Basal jest dość pewny,
    `location` = etykieta sektora z frontendu (np. "Bow & mooring") — frontend (sectorOf) stawia
    zgłoszenie w tym miejscu przekroju statku.
    """
    text = form.get("_text") or ""
    if not text.strip():
        return form
    answers = ask_basal(text)
    out = dict(form)
    out["_basal_answers"], out["_basal_for"] = answers, text
    sec = answers.get("sektor")
    if sec:
        probs = sec["probabilities"]
        key = max(probs, key=probs.get)
        cfg = config()
        out["_sector"] = key
        if float(sec["confidence"]) >= cfg.get("sector_min_conf", 0.5) and not form.get("_equipment_id"):
            out["location"] = cfg["sector_labels"][key]
    return out


def cached_answers(form: dict) -> dict | None:
    """Odpowiedzi Basala z structure(), jeśli dotyczą bieżącej treści."""
    if form.get("_basal_answers") and form.get("_basal_for") == form.get("_text"):
        return form["_basal_answers"]
    return None


def merge(decision: dict, text: str, answers: dict | None = None) -> dict:
    """Uzupełnia decyzję z reguł (czujniki, pytania zwrotne, alarm) o decyzję Basala.

    Nie rusza decyzji, gdy jest pytanie zwrotne (najpierw odpowiedź człowieka).
    Zachowuje: alarm z reguł (P1, oficer, ship/{id}/bridge/alert), sprawdzenia czujników
    i niezgodność z czujnikiem (wtedy zawsze oficer — needs_officer nadpisuje w serwerze ten warunek).
    """
    if decision.get("clarification") is not None or not text.strip():
        return decision
    b = to_decision(answers if answers is not None else ask_basal(text))
    out = dict(decision)
    alarm = bool(decision.get("alarm"))
    out["alarm"] = alarm
    out["priority"] = 1 if alarm else b["priority"]
    out["dept"] = b["dept"]
    out["route_role"] = "officer" if alarm else b["route_role"]
    out["assignee"] = b["assignee"]
    sensor_mismatch = any(c.get("ok") is False for c in decision.get("checks") or [])
    out["needs_officer"] = b["needs_officer"] or sensor_mismatch or alarm
    out["notes"] = list(decision.get("notes") or []) + b["notes"]
    out["_basal"] = b["_basal"]
    return out
