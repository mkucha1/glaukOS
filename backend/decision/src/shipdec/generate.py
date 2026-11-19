"""Generator syntetycznych zgłoszeń.

Wynik (w katalogu wyjściowym, domyślnie data/synthetic/):
  reports/<report_id>.json — jedno zgłoszenie = jeden plik, w formacie wejścia serwera pokładowego
                             (POST /api/reports/text: report_id, crew_id, text, lang, recorded_at, device)
                             + `_meta` (pola z "_" zostają na statku): statek, wachta, kto, gdzie, sektor.
  labels.jsonl             — poprawne odpowiedzi (gold) do ewaluacji, jedna linia na zgłoszenie.
                             Jest też indeksem: ewaluacja bierze tylko zgłoszenia wymienione tutaj.
Zgłoszenia są niezależne — żadnych powiązań między nimi.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT, load_yaml
from .ship import main_sector, sector_of

DEFAULT_TEMPLATES = ROOT / "data" / "templates" / "reports.yaml"
DEFAULT_ROSTER = ROOT / "config" / "roster.yaml"
SCHEMA_VERSION = "0.2"
ID_NAMESPACE = uuid.UUID("6f1c2d3e-4b5a-4c6d-8e7f-90a1b2c3d4e5")  # stałe UUID-y -> powtarzalne dane

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


def stable_id(*parts: object) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, "/".join(map(str, parts))))


def pick_reporter(roster: dict, role: str, lang: str | None, rng: random.Random) -> dict:
    """Osoba o danej roli; jeśli nikt w tej roli nie mówi w `lang` — ktoś z tego samego działu, kto mówi."""
    crew = roster["zaloga"]
    in_role = [c for c in crew if c["rola"] == role]
    if not in_role:
        raise ValueError(f"brak roli {role!r} w roster.yaml")
    if lang:
        same = [c for c in in_role if c["jezyk"] == lang]
        if same:
            return rng.choice(same)
        dept = in_role[0]["dzial"]
        same_dept = [c for c in crew if c["dzial"] == dept and c["jezyk"] == lang]
        if same_dept:
            return rng.choice(same_dept)
    return rng.choice(in_role)


def make_report(report_id: str, *, who: dict, text: str, lang: str, location: str, ts: datetime,
                device: str, roster: dict, audio_s: float) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "crew_id": who["crew_id"],
        "text": text,              # TYLKO to pole trafia do modelu decyzyjnego
        "lang": lang,
        "recorded_at": ts.isoformat(timespec="seconds"),
        "device": device,
        "_meta": {
            "ship": roster["statek"]["nazwa"],
            "ship_id": roster["statek"].get("ship_id"),
            "watch": watch_of(ts.hour),
            "reporter": {"crew_id": who["crew_id"], "name": who["imie"], "role": who["rola"], "dept": who["dzial"]},
            "location": location,
            "sector": main_sector(sector_of(location)),   # jeden z 4 sektorów demo
            "channel": "voice",
            "audio_s": audio_s,
        },
    }


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
        role = rng.choice(t["zglaszajacy"])
        who = pick_reporter(roster, role, None, rng)
        lang = who["jezyk"] if who["jezyk"] in t["teksty"] else rng.choice(list(t["teksty"]))
        # Jeden wspólny indeks dla wszystkich slotów: wersje pl/en i miejsce zgadzają się ze sobą.
        sloty = t.get("sloty", {})
        idx = rng.randrange(min((len(v) for v in sloty.values()), default=1))
        text = rng.choice(t["teksty"][lang]).format(**{k: v[idx] for k, v in sloty.items()})
        if noise:
            text = rng.choice(NOISE)(text)
        place = t["miejsca"][idx] if t.get("miejsca_wg_slotu") else rng.choice(t["miejsca"])
        ts = start + timedelta(seconds=rng.randrange(days * 24 * 3600))
        rid = stable_id("synthetic", seed, i)
        reports.append(make_report(rid, who=who, text=text, lang=lang, location=place, ts=ts,
                                   device=rng.choice(roster["urzadzenia"]), roster=roster,
                                   audio_s=round(len(text.split()) * rng.uniform(0.35, 0.6), 1)))
        labels.append({"report_id": rid, "template": t["id"], "kategoria": t.get("kategoria", "rutyna"),
                       "gold": {**t["gold"], "sektor": reports[-1]["_meta"]["sector"]}})
    return reports, labels


def write_dataset(reports: list[dict], labels: list[dict], out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    rep_dir = out_dir / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    for r in reports:
        (rep_dir / f"{r['report_id']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(labels, out_dir / "labels.jsonl")
    return rep_dir


def load_dataset(data_dir: str | Path) -> tuple[list[dict], list[dict]]:
    """Wczytuje zgłoszenia wymienione w labels.jsonl (pliki spoza indeksu są pomijane)."""
    data_dir = Path(data_dir)
    labels = read_jsonl(data_dir / "labels.jsonl")
    reports = [json.loads((data_dir / "reports" / f"{lab['report_id']}.json").read_text(encoding="utf-8"))
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
