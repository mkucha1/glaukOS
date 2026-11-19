"""Kolejka obsługi i wysyłki na ląd (po złapaniu łącza).

Reguła (w kodzie, nie w modelu):
  1. zgłoszenia, które model uznał za raport do DPA  -> priorytet 3 niezależnie od pilności
  2. pozostałe wg pilności z modelu: 3, potem 2, potem 1
  3. w ramach tego samego priorytetu: od najstarszego
"""
from __future__ import annotations


def priority(row: dict) -> int:
    d = row["decisions"]
    if d.get("raport_dpa", {}).get("pred") == "true":
        return 3
    return int(d["pilnosc"]["pred"]) + 1  # klucz "0".."2" -> poziom 1..3


def order(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: (-priority(r), r.get("czas_utc") or ""))
