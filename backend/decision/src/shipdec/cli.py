"""Polecenia:  shipdec generate | realistic | evaluate | clean | compare | voice | worker | push | queue | export-server-config"""
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

    x = sub.add_parser("export-server-config",
                       help="zapisz reguły decyzji do mozg-statku/server/config/decision.json (dla pluginu serwera)")
    x.add_argument("--out", default=None)

    u = sub.add_parser("push", help="wyślij zgłoszenia do serwera pokładowego (POST /api/reports/text)")
    u.add_argument("--server", default="http://127.0.0.1:8000", help="adres serwera mozg-statku")
    u.add_argument("--data-dir", default=str(DEFAULT_DATA))
    u.add_argument("--limit", type=int, default=None)

    c = sub.add_parser("clean", help="oczyść treść zgłoszeń warstwą LLM z gałęzi moj-llm -> osobny zbiór *_clean")
    c.add_argument("--data-dir", default=str(ROOT / "data" / "realistic"))
    c.add_argument("--out-dir", default=None, help="domyślnie <data-dir>_clean")
    c.add_argument("--llm-dir", default=str(ROOT.parents[2] / "moj-llm" / "my_folder"),
                   help="folder my_folder z gałęzi moj-llm (przetworz.py)")
    c.add_argument("--url", default=None, help="zamiast wołać LLM bezpośrednio: działający app.py, np. http://127.0.0.1:8010")
    c.add_argument("--limit", type=int, default=None)
    c.add_argument("--od-nowa", action="store_true", help="przetwórz też zgłoszenia, które mają już czystą wersję")

    sp = sub.add_parser("sample", help="wybierz reprezentatywną próbkę z data/realistic (config/sample15.yaml)")
    sp.add_argument("--data-dir", default=str(ROOT / "data" / "realistic"))
    sp.add_argument("--out-dir", default=str(ROOT / "data" / "sample15"))
    sp.add_argument("--list", default=str(ROOT / "config" / "sample15.yaml"))

    m = sub.add_parser("compare", help="porównaj dwie ewaluacje (np. surowe vs oczyszczone)")
    m.add_argument("a", help="wyniki A (results/....jsonl)")
    m.add_argument("b", help="wyniki B (results/....jsonl)")
    m.add_argument("--names", nargs=2, default=["surowe", "oczyszczone"])
    m.add_argument("--przyklady", type=int, default=10, help="ile zgłoszeń ze zmienioną trafnością pokazać")
    m.add_argument("--md", default=None, help="zapisz porównanie zgłoszenie po zgłoszeniu (markdown) do pliku")
    m.add_argument("--clean-dir", default=None, help="folder oczyszczonego zbioru (oznacza 'niejednoznaczne')")

    v = sub.add_parser("voice", help="potok głosowy: tekst z STT (stt_batch.py) -> qwen -> Basal")
    v.add_argument("--stt", default=str(ROOT / "results" / "voice" / "stt.jsonl"), help="wynik scripts/stt_batch.py")
    v.add_argument("--out-dir", default=str(ROOT / "results" / "voice"))
    v.add_argument("--llm-dir", default=str(ROOT.parents[2] / "moj-llm" / "my_folder"))
    v.add_argument("--no-qwen", action="store_true", help="bez porządkowania (Basal tylko na tekście z STT)")
    v.add_argument("--backend", choices=["basal", "mock"], default="basal")
    v.add_argument("--url", default=None)

    w = sub.add_parser("worker", help="worker statku: Supabase -> STT -> qwen -> Basal -> Supabase")
    w.add_argument("--stt-url", default="http://127.0.0.1:8002", help="serwis STT (gałąź stt)")
    w.add_argument("--basal-url", default=None, help="domyślnie BASAL_URL z .env")
    w.add_argument("--llm-dir", default=str(ROOT.parents[2] / "moj-llm" / "my_folder"))
    w.add_argument("--take-over", action="store_true",
                   help="wyłącz ship_status.autopilot (scenariusz demo w bazie), jak w supabase/README.md")
    w.add_argument("--restore-autopilot", action="store_true", help="po zakończeniu włącz autopilota z powrotem")
    w.add_argument("--since-minutes", type=float, default=10, help="obsłuż też zgłoszenia z ostatnich N minut")
    w.add_argument("--poll", type=float, default=2.0)

    k = sub.add_parser("queue", help="pokaż kolejkę wysyłki dla wyników ewaluacji")
    k.add_argument("--results", default=str(ROOT / "results" / "results.jsonl"))
    k.add_argument("-n", type=int, default=15)

    a = p.parse_args(argv)
    if a.cmd == "export-server-config":
        from .contract import SERVER_CONFIG, export_server_config
        print(f"zapisano -> {export_server_config(a.out or SERVER_CONFIG)}")
        return
    if a.cmd == "push":
        from .server import push_reports
        reports, _ = load_dataset(a.data_dir)
        push_reports(reports[:a.limit] if a.limit else reports, a.server)
        return
    if a.cmd == "realistic":
        from .realistic import build, write
        reports, labels = build()
        rep_dir = write(reports, labels, a.out_dir)
        print(f"zapisano {len(reports)} wypowiedzi -> {rep_dir}/  (+ labels.jsonl, kompresja.jsonl)")
        return
    if a.cmd == "clean":
        from .clean import clean_dataset
        out = a.out_dir or f"{a.data_dir.rstrip('/')}_clean"
        stats = clean_dataset(a.data_dir, out, a.llm_dir, url=a.url, limit=a.limit, skip_done=not a.od_nowa)
        print(f"oczyszczone -> {out}/reports/  {stats}")
        return
    if a.cmd == "compare":
        from .clean import compare, flips
        sa, sb = (str(Path(x).with_suffix(".summary.json")) for x in (a.a, a.b))
        print(compare(sa, sb, *a.names))
        print()
        print(flips(a.a, a.b, a.przyklady))
        if a.md:
            from .clean import side_by_side
            Path(a.md).write_text(side_by_side(a.a, a.b, a.clean_dir), encoding="utf-8")
            print(f"\nprzed/po zgłoszenie po zgłoszeniu -> {a.md}")
        return
    if a.cmd == "sample":
        from .clean import build_sample
        print(f"próbka {build_sample(a.data_dir, a.out_dir, a.list)} zgłoszeń -> {a.out_dir}")
        return
    if a.cmd == "worker":
        from .worker import main_worker
        main_worker(a)
        return
    if a.cmd == "voice":
        from .voice import run_voice
        run_voice(a.stt, a.out_dir, get_backend(a.backend, a.url), None if a.no_qwen else a.llm_dir)
        print(f"raport -> {Path(a.out_dir) / 'raport.md'}")
        return
    if a.cmd == "queue":
        rows = order(read_jsonl(a.results))
        print(f"{'prio':<5}{'recorded_at':<27}{'sektor':<10}treść")
        for r in rows[:a.n]:
            print(f"P{priority(r):<4}{(r.get('recorded_at') or '-'):<27}{(r.get('sector') or '-'):<10}{r['text'][:70]}")
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
