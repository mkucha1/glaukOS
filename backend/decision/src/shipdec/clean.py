"""Porządkowanie treści zgłoszeń warstwą LLM z gałęzi `moj-llm` (my_folder/przetworz.py).

Bierzemy NASZE zgłoszenia (data/<zbiór>/) i zapisujemy ich kopię z oczyszczoną treścią do
data/<zbiór>_clean/: ten sam report_id, te same metadane i etykiety, zmienia się tylko `text`.
Surowa wypowiedź i dane o porządkowaniu trafiają do `_meta.cleaning`. Basal czyta tylko `text`,
więc ewaluacja obu zbiorów porównuje dokładnie: surowa wypowiedź vs ta sama po oczyszczeniu.

Do warstwy porządkującej idzie wyłącznie tekst i język — bez lokalizacji, zgłaszającego itd.,
żeby nie podpowiadać modelowi niczego, czego nie ma w nagraniu.

Wymaga: kodu z gałęzi moj-llm (folder my_folder) i działającego LLM (Ollama, qwen3.5:4b),
albo uruchomionego `python app.py` z tamtego folderu (--url).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .generate import load_dataset, write_jsonl


def _przetworz_fn(llm_dir: str | Path):
    llm_dir = Path(llm_dir).resolve()
    if not (llm_dir / "przetworz.py").exists():
        raise SystemExit(f"Brak {llm_dir}/przetworz.py — podaj --llm-dir do folderu my_folder z gałęzi moj-llm")
    sys.path.insert(0, str(llm_dir))
    from przetworz import BladPrzetwarzania, przetworz  # type: ignore
    return przetworz, BladPrzetwarzania


def clean_dataset(src_dir: str | Path, out_dir: str | Path, llm_dir: str | Path,
                  url: str | None = None, limit: int | None = None, skip_done: bool = True) -> dict:
    przetworz, Blad = _przetworz_fn(llm_dir)
    reports, labels = load_dataset(src_dir)
    if limit:
        reports, labels = reports[:limit], labels[:limit]
    out_dir = Path(out_dir)
    rep_dir = out_dir / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)

    done_labels, stats = [], {"ok": 0, "pominiete": 0, "bledy": 0, "niejednoznaczne": 0, "czas_s": 0.0}
    t_start = time.perf_counter()
    for i, (r, lab) in enumerate(zip(reports, labels), 1):
        target = rep_dir / f"{r['report_id']}.json"
        if skip_done and target.exists():
            stats["pominiete"] += 1
            done_labels.append(lab)
            continue
        t0 = time.perf_counter()
        try:
            out = przetworz({"text": r["text"], "jezyk": r.get("lang")}, url=url)
        except Blad as e:
            stats["bledy"] += 1
            print(f"[{i}/{len(reports)}] {r['report_id'][:8]}  BŁĄD: {e}", file=sys.stderr, flush=True)
            if "nie odpowiada" in str(e):
                print("Przerywam: LLM nie odpowiada (czy działa Ollama?).", file=sys.stderr)
                break
            continue
        ms = round((time.perf_counter() - t0) * 1000)
        clean = dict(r)
        clean["text"] = out["tresc"]
        meta = dict(r.get("_meta") or {})
        meta["cleaning"] = {"raw_text": r["text"], "model": (out.get("porzadkowanie") or {}).get("model"),
                            "lang_detected": out.get("jezyk"), "unclear": bool(out.get("niejednoznaczne")),
                            "ms": ms}
        clean["_meta"] = meta
        target.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        done_labels.append(lab)
        stats["ok"] += 1
        stats["niejednoznaczne"] += meta["cleaning"]["unclear"]
        print(f"[{i}/{len(reports)}] {r['report_id'][:8]}  {ms / 1000:.1f}s  {out['tresc'][:90]}",
              file=sys.stderr, flush=True)
    write_jsonl(done_labels, out_dir / "labels.jsonl")   # tylko zgłoszenia, które mają czystą wersję
    stats["czas_s"] = round(time.perf_counter() - t_start, 1)
    return stats


def compare(summary_a: str | Path, summary_b: str | Path, name_a: str = "surowe",
            name_b: str = "oczyszczone") -> str:
    """Tabela porównania dwóch plików *.summary.json z `shipdec evaluate`."""
    a = json.loads(Path(summary_a).read_text(encoding="utf-8"))
    b = json.loads(Path(summary_b).read_text(encoding="utf-8"))
    pct = lambda v: "—" if v is None else f"{v:.1%}"
    lines = [f"{'pytanie':<12}{'trafność ' + name_a:>20}{'trafność ' + name_b:>24}{'różnica':>10}"
             f"{'automat ' + name_a:>18}{'automat ' + name_b:>22}"]
    for q in a["pytania"]:
        qa, qb = a["pytania"][q], b["pytania"].get(q)
        if not qb:
            continue
        lines.append(f"{q:<12}{pct(qa['accuracy']):>20}{pct(qb['accuracy']):>24}"
                     f"{(qb['accuracy'] - qa['accuracy']) * 100:>+9.1f}p"
                     f"{pct(qa['coverage']):>18}{pct(qb['coverage']):>22}")
    za, zb = a["zgloszenia"], b["zgloszenia"]
    lines += ["",
              f"zgłoszenia w pełni automatyczne:  {name_a} {pct(za['w_pelni_automatycznie'])}  ->  "
              f"{name_b} {pct(zb['w_pelni_automatycznie'])}",
              f"błędne wśród automatycznych:      {name_a} {pct(za['blad_wsrod_automatycznych'])}  ->  "
              f"{name_b} {pct(zb['blad_wsrod_automatycznych'])}",
              f"decyzji do zatwierdzenia / zgł.:  {name_a} {za['srednio_decyzji_do_zatwierdzenia']:.2f}  ->  "
              f"{name_b} {zb['srednio_decyzji_do_zatwierdzenia']:.2f}"]
    return "\n".join(lines)


def flips(results_a: str | Path, results_b: str | Path, limit: int = 15) -> str:
    """Zgłoszenia, w których oczyszczenie zmieniło trafność decyzji (do ręcznego przejrzenia)."""
    from .generate import read_jsonl
    b_by_id = {r["report_id"]: r for r in read_jsonl(results_b)}
    better, worse = [], []
    for ra in read_jsonl(results_a):
        rb = b_by_id.get(ra["report_id"])
        if not rb:
            continue
        for q, da in ra["decisions"].items():
            db = rb["decisions"].get(q)
            if db and da["correct"] != db["correct"]:
                (better if db["correct"] else worse).append((q, ra, rb))
    out = [f"oczyszczenie pomogło: {len(better)} decyzji, zaszkodziło: {len(worse)} decyzji"]
    for title, rows in (("ZASZKODZIŁO", worse), ("POMOGŁO", better)):
        if rows:
            out.append(f"\n{title}:")
        for q, ra, rb in rows[:limit]:
            d = rb["decisions"][q]
            out.append(f"- {q}: wzorzec {d['gold']}, surowe -> {ra['decisions'][q]['pred']}, czyste -> {d['pred']}\n"
                       f"    surowe: {ra['text'][:150]}\n    czyste: {rb['text'][:150]}")
    return "\n".join(out)


def build_sample(src_dir: str | Path, out_dir: str | Path, sample_file: str | Path) -> int:
    """Podzbiór naszego zbioru realistycznego wg listy id szablonów (config/sample15.yaml)."""
    from .config import load_yaml
    from .generate import write_dataset
    wanted = list(load_yaml(sample_file)["probka"])
    reports, labels = load_dataset(src_dir)
    by_tpl = {lab["template"]: (r, lab) for r, lab in zip(reports, labels)}
    missing = [t for t in wanted if t not in by_tpl]
    if missing:
        raise SystemExit(f"brak w {src_dir}: {missing} (najpierw: shipdec realistic)")
    out_dir = Path(out_dir)
    if out_dir.exists():
        import shutil
        shutil.rmtree(out_dir)
    write_dataset([by_tpl[t][0] for t in wanted], [by_tpl[t][1] for t in wanted], out_dir)
    return len(wanted)


def side_by_side(results_a: str | Path, results_b: str | Path, data_dir_b: str | Path | None = None) -> str:
    """Przed i po oczyszczeniu, zgłoszenie po zgłoszeniu (markdown): treść i każda decyzja."""
    from .generate import read_jsonl
    b_by_id = {r["report_id"]: r for r in read_jsonl(results_b)}
    show = lambda q, k: f"P{3 - int(k)}" if q == "pilnosc" else k      # klucz Basala "0".."2" -> P3..P1
    mark = lambda q, d: f"{show(q, d['pred'])} ({d['confidence']:.2f}) {'✓' if d['correct'] else '✗'}"
    out = ["# Basal: przed i po oczyszczeniu treści (qwen)", "",
           "✓/✗ = zgodność z etykietą wzorcową, w nawiasie pewność Basala.", ""]
    tot_a = tot_b = n = 0
    for ra in read_jsonl(results_a):
        rb = b_by_id.get(ra["report_id"])
        if not rb:
            continue
        unclear = ""
        if data_dir_b:
            p = Path(data_dir_b) / "reports" / f"{ra['report_id']}.json"
            if p.exists() and json.loads(p.read_text(encoding="utf-8"))["_meta"].get("cleaning", {}).get("unclear"):
                unclear = " — qwen: *niejednoznaczne*"
        ok_a = sum(d["correct"] for d in ra["decisions"].values())
        ok_b = sum(d["correct"] for d in rb["decisions"].values())
        tot_a, tot_b, n = tot_a + ok_a, tot_b + ok_b, n + len(ra["decisions"])
        out += [f"## {ra['template']} ({ra.get('kategoria')}) — trafne: przed {ok_a}, po {ok_b}{unclear}", "",
                f"**przed:** {ra['text']}", "", f"**po:** {rb['text']}", "",
                "| decyzja | wzorzec | przed | po |", "|---|---|---|---|"]
        for q, da in ra["decisions"].items():
            db = rb["decisions"][q]
            flag = " ⬆" if db["correct"] and not da["correct"] else (" ⬇" if da["correct"] and not db["correct"] else "")
            out.append(f"| {q}{flag} | {show(q, da['gold'])} | {mark(q, da)} | {mark(q, db)} |")
        out.append("")
    if n:
        out.insert(3, f"**Razem trafnych decyzji: przed {tot_a}/{n} ({tot_a / n:.0%}), po {tot_b}/{n} ({tot_b / n:.0%}).** "
                      "⬆ = oczyszczenie naprawiło decyzję, ⬇ = zepsuło.\n")
    return "\n".join(out)
