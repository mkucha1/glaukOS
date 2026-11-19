"""Polecenia:  shipdec generate | shipdec evaluate"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import settings
from .backends import get_backend
from .config import ROOT, load_questions
from .evaluate import format_reports, format_summary, run, summarize, summarize_reports
from .generate import read_jsonl
from .queue import order, priority
from .generate import generate, load_dataset, write_dataset, write_jsonl

DEFAULT_DATA = ROOT / "data" / "synthetic"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="shipdec", description="Testy modelu decyzyjnego na zgłoszeniach ze statku")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="wygeneruj syntetyczne zgłoszenia (jeden plik JSON na zgłoszenie)")
    g.add_argument("-n", type=int, default=200)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out-dir", default=str(DEFAULT_DATA))
    g.add_argument("--no-noise", action="store_true")

    e = sub.add_parser("evaluate", help="uruchom model na zgłoszeniach i policz wyniki")
    e.add_argument("--data-dir", default=str(DEFAULT_DATA))
    e.add_argument("--backend", choices=["basal", "mock"], default="basal")
    e.add_argument("--url", default=None, help="adres serwera; domyślnie BASAL_URL z .env")
    e.add_argument("--out", default=str(ROOT / "results" / "results.jsonl"))
    e.add_argument("--questions", default=None, help="plik z pytaniami; domyślnie DECISION_QUESTIONS z .env")
    e.add_argument("--timeout", type=float, default=None, help="limit czasu na zgłoszenie [s]; domyślnie BASAL_TIMEOUT")
    e.add_argument("--limit", type=int, default=None, help="tylko pierwsze N zgłoszeń (szybki test, np. na CPU)")

    r = sub.add_parser("realistic", help="zbuduj zbiór z realistycznych wypowiedzi (data/realistic/utterances.yaml)")
    r.add_argument("--out-dir", default=str(ROOT / "data" / "realistic"))

    k = sub.add_parser("queue", help="pokaż kolejkę wysyłki dla wyników ewaluacji")
    k.add_argument("--results", default=str(ROOT / "results" / "results.jsonl"))
    k.add_argument("-n", type=int, default=15)

    a = p.parse_args(argv)
    if a.cmd == "realistic":
        from .realistic import build, write
        reports, labels = build()
        rep_dir = write(reports, labels, a.out_dir)
        print(f"zapisano {len(reports)} wypowiedzi -> {rep_dir}/  (+ labels.jsonl, kompresja.jsonl)")
        return
    if a.cmd == "queue":
        rows = order(read_jsonl(a.results))
        print(f"{'prio':<5}{'czas_utc':<27}{'id':<20}treść")
        for r in rows[:a.n]:
            print(f"{priority(r):<5}{(r.get('czas_utc') or '-'):<27}{r['id']:<20}{r['tresc'][:70]}")
        return
    if a.cmd == "generate":
        reports, labels = generate(a.n, seed=a.seed, noise=not a.no_noise)
        rep_dir = write_dataset(reports, labels, a.out_dir)
        print(f"zapisano {len(reports)} zgłoszeń -> {rep_dir}/  (etykiety: {Path(a.out_dir) / 'labels.jsonl'})")
    else:
        questions, thresholds = load_questions(a.questions or settings.questions_path())
        reports, labels = load_dataset(a.data_dir)
        if a.limit:
            reports, labels = reports[:a.limit], labels[:a.limit]
        results = run(reports, labels, questions, get_backend(a.backend, a.url, a.timeout),
                      progress=a.backend != "mock")
        write_jsonl(results, a.out)
        summary = summarize(results, thresholds)
        reports_summary = summarize_reports(results, thresholds)
        Path(a.out).with_suffix(".summary.json").write_text(json.dumps(
            {"pytania": summary, "zgloszenia": reports_summary, "progi": thresholds},
            ensure_ascii=False, indent=2), encoding="utf-8")
        if a.backend == "mock":
            print("UWAGA: backend 'mock' — sprawdza tylko potok, wyniki nic nie mówią o modelu.\n")
        print(format_summary(summary))
        print()
        print(format_reports(reports_summary))


if __name__ == "__main__":
    main()
