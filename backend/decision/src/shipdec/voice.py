"""Potok głosowy: nagranie -> STT (gałąź stt) -> porządkowanie qwen (gałąź moj-llm) -> Basal.

Etap STT robi scripts/stt_batch.py (osobne środowisko). Tutaj etapy 2 i 3:
  - qwen porządkuje tekst z STT (my_folder/przetworz.py; tylko tekst, bez metadanych),
  - Basal ocenia OBA warianty: surowy tekst z STT i tekst po qwenie (eksperyment z cleaning-eval
    pokazał, że czyszczenie nie zawsze pomaga), decyzje jak na serwerze (contract.to_decision).

Wynik: results/voice/<nagranie>.json (wszystkie etapy, czasy) + results/voice/raport.md.
Nagrania nie mają etykiet wzorcowych — to test przejścia całego potoku, nie pomiar trafności.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .config import load_questions
from .contract import assignees, to_decision
from .generate import read_jsonl
from .ship import SECTOR_LABELS

FIELDS = ("priority", "dept", "route_role", "assignee", "sector", "needs_officer")


def _decide(backend, text: str, questions: dict, thresholds: dict) -> dict:
    t0 = time.perf_counter()
    resp = backend.decide(text, questions)
    dec = to_decision(resp["answers"], thresholds, assignees())
    dec["basal_s"] = round(time.perf_counter() - t0, 1)
    return dec


def run_voice(stt_jsonl: str | Path, out_dir: str | Path, backend, llm_dir: str | Path | None,
              questions_path: str | Path | None = None) -> list[dict]:
    questions, thresholds = load_questions(questions_path) if questions_path else load_questions()
    przetworz = None
    if llm_dir:
        from .clean import _przetworz_fn
        przetworz, _ = _przetworz_fn(llm_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for s in read_jsonl(stt_jsonl):
        name = Path(s["audio"]).name
        row = {"audio": name, "stt": s}
        if not s["text"].strip():
            row["note"] = s.get("error") or "STT nie rozpoznał mowy — trzeba nagrać ponownie"
            rows.append(row)
            continue
        if przetworz:
            t0 = time.perf_counter()
            c = przetworz({"text": s["text"]})
            row["qwen"] = {"text": c["tresc"], "lang": c.get("jezyk"), "unclear": bool(c.get("niejednoznaczne")),
                           "qwen_s": round(time.perf_counter() - t0, 1)}
        row["basal_raw"] = _decide(backend, s["text"], questions, thresholds)
        if "qwen" in row:
            row["basal_clean"] = _decide(backend, row["qwen"]["text"], questions, thresholds)
        (out_dir / f"{Path(name).stem}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
        print(f"[Basal] {name}: {_short(row.get('basal_clean') or row['basal_raw'])}", file=sys.stderr, flush=True)
        rows.append(row)
    (out_dir / "raport.md").write_text(report_md(rows), encoding="utf-8")
    return rows


def _short(d: dict) -> str:
    who = d.get("assignee") or d.get("route_role")
    sec = SECTOR_LABELS.get(d.get("sector") or "", d.get("sector"))
    return f"P{d['priority']}, {d['dept']}, {who}, {sec}{', do oficera' if d['needs_officer'] else ''}"


def report_md(rows: list[dict]) -> str:
    out = ["# Potok głosowy: nagranie → STT → qwen → Basal", "",
           "Nagrania nie mają etykiet wzorcowych: tu widać, co wychodzi na każdym etapie i ile to trwa.", ""]
    for r in rows:
        s = r["stt"]
        out += [f"## {r['audio']}", "", f"**STT** ({s['model']}, {s['device']}, {s['stt_s']} s): {s['text'] or '—'}", ""]
        if "note" in r:
            out += [f"_{r['note']}_", ""]
            continue
        if "qwen" in r:
            q = r["qwen"]
            out += [f"**qwen** ({q['qwen_s']} s{', niejednoznaczne' if q['unclear'] else ''}): {q['text']}", ""]
        cols = [("STT", r["basal_raw"])] + ([("qwen", r["basal_clean"])] if "basal_clean" in r else [])
        out += ["| Basal na tekście z → | " + " | ".join(c for c, _ in cols) + " |",
                "|---|" + "---|" * len(cols)]
        for f in FIELDS:
            vals = []
            for _, d in cols:
                v = d.get(f)
                v = f"P{v}" if f == "priority" else SECTOR_LABELS.get(v, v) if f == "sector" else v
                vals.append(str(v))
            out.append(f"| {f} | " + " | ".join(vals) + " |")
        out.append("| czas Basala [s] | " + " | ".join(str(d["basal_s"]) for _, d in cols) + " |")
        conf = lambda d: ", ".join(f"{k} {v['value']} ({v['confidence']:.2f})" for k, v in d["_basal"]["decisions"].items())
        out.append("")
        out += [f"Pewności Basala ({c}): {conf(d)}" + "  " for c, d in cols]
        total = s["stt_s"] + r.get("qwen", {}).get("qwen_s", 0) + (r.get("basal_clean") or r["basal_raw"])["basal_s"]
        out += ["", f"Czas całego potoku (STT + qwen + Basal): **{total:.1f} s**", ""]
    return "\n".join(out)
