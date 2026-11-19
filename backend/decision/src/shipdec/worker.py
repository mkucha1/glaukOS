"""Worker statku: Supabase -> nagranie -> STT -> qwen -> Basal -> zdarzenia z powrotem do Supabase.

Kontrakt jak w supabase/README.md ("Przepływ nagrania"):
  1. telefon wysyła audio do Storage (bucket `recordings`) i zdarzenie `report.recorded`,
  2. worker co kilka sekund pyta o nowe `report.recorded` (i `report.clarification_answered`),
  3. pobiera audio kluczem secret, przepuszcza przez potok i dopisuje zdarzenia z tym samym report_id:
       report.transcribed  {text, lang}                        actor system:whisper
       report.structured   ReportForm (+ `decision` z Basala)  actor system:basal
     albo report.clarification_requested, gdy nagranie jest puste / bez treści,
  4. odpowiedź na pytanie zwrotne (`report.clarification_answered`, tekst albo audio):
       report.clarified {answer} -> poprawiony report.structured.

Etapy:
  STT   — serwis zespołu (gałąź stt, POST /transcribe), uruchomiony lokalnie na CPU,
  qwen  — my_folder/przetworz.py (gałąź moj-llm), SUMMARY_LANGUAGE=en: wpis do dziennika po angielsku,
  Basal — decyzje na tekście z STT (eksperyment cleaning-eval: surowy tekst wypada nie gorzej).

Frontend czyta ReportForm (frontend/src/types.ts); dodatkowe pole `decision` niesie wyniki Basala
(dział, sugerowane stanowisko i osoba, raport DPA, pewności) — pokazuje je ReportDetail.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load_questions
from .contract import to_decision
from .ship import SECTOR_LABELS
from .supa import Supabase, SupabaseError

RECORDED, ANSWERED = "report.recorded", "report.clarification_answered"
ASK_AGAIN = {
    "pl": "Nie zrozumiałem nagrania. Powiedz jeszcze raz: co, gdzie i co się dzieje?",
    "en": "I could not understand the recording. Please say again: what, where and what is wrong?",
}


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class Pipeline:
    """STT -> qwen -> Basal. Każdy etap można podmienić (testy)."""

    def __init__(self, stt_url: str, basal, llm_dir: str | Path, questions_path=None):
        self.stt_url = stt_url.rstrip("/")
        self.basal = basal
        os.environ.setdefault("SUMMARY_LANGUAGE", "en")     # wpis do dziennika (text_en) po angielsku
        from .clean import _przetworz_fn
        self.przetworz, _ = _przetworz_fn(llm_dir)
        self.questions, self.thresholds = load_questions(questions_path) if questions_path else load_questions()

    def stt(self, audio: bytes, filename: str) -> str:
        import httpx
        r = httpx.post(f"{self.stt_url}/transcribe", files={"file": (filename, audio, "application/octet-stream")},
                       timeout=300.0)
        r.raise_for_status()
        return r.json()["text"]

    def clean(self, text: str) -> dict:
        out = self.przetworz({"text": text})
        return {"text_en": out["tresc"], "lang": out.get("jezyk") or "und", "unclear": bool(out.get("niejednoznaczne"))}

    def decide(self, text: str) -> dict:
        resp = self.basal.decide(text, self.questions)
        return to_decision(resp["answers"], self.thresholds, {})


def _title(text_en: str) -> str:
    """Krótki tytuł zgłoszenia (pole `equipment` we frontendzie): pierwsza fraza wpisu."""
    head = text_en.split(":")[0] if ":" in text_en[:60] else text_en
    for sep in (". ", "; ", ", "):
        head = head.split(sep)[0]
    head = head.strip(" .")
    return head if len(head) <= 48 else head[:45].rsplit(" ", 1)[0] + "…"


def build_form(text_en: str, lang: str, dec: dict, assignee_actor: str | None) -> dict:
    """ReportForm (frontend/src/types.ts) + `decision` z wynikami Basala."""
    b = dec["_basal"]["decisions"]
    sector = dec.get("sector")
    gating = [v["confidence"] for k, v in b.items() if k in ("dzial", "osoba", "raport_dpa")]
    return {
        "equipment": _title(text_en),
        "sfi_code": "",
        "priority": dec["priority"],
        "location": SECTOR_LABELS.get(sector, "") if sector else "",
        "text_en": text_en,
        "lang_original": lang,
        "missing_fields": [],
        "confidence": round(min(gating), 2) if gating else 0.0,
        "decision": {
            "model": "basal",
            "department": dec["dept"],
            "approver_position": dec["route_role"],
            "position": dec["_basal"]["assignee_role"],
            "assignee": assignee_actor,
            "dpa_report": dec["_basal"]["dpa_report"],
            "needs_officer": dec["needs_officer"],
            "needs_review": dec["_basal"]["needs_review"],
            "sector": sector,
            "confidences": {k: v["confidence"] for k, v in b.items()},
            "answers": {k: v["value"] for k, v in b.items()},
        },
    }


class Worker:
    def __init__(self, sb: Supabase, pipe: Pipeline, since: datetime, poll_s: float = 2.0, briefing_llm=None):
        self.sb, self.pipe, self.since, self.poll_s = sb, pipe, since, poll_s
        self.done: set[str] = set()
        self.briefings_on = True          # wyłącza się, gdy w bazie nie ma tabel z migracji briefings
        self.last_beat = 0.0
        from .briefing import ask_qwen
        self.briefing_llm = briefing_llm or ask_qwen

    # ---------- Supabase helpers
    def emit(self, report_id: str, type_: str, actor: str, payload: dict) -> None:
        self.sb.insert("events", {"event_id": str(uuid.uuid4()), "report_id": report_id, "type": type_,
                                  "actor": actor, "device": "ship-brain-worker", "payload": payload})

    def has_event(self, report_id: str, type_: str, **extra) -> bool:
        return bool(self.sb.select("events", select="event_id", report_id=f"eq.{report_id}", type=f"eq.{type_}",
                                   limit="1", **extra))

    def report_events(self, report_id: str) -> list[dict]:
        return self.sb.select("events", select="type,payload,ts", report_id=f"eq.{report_id}", order="ts.asc")

    def assignee_for(self, position: str | None) -> str | None:
        if not position:
            return None
        rows = self.sb.select("crew", select="actor,on_duty", position=f"eq.{position}", order="on_duty.desc,name.asc",
                              limit="1")
        return rows[0]["actor"] if rows else None

    def audio(self, path: str) -> bytes:
        return self.sb.download("recordings", path)

    # ---------- potok
    def structure(self, report_id: str, raw_text: str, c: dict | None = None) -> None:
        t0 = time.perf_counter()
        c = c or self.pipe.clean(raw_text)
        if c["unclear"]:
            self.emit(report_id, "report.clarification_requested", "system:basal",
                      {"question": ASK_AGAIN.get(c["lang"], ASK_AGAIN["en"])})
            log(f"  {report_id[:8]} bez treści -> pytanie zwrotne")
            return
        t1 = time.perf_counter()
        dec = self.pipe.decide(raw_text)
        form = build_form(c["text_en"], c["lang"], dec, self.assignee_for(dec["_basal"]["assignee_role"]))
        form["decision"]["timings_s"] = {"qwen": round(t1 - t0, 1), "basal": round(time.perf_counter() - t1, 1)}
        self.emit(report_id, "report.structured", "system:basal", form)
        d = form["decision"]
        log(f"  {report_id[:8]} P{form['priority']} {d['department']} -> {d['position']} ({d['assignee'] or 'brak w crew'}), "
            f"{form['location']}{', DPA' if d['dpa_report'] else ''}{', do oficera' if d['needs_officer'] else ''}")

    def transcribe(self, report_id: str, path: str) -> str:
        t0 = time.perf_counter()
        text = self.pipe.stt(self.audio(path), Path(path).name)
        log(f"  {report_id[:8]} STT {time.perf_counter() - t0:.1f}s: {text[:100]!r}")
        return text

    def on_recorded(self, ev: dict) -> None:
        rid = ev["report_id"]
        if self.has_event(rid, "report.transcribed") or self.has_event(rid, "report.clarification_requested"):
            return                                   # już obsłużone (np. przed restartem workera)
        path = (ev.get("payload") or {}).get("audio_path")
        if not path:
            log(f"  {rid[:8]} bez audio_path — pomijam")
            return
        log(f"nowe zgłoszenie {rid[:8]} od {ev['actor']}")
        text = self.transcribe(rid, path)
        if not text.strip():
            self.emit(rid, "report.clarification_requested", "system:whisper", {"question": ASK_AGAIN["en"]})
            return
        c = self.pipe.clean(text)                     # qwen: wpis po angielsku + język mówiącego
        self.emit(rid, "report.transcribed", "system:whisper", {"text": text, "lang": c["lang"]})
        self.structure(rid, text, c)

    def on_answered(self, ev: dict) -> None:
        rid, eid = ev["report_id"], ev["event_id"]
        if self.has_event(rid, "report.clarified", **{"payload->>answer_event_id": f"eq.{eid}"}):
            return
        p = ev.get("payload") or {}
        answer = p.get("answer") or (self.transcribe(rid, p["audio_path"]) if p.get("audio_path") else "")
        log(f"odpowiedź na pytanie {rid[:8]}: {answer!r}")
        self.emit(rid, "report.clarified", "system:basal", {"answer": answer, "answer_event_id": eid})
        texts = [e["payload"].get("text", "") for e in self.report_events(rid) if e["type"] == "report.transcribed"]
        full = " — ".join(t for t in texts + [answer] if t.strip())
        if full.strip():
            if not texts:                              # pierwsze nagranie było puste: odpowiedź jest treścią
                self.emit(rid, "report.transcribed", "system:whisper", {"text": answer, "lang": "und"})
            self.structure(rid, full)

    # ---------- briefing na zmianę wachty (tabela `briefings`)
    def heartbeat(self) -> None:
        if not self.briefings_on or time.monotonic() - self.last_beat < 10:
            return
        self.last_beat = time.monotonic()
        try:
            self.sb.update("worker_status", {"last_seen": _iso(datetime.now(timezone.utc)),
                                             "info": {"briefing_model": os.getenv("LLM_MODEL", "qwen3.5:4b")}}, id="eq.1")
        except SupabaseError as e:
            self._no_briefings(e)

    def _no_briefings(self, e) -> None:
        self.briefings_on = False
        log(f"briefing qwenem wyłączony (brak tabel z migracji 20261119160000_glaukos_briefings.sql?): {e}")

    def briefings(self) -> int:
        if not self.briefings_on:
            return 0
        from .briefing import write_briefing
        try:
            reqs = self.sb.select("briefings", select="*", status="eq.requested", order="requested_at.asc", limit="5",
                                  requested_at=f"gte.{_iso(datetime.now(timezone.utc) - timedelta(minutes=10))}")
        except SupabaseError as e:
            self._no_briefings(e)
            return 0
        for req in reqs:
            self.sb.update("briefings", {"status": "working"}, id=f"eq.{req['id']}", status="eq.requested")
            t0 = time.perf_counter()
            try:
                text = write_briefing(self.sb, req, self.briefing_llm)
                self.sb.update("briefings", {"status": "done", "text": text, "model": os.getenv("LLM_MODEL", "qwen3.5:4b"),
                                             "generated_at": _iso(datetime.now(timezone.utc))}, id=f"eq.{req['id']}")
                log(f"briefing {req['watch']} gotowy w {time.perf_counter() - t0:.1f}s")
            except Exception as e:  # noqa: BLE001 — strona wtedy robi briefing z szablonu
                self.sb.update("briefings", {"status": "failed", "error": repr(e)[:300]}, id=f"eq.{req['id']}")
                log(f"briefing {req['watch']} nieudany: {e!r}")
        return len(reqs)

    def tick(self) -> int:
        self.heartbeat()
        self.briefings()
        events = self.sb.select("events", select="event_id,report_id,type,actor,payload,ts",
                                type=f'in.("{RECORDED}","{ANSWERED}")', ts=f"gte.{_iso(self.since)}", order="ts.asc",
                                limit="50")
        n = 0
        for ev in events:
            if ev["event_id"] in self.done or not ev.get("report_id"):
                continue
            try:
                (self.on_recorded if ev["type"] == RECORDED else self.on_answered)(ev)
                self.done.add(ev["event_id"])
                n += 1
            except (SupabaseError, OSError, RuntimeError) as e:
                log(f"  błąd przy {ev['report_id'][:8]}: {e!r} — spróbuję ponownie")
        return n

    def run(self) -> None:
        log(f"worker działa: zgłoszenia od {self.since:%Y-%m-%d %H:%M} UTC, sprawdzam co {self.poll_s}s (Ctrl+C kończy)")
        while True:
            try:
                self.tick()
            except (SupabaseError, OSError) as e:
                log(f"Supabase niedostępny: {e!r}")
            time.sleep(self.poll_s)


def autopilot(sb: Supabase, on: bool | None = None) -> bool:
    """Odczytaj (on=None) albo ustaw ship_status.autopilot. Zwraca stan sprzed zmiany."""
    rows = sb.select("ship_status", select="autopilot", id="eq.1")
    before = bool(rows and rows[0]["autopilot"])
    if on is not None and on != before:
        sb.update("ship_status", {"autopilot": on, "updated_at": _iso(datetime.now(timezone.utc))}, id="eq.1")
    return before


def main_worker(args) -> None:
    from . import settings
    from .backends import get_backend
    sb = Supabase(settings.get("SUPABASE_URL"), settings.get("SUPABASE_SECRET_KEY"))
    pipe = Pipeline(args.stt_url, get_backend("basal", args.basal_url), args.llm_dir)
    was_on = autopilot(sb)
    if was_on and args.take_over:
        autopilot(sb, False)
        log("autopilot (scenariusz demo w bazie) wyłączony — zgłoszenia obsługuje ten worker")
    elif was_on:
        log("UWAGA: ship_status.autopilot = true — baza dopisze też scenariusz demo. Uruchom z --take-over.")
    since = datetime.now(timezone.utc) - timedelta(minutes=args.since_minutes)
    try:
        Worker(sb, pipe, since, args.poll).run()
    except KeyboardInterrupt:
        log("koniec")
    finally:
        if was_on and args.take_over and args.restore_autopilot:
            autopilot(sb, True)
            log("autopilot przywrócony")
