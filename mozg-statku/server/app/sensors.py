"""Pamięć podręczna ostatnich odczytów czujników (tylko do odczytu — nic nie steruje maszynami).

Źródła: MQTT ship/{id}/sensors/{tag} (symulator Macieja) albo HTTP POST /api/sensors (fallback).
Format wiadomości (styl Vessel Insight): {"tag": "CW_PUMP_2_P", "value": 1.9, "unit": "bar", "ts": "..."}
"""
from __future__ import annotations

import threading
import time
from typing import Any

from .eventstore import utcnow


class SensorCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}

    def update(self, tag: str, msg: Any) -> None:
        if isinstance(msg, (int, float)):
            msg = {"value": msg}
        if not isinstance(msg, dict) or "value" not in msg:
            return
        try:
            value = float(msg["value"])
        except (TypeError, ValueError):
            return
        with self._lock:
            self._data[tag] = {"tag": tag, "value": value, "unit": msg.get("unit"),
                               "ts": msg.get("ts") or utcnow(), "_mono": time.monotonic()}

    def get(self, tag: str) -> dict | None:
        with self._lock:
            r = self._data.get(tag)
            if r is None:
                return None
            out = {k: v for k, v in r.items() if k != "_mono"}
            out["age_s"] = round(time.monotonic() - r["_mono"], 1)
            return out

    def all(self) -> dict[str, dict]:
        with self._lock:
            tags = list(self._data)
        return {t: self.get(t) for t in tags}
