"""Ustawienia z backend/decision/.env (oraz zmiennych środowiskowych, które mają pierwszeństwo).

Bez zależności: prosty parser KEY=VALUE, komentarze '#', puste linie pomijane.
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT

ENV_FILE = ROOT / ".env"

DEFAULTS = {
    "SHIP_ID": "demo",
    "BASAL_URL": "http://127.0.0.1:8001/v1/systemone",
    "BASAL_TIMEOUT": "600",
    "BASAL_MODEL": "Remek/basal-2.0-4.5B-MLX-8bit",
    "DECISION_QUESTIONS": "config/questions.yaml",
}


def read_env_file(path: str | Path = ENV_FILE) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def get(key: str) -> str:
    """Kolejność: zmienna środowiskowa > .env > wartość domyślna."""
    return os.environ.get(key) or read_env_file().get(key) or DEFAULTS.get(key, "")


def questions_path() -> Path:
    p = Path(get("DECISION_QUESTIONS"))
    return p if p.is_absolute() else ROOT / p
