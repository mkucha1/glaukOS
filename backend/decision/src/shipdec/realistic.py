"""Zbiór realistycznych, "nieczystych" wypowiedzi (data/realistic/utterances.yaml).

Zamienia wypowiedzi na ten sam format co generator syntetyczny (wejście serwera, POST /api/reports/text):
  <out>/reports/<report_id>.json — zgłoszenie + `_meta` (kto, skąd, kiedy, sektor); `text` = surowa wypowiedź
  <out>/labels.jsonl             — gold + streszczenie_wzorcowe, cechy, uwagi (do ewaluacji)
  <out>/kompresja.jsonl          — pary {report_id, lang, text, streszczenie_wzorcowe} dla warstwy porządkującej
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ROOT, load_yaml
from .generate import DEFAULT_ROSTER, make_report, pick_reporter, stable_id, write_dataset, write_jsonl

DEFAULT_UTTERANCES = ROOT / "data" / "realistic" / "utterances.yaml"
META_KEYS = ("streszczenie_wzorcowe", "cechy", "uwagi", "niejednoznaczne")


def build(path: str | Path = DEFAULT_UTTERANCES, roster_path: str | Path = DEFAULT_ROSTER, seed: int = 7,
          start: datetime = datetime(2026, 11, 1, tzinfo=timezone.utc), days: int = 14
          ) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    roster = load_yaml(roster_path)
    reports, labels = [], []
    for u in load_yaml(path)["wypowiedzi"]:
        who = pick_reporter(roster, u["stanowisko"], u["jezyk"], rng)
        ts = start + timedelta(seconds=rng.randrange(days * 24 * 3600))
        rid = stable_id("realistic", u["id"])
        reports.append(make_report(rid, who=who, text=u["tresc"], lang=u["jezyk"], location=u["lokalizacja"],
                                   ts=ts, device="phone", roster=roster,
                                   audio_s=round(len(u["tresc"].split()) * rng.uniform(0.4, 0.65), 1)))
        lab = {"report_id": rid, "template": u["id"], "kategoria": u.get("kategoria", "rutyna"), "gold": {**u["gold"], "sektor": reports[-1]["_meta"]["sector"]}}
        lab.update({k: u[k] for k in META_KEYS if k in u})
        labels.append(lab)
    return reports, labels


def write(reports: list[dict], labels: list[dict], out_dir: str | Path) -> Path:
    rep_dir = write_dataset(reports, labels, out_dir)
    by_id = {lab["report_id"]: lab for lab in labels}
    write_jsonl([{"report_id": r["report_id"], "lang": r["lang"], "text": r["text"],
                  "streszczenie_wzorcowe": by_id[r["report_id"]].get("streszczenie_wzorcowe")} for r in reports],
                Path(out_dir) / "kompresja.jsonl")
    return rep_dir
