"""Generator syntetycznych zgłoszeń.

Wynik (w katalogu wyjściowym, domyślnie data/synthetic/):
  reports/<id>.json — jedno zgłoszenie = jeden plik: metadane (kto, skąd, kiedy, czym) + treść.
                      Tak wyglądałoby zgłoszenie przychodzące z aplikacji. Bez poprawnych odpowiedzi.
  labels.jsonl      — poprawne odpowiedzi (gold) do ewaluacji, jedna linia na zgłoszenie.
                      Jest też indeksem: ewaluacja bierze tylko zgłoszenia wymienione tutaj.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT, load_yaml

DEFAULT_TEMPLATES = ROOT / "data" / "templates" / "reports.yaml"
DEFAULT_ROSTER = ROOT / "config" / "roster.yaml"
SCHEMA_VERSION = "0.1"

# Proste "zakłócenia" udające zapis z rozpoznawania mowy.
# TODO: literówki, brak polskich znaków, wtrącenia ("yyy", "znaczy"), mieszanie języków.
NOISE = [
    lambda s: s,
    lambda s: s.lower(),
    lambda s: s.replace(",", ""),
    lambda s: "yyy " + s,
]


def watch_of(hour: int) -> str:
    start = hour // 4 * 4
    return f"{start:02d}-{start + 4:02d}"


def make_report(i: int, t: dict, roster: dict, rng: random.Random, start: datetime,
                days: int, noise: bool) -> tuple[dict, dict]:
    crew = [c for c in roster["zaloga"] if c["stanowisko"] in t["zglaszajacy"]]
    if not crew:
        raise ValueError(f"szablon {t['id']}: brak osób o stanowiskach {t['zglaszajacy']} w roster.yaml")
    who = rng.choice(crew)
    lang = who["jezyk"] if who["jezyk"] in t["teksty"] else rng.choice(list(t["teksty"]))
    # Jeden wspólny indeks dla wszystkich slotów: wersje pl/en i miejsce zgadzają się ze sobą.
    sloty = t.get("sloty", {})
    idx = rng.randrange(min((len(v) for v in sloty.values()), default=1))
    slots = {k: v[idx] for k, v in sloty.items()}
    text = rng.choice(t["teksty"][lang]).format(**slots)
    # miejsca_wg_slotu: true -> lista `miejsca` jest równoległa do slotów (np. "na rufie" -> "pokład rufowy")
    place = t["miejsca"][idx] if t.get("miejsca_wg_slotu") else rng.choice(t["miejsca"])
    if noise:
        text = rng.choice(NOISE)(text)

    ts = start + timedelta(seconds=rng.randrange(days * 24 * 3600))
    rid = f"ZGL-{ts:%Y%m%d}-{i:04d}"
    report = {
        "schema_version": SCHEMA_VERSION,
        "id": rid,
        "statek": roster["statek"]["nazwa"],
        "czas_utc": ts.isoformat(timespec="seconds"),
        "wachta": watch_of(ts.hour),
        "zglaszajacy": {k: who[k] for k in ("id", "imie_nazwisko", "stanowisko", "dzial")},
        "lokalizacja": place,
        "kanal": "glos",
        "urzadzenie": rng.choice(roster["urzadzenia"]),
        "jezyk": lang,
        "nagranie_s": round(len(text.split()) * rng.uniform(0.35, 0.6), 1),  # szacowana długość nagrania
        "tresc": text,  # TYLKO to pole trafia do modelu
    }
    label = {"id": rid, "template": t["id"], "kategoria": t.get("kategoria", "rutyna"), "gold": dict(t["gold"])}
    return report, label


def generate(n: int, seed: int = 42, templates_path: str | Path = DEFAULT_TEMPLATES,
             roster_path: str | Path = DEFAULT_ROSTER, noise: bool = True,
             start: datetime = datetime(2026, 11, 1, tzinfo=timezone.utc), days: int = 14
             ) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    cfg = load_yaml(templates_path)
    templates = cfg["templates"]
    roster = load_yaml(roster_path)
    # Losowanie: najpierw kategoria wg `udzialy` (np. 80% rutyny), potem szablon z tej kategorii.
    by_cat: dict[str, list] = {}
    for t in templates:
        by_cat.setdefault(t.get("kategoria", "rutyna"), []).append(t)
    shares = {c: w for c, w in cfg.get("udzialy", {c: 1 for c in by_cat}).items() if c in by_cat}
    cats, weights = list(shares), list(shares.values())
    reports, labels = [], []
    for i in range(n):
        t = rng.choice(by_cat[rng.choices(cats, weights)[0]])
        r, lab = make_report(i, t, roster, rng, start, days, noise)
        reports.append(r)
        labels.append(lab)
    return reports, labels


def write_dataset(reports: list[dict], labels: list[dict], out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    rep_dir = out_dir / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    for r in reports:
        (rep_dir / f"{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(labels, out_dir / "labels.jsonl")
    return rep_dir


def load_dataset(data_dir: str | Path) -> tuple[list[dict], list[dict]]:
    """Wczytuje zgłoszenia wymienione w labels.jsonl (pliki spoza indeksu są pomijane)."""
    data_dir = Path(data_dir)
    labels = read_jsonl(data_dir / "labels.jsonl")
    reports = [json.loads((data_dir / "reports" / f"{lab['id']}.json").read_text(encoding="utf-8"))
               for lab in labels]
    return reports, labels


def write_jsonl(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
