"""Wczytywanie konfiguracji i budowa zapytania do API /v1/systemone."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_crew(path: str | Path = ROOT / "config" / "crew.yaml") -> dict:
    return load_yaml(path)["crew"]


def load_questions(path: str | Path = ROOT / "config" / "questions.yaml",
                   crew: dict | None = None) -> tuple[dict, dict]:
    """Zwraca (pytania w formacie API, progi pewności)."""
    cfg = load_yaml(path)
    crew = crew if crew is not None else load_crew()
    questions = {}
    for name, q in cfg["questions"].items():
        q = dict(q)
        if q.pop("criteria_from", None) == "crew":
            q["criteria"] = {role: d["opis"] for role, d in crew.items()}
        questions[name] = q
    return questions, cfg.get("thresholds", {"default": 0.8})


# Pola pytań, które są tylko dla nas (ewaluacja) i nie trafiają do modelu.
LOCAL_KEYS = {"gold_map"}


def api_questions(questions: dict) -> dict:
    """Pytania w postaci wysyłanej do Basala (bez pól pomocniczych)."""
    return {n: {k: v for k, v in q.items() if k not in LOCAL_KEYS} for n, q in questions.items()}


def gold_key(question: dict, value) -> str:
    """Zamienia etykietę gold na klucz odpowiedzi zwracany przez Basala."""
    if question["type"] == "noul":
        return "true" if value else "false"
    if question["type"] == "score":
        value = question.get("gold_map", {}).get(value, value)  # np. skala 1-5 z szablonów -> 1-3
        return str(int(value) - 1)  # poziom 1..N -> klucze "0".."N-1"
    return str(value)
