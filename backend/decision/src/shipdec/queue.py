"""Kolejka obsługi i wysyłki na ląd (po złapaniu łącza).

Reguła (w kodzie, nie w modelu), na priorytecie P jak we frontendzie (1 = najwyższy):
  1. zgłoszenia, które model uznał za raport do DPA  -> P1 niezależnie od pilności
  2. pozostałe wg priorytetu z modelu: P1, potem P2, potem P3
  3. w ramach tego samego priorytetu: od najstarszego
"""
from __future__ import annotations

from .contract import DPA_PRIORITY, PRIORITY_FROM_LEVEL


def priority(row: dict) -> int:
    d = row["decisions"]
    if d.get("raport_dpa", {}).get("pred") == "true":
        return DPA_PRIORITY
    return PRIORITY_FROM_LEVEL[int(d["pilnosc"]["pred"]) + 1]   # klucz "0".."2" -> poziom 1..3 -> P3..P1


def order(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: (priority(r), r.get("recorded_at") or ""))
