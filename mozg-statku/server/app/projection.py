"""Projekcja: aktualny stan zgłoszenia = złożenie (fold) jego zdarzeń z rejestru.

Nigdzie nie trzymamy „stanu” osobno — zawsze da się go odtworzyć z historii, więc
oficer, armator i audytor widzą to samo. Tę samą funkcję używa pipeline, żeby
zdecydować o kolejnym kroku (i dzięki temu przetwarzanie jest wznawialne po awarii).
"""
from __future__ import annotations

from typing import Any, Optional

# status -> co oznacza dla UI
STATUSES = [
    "recorded",                # nagranie przyjęte na serwer
    "transcribed",             # tekst gotowy
    "refined",                 # raport przerobiony (Daniel)
    "structured",              # formularz gotowy (LLM)
    "checked",                 # sprawdzone z czujnikami, zaraz pytanie zwrotne
    "awaiting_clarification",  # czekamy na odpowiedź załoganta
    "clarified",               # odpowiedź przyszła, przetwarzamy
    "pending_approval",        # na tablecie oficera (mała pewność) albo tuż przed auto-zatwierdzeniem
    "approved", "rejected",
    "assigned", "in_progress", "closed",
    "failed",
]
OPEN_STATUSES = set(STATUSES) - {"rejected", "closed"}


def new_state(report_id: str) -> dict[str, Any]:
    return {
        "report_id": report_id,
        "status": None,
        "created_ts": None,
        "updated_ts": None,
        "crew_id": None,
        "actor": None,
        "device": None,
        "audio": None,
        "transcript": None,
        "refined": None,
        "form": None,
        "structured_round": -1,
        "decision": None,
        "priority": None,
        "route_role": None,
        "dept": None,
        "unresolved_clarification": False,
        "clarifications": [],
        "approval": None,
        "tasks": [],
        "failures": [],
        "status_before_fail": None,
        "last_event_type": None,
        "event_count": 0,
    }


def apply(st: dict[str, Any], ev: dict[str, Any]) -> dict[str, Any]:
    t, p = ev["type"], ev.get("payload") or {}
    st["event_count"] += 1
    st["last_event_type"] = t
    st["updated_ts"] = ev["ts"]

    if t == "report.recorded":
        st["status"] = "recorded"
        st["created_ts"] = ev["ts"]
        st["crew_id"] = p.get("crew_id")
        st["actor"] = ev.get("actor")
        st["device"] = ev.get("device")
        st["audio"] = p.get("audio")
        st["lang_hint"] = p.get("lang_hint")

    elif t == "report.transcribed":
        if p.get("kind") == "clarification":
            idx = p.get("clarification_index", len(st["clarifications"]) - 1)
            if 0 <= idx < len(st["clarifications"]):
                st["clarifications"][idx]["answer_text"] = p.get("text")
                st["clarifications"][idx]["answer_lang"] = p.get("lang")
            st["status"] = "clarified"
        else:
            st["transcript"] = {k: p.get(k) for k in ("text", "lang", "duration_s", "model")}
            st["status"] = "transcribed"

    elif t == "report.refined":
        st["refined"] = {k: p.get(k) for k in ("text", "lang", "changes")}
        st["status"] = "refined"

    elif t == "report.structured":
        st["form"] = p.get("form")
        st["structured_round"] = p.get("round", st["structured_round"] + 1)
        if st["form"]:
            st["priority"] = st["form"].get("priority", st["priority"])
        st["status"] = "structured"

    elif t == "report.sensor_checked":
        st["decision"] = p
        st["priority"] = p.get("priority", st["priority"])
        st["route_role"] = p.get("route_role")
        st["dept"] = p.get("dept")
        st["unresolved_clarification"] = bool(p.get("unresolved_clarification"))
        st["status"] = "checked" if p.get("needs_clarification") else "pending_approval"

    elif t == "report.clarification_requested":
        st["clarifications"].append({
            "round": p.get("round"),
            "question": p.get("question"),
            "question_en": p.get("question_en"),
            "lang": p.get("lang"),
            "field": p.get("field"),
            "to": p.get("to"),
            "asked_ts": ev["ts"],
            "answer_text": None,
            "answer_lang": None,
            "answer_audio": None,
            "answered_ts": None,
        })
        st["status"] = "awaiting_clarification"

    elif t == "report.clarified":
        if st["clarifications"]:
            c = st["clarifications"][-1]
            c["answer_text"] = p.get("text")
            c["answer_lang"] = p.get("lang")
            c["answer_audio"] = p.get("audio")
            c["answered_ts"] = ev["ts"]
        st["status"] = "clarified"

    elif t == "report.approved":
        st["approval"] = {"decision": "approve", "by": ev.get("actor"), "ts": ev["ts"], "auto": bool(p.get("auto")), **p}
        if p.get("form"):
            st["form"] = p["form"]
        st["status"] = "approved"

    elif t == "report.rejected":
        st["approval"] = {"decision": "reject", "by": ev.get("actor"), "ts": ev["ts"], **p}
        st["status"] = "rejected"

    elif t.startswith("task."):
        tid = p.get("task_id")
        task = next((x for x in st["tasks"] if x["task_id"] == tid), None)
        if t == "task.assigned":
            if task is None:
                task = {"task_id": tid, "report_id": st["report_id"]}
                st["tasks"].append(task)
            task.update({"assignee": p.get("assignee"), "assigned_by": ev.get("actor"),
                         "title": p.get("title"), "priority": p.get("priority"),
                         "status": "assigned", "assigned_ts": ev["ts"]})
            st["status"] = "assigned"
        elif task is not None:
            if t == "task.acknowledged":
                task.update({"status": "acknowledged", "ack_ts": ev["ts"]})
                st["status"] = "in_progress"
            elif t == "task.escalated":
                task.update({"status": "escalated", "escalated_ts": ev["ts"]})
            elif t == "task.closed":
                task.update({"status": "closed", "closed_ts": ev["ts"], "close_note": p.get("note")})
                if all(x["status"] == "closed" for x in st["tasks"]):
                    st["status"] = "closed"

    elif t == "report.failed":
        if st["status"] != "failed":
            st["status_before_fail"] = st["status"]
        st["failures"].append({"stage": p.get("stage"), "error": p.get("error"), "ts": ev["ts"]})
        st["status"] = "failed"

    elif t == "report.retry":
        if st["status"] == "failed":
            st["status"] = st["status_before_fail"] or "recorded"

    return st


def project(events: list[dict]) -> Optional[dict]:
    if not events:
        return None
    st = new_state(events[0]["report_id"])
    for ev in events:
        apply(st, ev)
    return st


def summary(st: dict) -> dict:
    """Lekka wersja do list (tablet oficera)."""
    form = st.get("form") or {}
    last_q = st["clarifications"][-1] if st["clarifications"] else None
    return {
        "report_id": st["report_id"],
        "status": st["status"],
        "created_ts": st["created_ts"],
        "updated_ts": st["updated_ts"],
        "crew_id": st["crew_id"],
        "actor": st["actor"],
        "priority": st["priority"],
        "route_role": st["route_role"],
        "equipment": form.get("equipment"),
        "sfi_code": form.get("sfi_code"),
        "text_en": form.get("text_en"),
        "transcript": (st.get("transcript") or {}).get("text"),
        "refined": (st.get("refined") or {}).get("text"),
        "confidence": form.get("confidence"),
        "needs_officer": (st.get("decision") or {}).get("needs_officer"),
        "approval_reason": (st.get("decision") or {}).get("approval_reason"),
        "auto_approved": bool((st.get("approval") or {}).get("auto")),
        "lang": (st.get("transcript") or {}).get("lang"),
        "checks": (st.get("decision") or {}).get("checks", []),
        "question": last_q["question"] if last_q and st["status"] == "awaiting_clarification" else None,
        "unresolved_clarification": st["unresolved_clarification"],
        "tasks": st["tasks"],
        "has_audio": bool(st.get("audio")),
    }
