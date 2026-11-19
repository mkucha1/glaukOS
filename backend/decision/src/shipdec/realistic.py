"""Zbiór realistycznych, "nieczystych" wypowiedzi (data/realistic/utterances.yaml).

Zamienia wypowiedzi na ten sam format co generator syntetyczny:
  <out>/reports/<id>.json  — zgłoszenie z metadanymi (kto, skąd, kiedy) + `tresc` (surowa wypowiedź)
  <out>/labels.jsonl       — gold + streszczenie_wzorcowe, cechy, uwagi (do ewaluacji)
  <out>/kompresja.jsonl    — pary {id, jezyk, tresc, streszczenie_wzorcowe} dla modelu kompresującego
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT, load_yaml
from .generate import DEFAULT_ROSTER, SCHEMA_VERSION, watch_of, write_dataset, write_jsonl

DEFAULT_UTTERANCES = ROOT / "data" / "realistic" / "utterances.yaml"
META_KEYS = ("streszczenie_wzorcowe", "cechy", "uwagi", "niejednoznaczne")


def build(path: str | Path = DEFAULT_UTTERANCES, roster_path: str | Path = DEFAULT_ROSTER, seed: int = 7,
          start: datetime = datetime(2026, 11, 1, tzinfo=timezone.utc), days: int = 14
          ) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    roster = load_yaml(roster_path)
    reports, labels = [], []
    for u in load_yaml(path)["wypowiedzi"]:
        crew = [c for c in roster["zaloga"] if c["stanowisko"] == u["stanowisko"]]
        if not crew:
            raise ValueError(f"{u['id']}: brak stanowiska {u['stanowisko']!r} w roster.yaml")
        same_lang = [c for c in crew if c["jezyk"] == u["jezyk"]]
        who = rng.choice(same_lang or crew)
        ts = start + timedelta(seconds=rng.randrange(days * 24 * 3600))
        rid = f"REAL-{u['id']}"
        reports.append({
            "schema_version": SCHEMA_VERSION,
            "id": rid,
            "statek": roster["statek"]["nazwa"],
            "czas_utc": ts.isoformat(timespec="seconds"),
            "wachta": watch_of(ts.hour),
            "zglaszajacy": {k: who[k] for k in ("id", "imie_nazwisko", "stanowisko", "dzial")},
            "lokalizacja": u["lokalizacja"],
            "kanal": "glos",
            "urzadzenie": "telefon",
            "jezyk": u["jezyk"],
            "nagranie_s": round(len(u["tresc"].split()) * rng.uniform(0.4, 0.65), 1),
            "tresc": u["tresc"],
        })
        lab = {"id": rid, "template": u["id"], "kategoria": u.get("kategoria", "rutyna"), "gold": dict(u["gold"])}
        lab.update({k: u[k] for k in META_KEYS if k in u})
        labels.append(lab)
    return reports, labels


def write(reports: list[dict], labels: list[dict], out_dir: str | Path) -> Path:
    rep_dir = write_dataset(reports, labels, out_dir)
    by_id = {lab["id"]: lab for lab in labels}
    write_jsonl([{"id": r["id"], "jezyk": r["jezyk"], "tresc": r["tresc"],
                  "streszczenie_wzorcowe": by_id[r["id"]].get("streszczenie_wzorcowe")} for r in reports],
                Path(out_dir) / "kompresja.jsonl")
    return rep_dir
