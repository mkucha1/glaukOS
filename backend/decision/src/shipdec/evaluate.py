"""Uruchamia model na zgłoszeniach i liczy wyniki.

Model dostaje WYŁĄCZNIE treść zgłoszenia (`text`) i listę opcji z config/questions.yaml.
Metadane (kto, skąd, kiedy) nie trafiają do modelu.

Kluczowa miara: przy danym progu pewności — jaki odsetek decyzji przechodzi
automatycznie (pokrycie) i jaki jest błąd wśród nich.
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict

from .config import gold_key

MODEL_INPUT_FIELD = "text"


def predicted_key(ans: dict) -> str:
    """Klucz wybranej odpowiedzi (dla każdego typu pytania)."""
    return max(ans["probabilities"], key=ans["probabilities"].get)


def run(reports: list[dict], labels: list[dict], questions: dict, backend,
        progress: bool = False) -> list[dict]:
    gold_by_id = {lab["report_id"]: lab for lab in labels}
    results = []
    for i, r in enumerate(reports, 1):
        lab = gold_by_id[r["report_id"]]
        t0 = time.perf_counter()
        resp = backend.decide(r[MODEL_INPUT_FIELD], questions)
        row = {"report_id": r["report_id"], "template": lab["template"], "kategoria": lab.get("kategoria"),
               "recorded_at": r.get("recorded_at"), "sector": (r.get("_meta") or {}).get("sector"),
               "text": r[MODEL_INPUT_FIELD],
               "latency_ms": resp.get("usage", {}).get("latency_ms"), "decisions": {}}
        for name, q in questions.items():
            ans = resp["answers"][name]
            gold = gold_key(q, lab["gold"][name])
            pred = predicted_key(ans)
            row["decisions"][name] = {"pred": pred, "gold": gold, "correct": pred == gold,
                                      "confidence": round(ans["confidence"], 4)}
        results.append(row)
        if progress:
            ok = sum(d["correct"] for d in row["decisions"].values())
            print(f"[{i}/{len(reports)}] {r['report_id'][:8]}  {ok}/{len(questions)} trafnych  "
                  f"{time.perf_counter() - t0:.1f}s", file=sys.stderr, flush=True)
    return results


def summarize(results: list[dict], thresholds: dict) -> dict:
    per_q = defaultdict(lambda: {"n": 0, "correct": 0, "auto": 0, "auto_errors": 0})
    for row in results:
        for name, d in row["decisions"].items():
            s = per_q[name]
            s["n"] += 1
            s["correct"] += d["correct"]
            if d["confidence"] >= thresholds.get(name, thresholds.get("default", 0.8)):
                s["auto"] += 1
                s["auto_errors"] += not d["correct"]
    out = {}
    for name, s in per_q.items():
        out[name] = {
            "accuracy": s["correct"] / s["n"],
            "threshold": thresholds.get(name, thresholds.get("default", 0.8)),
            "coverage": s["auto"] / s["n"],                       # ile idzie automatycznie
            "error_when_auto": (s["auto_errors"] / s["auto"]) if s["auto"] else None,
        }
    return out


def _threshold(thresholds: dict, name: str) -> float:
    return thresholds.get(name, thresholds.get("default", 0.8))


def summarize_reports(results: list[dict], thresholds: dict) -> dict:
    """Miara oszczędności czasu: ile zgłoszeń przechodzi bez żadnego dotknięcia oficera."""
    n = len(results)
    auto = auto_err = to_review = 0
    by_cat: dict = defaultdict(lambda: {"n": 0, "auto": 0})
    for row in results:
        pending = [k for k, d in row["decisions"].items() if d["confidence"] < _threshold(thresholds, k)]
        cat = by_cat[row.get("kategoria") or "?"]
        cat["n"] += 1
        to_review += len(pending)
        if not pending:
            auto += 1
            cat["auto"] += 1
            # Sektor tylko ustawia kropkę na mapie — jego pomyłka nie psuje przydziału.
            auto_err += not all(d["correct"] for k, d in row["decisions"].items() if k != "sektor")
    return {
        "zgloszen": n,
        "w_pelni_automatycznie": auto / n if n else 0.0,
        "blad_wsrod_automatycznych": (auto_err / auto) if auto else None,
        "srednio_decyzji_do_zatwierdzenia": to_review / n if n else 0.0,
        "automatycznie_wg_kategorii": {c: v["auto"] / v["n"] for c, v in sorted(by_cat.items())},
    }


def format_reports(rep: dict) -> str:
    err = "—" if rep["blad_wsrod_automatycznych"] is None else f"{rep['blad_wsrod_automatycznych']:.1%}"
    cats = ", ".join(f"{c} {v:.0%}" for c, v in rep["automatycznie_wg_kategorii"].items())
    return (f"zgłoszenia w pełni automatyczne: {rep['w_pelni_automatycznie']:.1%} z {rep['zgloszen']} "
            f"(błędne wśród nich: {err})\n"
            f"średnio decyzji do zatwierdzenia na zgłoszenie: {rep['srednio_decyzji_do_zatwierdzenia']:.2f}\n"
            f"automatycznie wg kategorii: {cats}")


def format_summary(summary: dict) -> str:
    lines = [f"{'pytanie':<12}{'trafność':>10}{'próg':>8}{'automat':>10}{'błąd auto':>12}"]
    for name, s in summary.items():
        err = "—" if s["error_when_auto"] is None else f"{s['error_when_auto']:.1%}"
        lines.append(f"{name:<12}{s['accuracy']:>10.1%}{s['threshold']:>8.2f}{s['coverage']:>10.1%}{err:>12}")
    return "\n".join(lines)
