"""Mapowanie: nowe zdarzenie w rejestrze -> powiadomienia na tematy MQTT/SSE.

Tematy (zgodnie z planem):
  ship/{id}/events            każde zdarzenie (wszystkie widoki)
  ship/{id}/eng/new           nowe zgłoszenie maszynowni gotowe do zatwierdzenia
  role/{rola}/approve         prośba o zatwierdzenie (tylko przy małej pewności)
  person/{crew_id}            pytania zwrotne, zadania, zmiana statusu własnego zgłoszenia
  ship/{id}/bridge/alert      priorytet 5
  ship/{id}/sync              stan kolejki na ląd (retained) — publikuje outbox
  ship/{id}/sensors/{tag}     odczyty czujników (publikuje symulator, nie serwer)
"""
from __future__ import annotations

from .eventstore import EventStore
from .hub import Hub
from .projection import project, summary


class Notifier:
    def __init__(self, store: EventStore, hub: Hub, ship_id: str):
        self.store, self.hub, self.ship = store, hub, ship_id

    def __call__(self, ev: dict) -> None:
        s = self.ship
        self.hub.publish(f"ship/{s}/events", {k: v for k, v in ev.items() if k not in ("prev_hash",)})
        t, p, rid = ev["type"], ev.get("payload") or {}, ev.get("report_id")

        if t == "report.clarification_requested" and p.get("to"):
            self.hub.publish(f"person/{p['to']}", {
                "type": "clarification", "report_id": rid, "question": p.get("question"),
                "lang": p.get("lang"), "question_en": p.get("question_en"), "field": p.get("field"),
                "round": p.get("round"), "ts": ev["ts"]})
            return

        if t == "report.sensor_checked" and not p.get("needs_clarification"):
            st = project(self.store.for_report(rid))
            summ = summary(st)
            auto = bool(p.get("auto_approve"))
            msg = {"type": "auto_approved" if auto else "approval_request", "report": summ, "ts": ev["ts"]}
            if not auto:  # oficer dostaje prośbę tylko przy małej pewności
                self.hub.publish(f"role/{p.get('route_role') or 'chief_engineer'}/approve", msg)
            if (p.get("dept") or "engine") == "engine":
                self.hub.publish(f"ship/{s}/eng/new", msg)
            if (p.get("priority") or 0) >= 5:
                self.hub.publish(f"ship/{s}/bridge/alert", {"type": "alert", "report": summ, "ts": ev["ts"]})
            return

        if t == "task.assigned" and p.get("assignee"):
            self.hub.publish(f"person/{p['assignee']}", {
                "type": "task", "task_id": p.get("task_id"), "report_id": rid, "title": p.get("title"),
                "priority": p.get("priority"), "assigned_by": ev.get("actor"), "ts": ev["ts"]})

        if t in ("report.approved", "report.rejected", "report.failed"):
            st = project(self.store.for_report(rid))
            if st and st.get("crew_id"):
                self.hub.publish(f"person/{st['crew_id']}", {
                    "type": "report_update", "report_id": rid, "status": st["status"], "ts": ev["ts"]})
