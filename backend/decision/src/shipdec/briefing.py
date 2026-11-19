"""Briefing na zmianę wachty pisany przez qwena (Ollama) z rejestru zgłoszeń w Supabase.

Strona wstawia prośbę do tabeli `briefings` (supabase/migrations/20261119160000_glaukos_briefings.sql),
worker ją widzi, zbiera zgłoszenia, które ta osoba może czytać (jak public.can_read: swój dział,
działy, które zatwierdza, zadania przydzielone jej), i prosi qwena o krótki tekst do odczytania na głos.
Do qwena idą tylko fakty z rejestru; model ma ich nie dopisywać.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from .ship import SECTOR_LABELS, main_sector, sector_of

DONE = {"report.rejected": "rejected", "task.closed": "closed"}
STATUS_OF = {
    "report.recorded": "recorded", "report.transcribed": "transcribed", "report.structured": "pending approval",
    "report.clarification_requested": "waiting for crew answer", "report.clarification_answered": "answered",
    "report.clarified": "clarified", "report.sensor_checked": "pending approval", "report.approved": "approved",
    "report.rejected": "rejected", "task.assigned": "assigned", "task.acknowledged": "in progress",
    "task.closed": "closed",
}

SYSTEM = (
    "You write a spoken watch handover briefing for the officer taking over the watch on a cargo ship. "
    "Use ONLY the facts in the JSON you get; never add equipment, numbers, names or events that are not there. "
    "Plain English, short sentences, no lists, no markdown, about 60-130 words, readable aloud in under a minute. "
    "Order: what needs action now (priority 1 first, say who holds it), accidents or near misses reported to the DPA, "
    "sensor mismatches, work in progress, then a count of minor open items. "
    "If there is nothing open, say so briefly. Start with 'Watch handover,' and the watch, end with 'End of handover.'"
)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def visible_departments(sb, requester: str) -> tuple[set[str], str | None]:
    crew = sb.select("crew", select="actor,position", id=f"eq.{requester}", limit="1")
    if not crew:
        return set(), None
    pos = sb.select("positions", select="department,approves", id=f"eq.{crew[0]['position']}", limit="1")
    depts = {pos[0]["department"], *pos[0]["approves"]} if pos else set()
    return depts, crew[0]["actor"]


def report_states(events: list[dict]) -> list[dict]:
    """Stan każdego zgłoszenia z ciągu jego zdarzeń (jak buildReport we frontendzie, uproszczone)."""
    by: dict[str, dict] = {}
    for e in sorted(events, key=lambda e: e["ts"]):
        rid = e.get("report_id")
        if not rid:
            continue
        r = by.setdefault(rid, {"report_id": rid, "department": e.get("department"), "created": e["ts"],
                                "reporter": None, "form": None, "assignee": None, "sensor_ok": None})
        r["updated"] = e["ts"]
        p = e.get("payload") or {}
        t = e["type"]
        if t == "report.recorded":
            r["reporter"] = e.get("actor")
        elif t == "report.structured":
            r["form"] = p
        elif t == "report.approved":
            r["form"] = p.get("form") or r["form"]
            r["assignee"] = p.get("assignee") or r["assignee"]
        elif t == "task.assigned":
            r["assignee"] = p.get("assignee") or r["assignee"]
        elif t == "report.sensor_checked":
            r["sensor_ok"] = p.get("matches")
        if t in STATUS_OF and not (r.get("status") in ("rejected", "closed")):
            r["status"] = STATUS_OF[t]
    return list(by.values())


def facts_for(reports: list[dict], win_from: datetime, win_to: datetime) -> list[dict]:
    """Zgłoszenia zmienione w czasie wachty + wszystkie wciąż otwarte, w zwięzłej postaci dla qwena."""
    out = []
    for r in reports:
        open_ = r.get("status") not in ("closed", "rejected")
        changed = win_from <= _parse(r["updated"]) <= win_to
        if not (open_ or changed):
            continue
        f = r.get("form") or {}
        d = f.get("decision") or {}
        sector = d.get("sector") or main_sector(sector_of(f.get("location") or "", f.get("equipment") or ""))
        out.append({
            "what": f.get("equipment") or "voice report not processed yet",
            "entry": (f.get("text_en") or "")[:300],
            "priority": f.get("priority"),
            "status": r.get("status"),
            "where": SECTOR_LABELS.get(sector, sector),
            "reported_by": r.get("reporter"),
            "assigned_to": r.get("assignee") or (f"suggested: {d['assignee']}" if d.get("assignee") else None),
            "dpa_report": bool(d.get("dpa_report")) or None,
            "sensor_matches": r.get("sensor_ok"),
            "changed_this_watch": changed,
        })
    out.sort(key=lambda x: (x["status"] in ("closed", "rejected"), x["priority"] or 9))
    return out[:25]


def ask_qwen(watch: str, facts: list[dict], lang: str = "en") -> str:
    import httpx
    base = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    body = {"model": os.getenv("LLM_MODEL", "qwen3.5:4b"), "temperature": 0.2,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": json.dumps({"watch": watch, "reports": facts}, ensure_ascii=False)}]}
    effort = os.getenv("LLM_REASONING_EFFORT", "none")
    if effort:
        body["reasoning_effort"] = effort                 # bez "thinking": kilka sekund zamiast kilkudziesięciu
    r = httpx.post(f"{base}/chat/completions", json=body, timeout=120.0)
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()
    if "</think>" in text:
        text = text.split("</think>", 1)[1].strip()
    return " ".join(text.replace("*", "").split())


def write_briefing(sb, req: dict, llm=ask_qwen) -> str:
    depts, actor = visible_departments(sb, req["requested_by"])
    win_from, win_to = _parse(req["window_from"]), _parse(req["window_to"])
    since = (min(win_from, datetime.now(timezone.utc)) - timedelta(days=7)).isoformat()
    events = sb.select("events", select="report_id,type,actor,payload,ts,department", ts=f"gte.{since}",
                       order="ts.asc", limit="5000")
    mine = {e["report_id"] for e in events if e["type"] == "task.assigned"
            and (e.get("payload") or {}).get("assignee") == actor}
    events = [e for e in events if e.get("department") in depts or e.get("report_id") in mine]
    facts = facts_for(report_states(events), win_from, win_to)
    if not facts:
        return f"Watch handover, {req['watch'].replace('-', ' to ')}. No reports for your departments. End of handover."
    return llm(req["watch"], facts, req.get("lang") or "en")
