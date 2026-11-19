"""Przetwarzanie zgłoszenia jako maszyna stanów sterowana rejestrem zdarzeń.

Kluczowe właściwości:
  * Kolejny krok wynika WYŁĄCZNIE z projekcji rejestru (`next_step`) — po restarcie serwera
    `recover()` dokańcza przerwane zgłoszenia, nic nie przepada.
  * Każdy krok ma deterministyczny event_id (uuid5 z report_id + krok + runda), więc nawet
    gdyby krok wykonał się dwa razy, rejestr przyjmie wynik tylko raz.
  * Jeden worker (GPU i tak jest jedno) + zbiór `inflight` => moduły AI nigdy nie liczą
    tego samego zgłoszenia równolegle ani drugi raz.
  * Ciężkie wywołania (Whisper, LLM) idą do wątków — API odpowiada w tym czasie normalnie.
"""
from __future__ import annotations

import asyncio
import time
import traceback
from typing import Any, Callable

from pydantic import BaseModel

from .config import Settings
from .contracts import Decision, RefineResult, ReportForm, TranscriptResult
from .eventstore import EventStore, det_id
from .plugin_loader import Plugins
from .projection import project
from .sensors import SensorCache


def next_step(st: dict | None) -> str | None:
    if not st:
        return None
    s = st["status"]
    if s == "recorded":
        return "transcribe" if st.get("audio") else None
    if s == "transcribed":
        return "refine"
    if s == "refined":
        return "structure"
    if s == "structured":
        return "check"
    if s == "checked":
        return "ask"
    if s == "pending_approval" and (st.get("decision") or {}).get("auto_approve") and not st.get("approval"):
        return "auto_approve"
    if s == "clarified" and st["clarifications"]:
        c = st["clarifications"][-1]
        if c.get("answer_text") is None:
            return "transcribe_clarification" if c.get("answer_audio") else None
        return "apply_clarification"
    return None


def _validated(model: type[BaseModel], data: Any) -> dict:
    """Waliduje wynik pluginu, ale zachowuje pola dodatkowe (także te z '_' na początku)."""
    if isinstance(data, BaseModel):
        data = data.model_dump()
    if not isinstance(data, dict):
        raise TypeError(f"plugin returned {type(data).__name__}, expected dict")
    return {**data, **model.model_validate(data).model_dump()}


class Pipeline:
    def __init__(self, store: EventStore, sensors: SensorCache, plugins: Plugins, settings: Settings,
                 crew: dict[str, dict], equipment: dict):
        self.store, self.sensors, self.plugins, self.settings = store, sensors, plugins, settings
        self.crew, self.equipment = crew, equipment
        self.inflight: set[str] = set()
        self.queue: asyncio.Queue[str] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self.processed_steps = 0

    # ------------------------------------------------------------ cykl życia
    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self._task = asyncio.create_task(self._worker(), name="pipeline")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def kick(self, report_id: str) -> None:
        """Bezpieczne z dowolnego wątku."""
        if self._loop and self.queue is not None:
            self._loop.call_soon_threadsafe(self.queue.put_nowait, report_id)

    def recover(self) -> int:
        n = 0
        for rid in self.store.report_ids():
            if next_step(project(self.store.for_report(rid))):
                self.kick(rid)
                n += 1
        if n:
            print(f"[pipeline] wznawiam {n} przerwanych zgłoszeń")
        return n

    async def _worker(self) -> None:
        assert self.queue is not None
        while True:
            rid = await self.queue.get()
            try:
                await self.advance(rid)
            except Exception:
                traceback.print_exc()

    # ------------------------------------------------------------ logika
    async def advance(self, rid: str) -> None:
        if rid in self.inflight:
            return
        self.inflight.add(rid)
        try:
            for _ in range(25):  # bezpiecznik
                st = project(self.store.for_report(rid))
                step = next_step(st)
                if step is None:
                    return
                if not await getattr(self, f"_step_{step}")(st):
                    return
                self.processed_steps += 1
        finally:
            self.inflight.discard(rid)

    def _ctx(self, st: dict, round_: int) -> dict:
        return {"report_id": st["report_id"], "crew": self.crew.get(st.get("crew_id") or "", {}),
                "equipment": self.equipment, "round": round_,
                "ollama_url": __import__("os").getenv("OLLAMA_URL", "http://ollama:11434")}

    async def _call(self, st: dict, stage: str, fn: Callable, *args: Any) -> tuple[Any, int] | None:
        attempts = 1 + max(0, self.settings.plugin_retries)
        err = None
        for a in range(attempts):
            t0 = time.perf_counter()
            try:
                res = await asyncio.to_thread(fn, *args)
                return res, int((time.perf_counter() - t0) * 1000)
            except Exception as e:
                err = e
                print(f"[pipeline] {stage} failed for {st['report_id']} (attempt {a + 1}/{attempts}): {e!r}")
                await asyncio.sleep(0.3 * (a + 1))
        self.store.append("report.failed", {"stage": stage, "error": repr(err)[:500]},
                          report_id=st["report_id"], actor=f"system:{stage}",
                          event_id=det_id(st["report_id"], "failed", stage, len(st["failures"])))
        return None

    def _audio_path(self, rel: str) -> str:
        return str(self.settings.audio_dir / rel)

    async def _step_transcribe(self, st: dict) -> bool:
        r = await self._call(st, "stt", self.plugins.transcribe,
                             self._audio_path(st["audio"]["file"]), st.get("lang_hint"))
        if r is None:
            return False
        try:
            data = _validated(TranscriptResult, r[0])
        except Exception as e:
            return self._bad_output(st, "stt", e)
        self.store.append("report.transcribed", {"kind": "report", **data, "ms": r[1]},
                          report_id=st["report_id"], actor="system:stt",
                          event_id=det_id(st["report_id"], "transcribed", "main"))
        return True

    async def _step_refine(self, st: dict) -> bool:
        tr = st["transcript"] or {}
        r = await self._call(st, "refine", self.plugins.refine,
                             tr.get("text") or "", tr.get("lang") or "und", self._ctx(st, 0))
        if r is None:
            return False
        try:
            data = _validated(RefineResult, r[0])
        except Exception as e:
            return self._bad_output(st, "refine", e)
        data["lang"] = data.get("lang") or tr.get("lang")
        self.store.append("report.refined", {**data, "ms": r[1]}, report_id=st["report_id"], actor="system:refine",
                          event_id=det_id(st["report_id"], "refined"))
        return True

    async def _step_structure(self, st: dict) -> bool:
        tr = st.get("refined") or st["transcript"] or {}
        r = await self._call(st, "brain.structure", self.plugins.structure,
                             tr.get("text") or "", tr.get("lang") or "und", self._ctx(st, 0))
        if r is None:
            return False
        try:
            form = _validated(ReportForm, r[0])
        except Exception as e:
            return self._bad_output(st, "brain.structure", e)
        self.store.append("report.structured", {"form": form, "round": 0, "ms": r[1]},
                          report_id=st["report_id"], actor="system:llm",
                          event_id=det_id(st["report_id"], "structured", 0))
        return True

    async def _step_check(self, st: dict) -> bool:
        rnd = max(0, st["structured_round"])
        r = await self._call(st, "brain.check", self.plugins.check,
                             st["form"] or {}, self.sensors, self._ctx(st, rnd))
        if r is None:
            return False
        try:
            dec = _validated(Decision, r[0])
        except Exception as e:
            return self._bad_output(st, "brain.check", e)
        wants = dec.get("clarification") is not None
        can_ask = len(st["clarifications"]) < self.settings.max_clarify_rounds
        needs_clar, unresolved = wants and can_ask, wants and not can_ask
        needs_officer, reason = self._needs_officer(st["form"] or {}, dec, unresolved)
        payload = {**dec, "round": rnd, "ms": r[1],
                   "needs_clarification": needs_clar,
                   "unresolved_clarification": unresolved,
                   "needs_officer": needs_officer,
                   "auto_approve": not needs_clar and not needs_officer,
                   "approval_reason": reason}
        self.store.append("report.sensor_checked", payload, report_id=st["report_id"], actor="system:rules",
                          event_id=det_id(st["report_id"], "sensor_checked", rnd))
        return True

    def _needs_officer(self, form: dict, dec: dict, unresolved: bool) -> tuple[bool, str]:
        """Oficer zatwierdza tylko przy małej pewności. Rozbieżność z czujnikiem albo pytanie bez
        odpowiedzi też oznaczają małą pewność. Maciej może to nadpisać polem needs_officer."""
        conf = float(form.get("confidence") or 0.0)
        thr = self.settings.auto_approve_confidence
        if dec.get("needs_officer") is not None:
            return bool(dec["needs_officer"]), "decided by rules (needs_officer)"
        if unresolved:
            return True, "clarification left unanswered"
        if any(c.get("ok") is False for c in dec.get("checks") or []):
            return True, "report does not match sensor"
        if conf < thr:
            return True, f"low confidence {conf:.2f} < {thr:.2f}"
        return False, f"confidence {conf:.2f} >= {thr:.2f}, sensors consistent"

    async def _step_auto_approve(self, st: dict) -> bool:
        dec, rid = st["decision"] or {}, st["report_id"]
        form = st.get("form") or {}
        self.store.append("report.approved", {"auto": True, "reason": dec.get("approval_reason"),
                                              "confidence": form.get("confidence"), "assignee": dec.get("assignee")},
                          report_id=rid, actor="system:auto_approve", event_id=det_id(rid, "decision"))
        if dec.get("assignee"):
            task_id = det_id(rid, "task", 1)
            self.store.append("task.assigned", {
                "task_id": task_id, "assignee": dec["assignee"],
                "title": form.get("text_en") or form.get("equipment") or "Inspect reported defect",
                "priority": form.get("priority")},
                report_id=rid, actor="system:auto_approve", event_id=det_id(rid, "task.assigned", task_id))
        return True

    async def _step_ask(self, st: dict) -> bool:
        c = (st["decision"] or {}).get("clarification") or {}
        rnd = len(st["clarifications"]) + 1
        self.store.append("report.clarification_requested", {
            "question": c.get("question"), "question_en": c.get("question_en"), "lang": c.get("lang"),
            "field": c.get("field"), "to": st.get("crew_id"), "round": rnd,
        }, report_id=st["report_id"], actor="system:rules",
            event_id=det_id(st["report_id"], "clarification_requested", rnd))
        return False  # czekamy na człowieka

    async def _step_transcribe_clarification(self, st: dict) -> bool:
        idx = len(st["clarifications"]) - 1
        c = st["clarifications"][idx]
        r = await self._call(st, "stt", self.plugins.transcribe, self._audio_path(c["answer_audio"]["file"]),
                             c.get("lang"))
        if r is None:
            return False
        try:
            data = _validated(TranscriptResult, r[0])
        except Exception as e:
            return self._bad_output(st, "stt", e)
        self.store.append("report.transcribed", {"kind": "clarification", "clarification_index": idx,
                                                 **data, "ms": r[1]},
                          report_id=st["report_id"], actor="system:stt",
                          event_id=det_id(st["report_id"], "transcribed", "clar", idx))
        return True

    async def _step_apply_clarification(self, st: dict) -> bool:
        idx = len(st["clarifications"]) - 1
        c = st["clarifications"][idx]
        clar = {k: c.get(k) for k in ("question", "question_en", "lang", "field", "round")}
        r = await self._call(st, "brain.apply_clarification", self.plugins.apply_clarification,
                             st["form"] or {}, clar, c.get("answer_text") or "", c.get("answer_lang") or "und",
                             self._ctx(st, idx + 1))
        if r is None:
            return False
        try:
            form = _validated(ReportForm, r[0])
        except Exception as e:
            return self._bad_output(st, "brain.apply_clarification", e)
        self.store.append("report.structured", {"form": form, "round": idx + 1, "ms": r[1]},
                          report_id=st["report_id"], actor="system:llm",
                          event_id=det_id(st["report_id"], "structured", idx + 1))
        return True

    def _bad_output(self, st: dict, stage: str, e: Exception) -> bool:
        self.store.append("report.failed", {"stage": stage, "error": f"invalid plugin output: {e}"[:500]},
                          report_id=st["report_id"], actor=f"system:{stage}",
                          event_id=det_id(st["report_id"], "failed", stage, len(st["failures"])))
        return False
