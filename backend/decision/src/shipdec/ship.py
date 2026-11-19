"""Sektory statku jak na przekroju we frontendzie (frontend/src/lib/ship.ts).

`sector_of()` to wierne przeniesienie `sectorOf()` z frontendu: te same reguły (słowa kluczowe w
`location` i `equipment`, potem pierwsza cyfra kodu SFI). Dzięki temu lokalizacje w naszych danych
trafiają na przekroju dokładnie tam, gdzie powinny. Przy zmianie reguł we frontendzie — zmień też tutaj.
"""
from __future__ import annotations

import re

SECTORS = ["bridge", "cabins", "galley", "purifier", "ecr", "engine", "steering", "deck", "holds", "bow", "tanks"]

# Demo działa na 4 głównych sektorach; pozostałe sektory frontendu są do nich dołączane.
MAIN_SECTORS = ["engine", "deck", "galley", "bridge"]
SECTOR_MERGE = {"purifier": "engine", "ecr": "engine", "steering": "engine",
                "bow": "deck", "holds": "deck", "tanks": "deck", "cabins": "galley"}


def main_sector(sector: str) -> str:
    return SECTOR_MERGE.get(sector, sector)


SECTOR_LABELS = {
    "engine": "Engine room", "holds": "Cargo holds", "deck": "Main deck", "bow": "Bow & mooring",
    "tanks": "Ballast & tanks", "steering": "Steering", "purifier": "Purifiers", "ecr": "ECR",
    "galley": "Galley & mess", "cabins": "Cabins", "bridge": "Bridge",
}

# Kolejność ma znaczenie — jak w RULES we frontendzie.
RULES: list[tuple[str, re.Pattern]] = [
    ("purifier", re.compile(r"purifier|separator")),
    ("ecr", re.compile(r"\becr\b|control room|switchboard|alarm panel")),
    ("steering", re.compile(r"steering|rudder")),
    ("bridge", re.compile(r"bridge|wheelhouse|radar|ecdis|gyro|vhf|navigation|autopilot")),
    ("galley", re.compile(r"galley|cold room|provision|mess\b|pantry")),
    ("cabins", re.compile(r"cabin|accommodation|hvac|ac unit|air condition")),
    ("bow", re.compile(r"\bbow\b|forecastle|windlass|anchor|forepeak")),
    ("deck", re.compile(r"crane|hatch|davit|lifeboat|boat deck|main deck|mooring")),
    ("holds", re.compile(r"\bhold\b|cargo")),
    ("tanks", re.compile(r"ballast|double bottom|\btank\b")),
    ("engine", re.compile(r"engine|generator|aux|boiler|compressor|pump|bilge")),
]

_SFI_SECTOR = {"4": "bridge", "5": "cabins", "3": "holds", "2": "tanks"}


def sector_of(location: str = "", equipment: str = "", sfi_code: str | None = None) -> str:
    text = f"{location or ''} {equipment or ''}".lower()
    for sid, rx in RULES:
        if rx.search(text):
            return sid
    return _SFI_SECTOR.get((sfi_code or " ")[0], "engine")
