"""Operacje biznesowe (wołane przez API). Każda jest idempotentna:
ponowienie tego samego żądania zwraca ten sam wynik i NIE tworzy nowych zdarzeń."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone  # noqa: F401
from pathlib import Path
from typing import Any, BinaryIO

from .config import Settings
from .contracts import ApproveIn, TaskActionIn, TextReportIn
from .eventstore import EventStore, det_id, utcnow
from .pipeline import Pipeline
from .plugin_loader import Plugins
from .projection import OPEN_STATUSES, project, summary

MIME_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/aac": "aac",
            "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
            "video/webm": "webm", "audio/x-m4a": "m4a"}
FINAL = {"approved", "rejected", "assigned", "in_progress", "closed"}


class ApiError(Exception):
    def __init__(self, status: int, msg: str, **extra: Any):
        super().__init__(msg)
        self.status, self.msg, self.extra = status, msg, extra


def check_uuid(v: str | None, name: str) -> str:
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, TypeError):
        raise ApiError(400, f"{name} must be a UUID (generated on the device)")


def sane_ts(device_ts: str | None) -> str:
    """Czas z urządzenia (nagranie w martwej strefie o 10:00, wysłane o 10:07) — jeśli wiarygodny."""
    if not device_ts:
        return utcnow()
    try:
        dt = datetime.fromisoformat(device_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if dt > now + timedelta(minutes=5) or dt < now - timedelta(days=7):
            return utcnow()
        return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except ValueError:
        return utcnow()


class Service:
    def __init__(self, store: EventStore, pipeline: Pipeline, plugins: Plugins, settings: Settings,
                 crew: dict[str, dict], equipment: dict):
        self.store, self.pipeline, self.plugins, self.s = store, pipeline, plugins, settings
        self.crew, self.equipment = crew, equipment

    def actor(self, crew_id: str | None) -> str | None:
        if not crew_id:
            return None
        role = self.crew.get(crew_id, {}).get("role", "crew")
        return f"{role}:{crew_id}"

    def state(self, rid: str) -> dict | None:
        return project(self.store.for_report(rid))

    # ------------------------------------------------------------ audio na dysk
    def _save_audio(self, src: BinaryIO, rid: str, name: str, mime: str, expect_sha: str | None) -> dict:
        ext = MIME_EXT.get((mime or "").split(";")[0].strip().lower(), "bin")
        folder = self.s.audio_dir / rid
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".{name}.{uuid.uuid4().hex}.part"
        h, size, limit = hashlib.sha256(), 0, self.s.max_upload_mb * 1024 * 1024
        try:
            with open(tmp, "wb") as f:
                while chunk := src.read(256 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ApiError(413, f"audio larger than {self.s.max_upload_mb} MB")
                    h.update(chunk)
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
            if size == 0:
                raise ApiError(400, "empty audio file")
            sha = h.hexdigest()
            if expect_sha and expect_sha.lower() != sha:
                raise ApiError(400, "sha256 mismatch — upload corrupted, retry", sha256=sha)
            return {"tmp": tmp, "rel": f"{rid}/{name}.{ext}", "sha256": sha, "bytes": size, "mime": mime}
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _commit_audio(self, info: dict) -> dict:
        final = self.s.audio_dir / info["rel"]
        os.replace(info["tmp"], final)  # atomowo: plik jest albo cały, albo go nie ma
        return {"file": info["rel"], "sha256": info["sha256"], "bytes": info["bytes"], "mime": info["mime"]}

    @staticmethod
    def _hint(rel_audio: str, audio_dir: Path, hint: str | None) -> None:
        if hint:
            (audio_dir / (rel_audio + ".hint.txt")).write_text(hint, encoding="utf-8")

    # ------------------------------------------------------------ zgłoszenia
    def ingest_audio(self, *, report_id: str, crew_id: str, src: BinaryIO, mime: str, device: str | None,
                     lang_hint: str | None, recorded_at: str | None, event_id: str | None,
                     sha256: str | None, transcript_hint: str | None) -> tuple[dict, bool]:
        rid = check_uuid(report_id, "report_id")
        if event_id:
            event_id = check_uuid(event_id, "event_id")
        if self.store.has_type(rid, "report.recorded"):
            # ponowienie: porównaj treść (sha z telefonu albo policz z przesłanych bajtów), nic nie zapisuj
            if not sha256:
                h = hashlib.sha256()
                while chunk := src.read(256 * 1024):
                    h.update(chunk)
                sha256 = h.hexdigest()
            return self._recorded_dup(rid, sha256), False
        info = self._save_audio(src, rid, "main", mime, sha256)  # zapis poza blokadą (może trwać)
        with self.store.lock:
            dup = self._recorded_dup(rid, info["sha256"])
            if dup:  # równoległy duplikat wygrał wyścig
                info["tmp"].unlink(missing_ok=True)
                return dup, False
            audio = self._commit_audio(info)
            self._hint(audio["file"], self.s.audio_dir, transcript_hint)
            lang_hint = lang_hint or self.crew.get(crew_id, {}).get("lang")
            ev, created = self.store.append(
                "report.recorded",
                {"crew_id": crew_id, "audio": audio, "lang_hint": lang_hint,
                 "device_recorded_at": recorded_at, "received_at": utcnow()},
                report_id=rid, actor=self.actor(crew_id), device=device,
                event_id=event_id or det_id(rid, "recorded"), ts=sane_ts(recorded_at))
            if not created and ev["report_id"] != rid:
                raise ApiError(409, "event_id already used by another report")
        self.pipeline.kick(rid)
        return {"report_id": rid, "status": "recorded", "duplicate": False, "event_id": ev["event_id"]}, True

    def _recorded_dup(self, rid: str, sha: str | None) -> dict | None:
        evs = [e for e in self.store.for_report(rid) if e["type"] == "report.recorded"]
        if not evs:
            return None
        old = (evs[0]["payload"].get("audio") or {}).get("sha256")
        if sha and old and sha.lower() != old:
            raise ApiError(409, "report_id already exists with different audio", report_id=rid)
        st = self.state(rid)
        return {"report_id": rid, "status": st["status"], "duplicate": True, "event_id": evs[0]["event_id"]}

    def ingest_text(self, body: TextReportIn) -> tuple[dict, bool]:
        """Plan B / terminal w ECR: zgłoszenie wpisane tekstem (pomija STT)."""
        rid = check_uuid(body.report_id, "report_id")
        with self.store.lock:
            dup = self._recorded_dup(rid, None)
            if dup:
                return dup, False
            lang = body.lang or self.crew.get(body.crew_id, {}).get("lang") or "und"
            ts = sane_ts(body.recorded_at)
            self.store.append("report.recorded", {"crew_id": body.crew_id, "audio": None, "text_input": True,
                                                  "lang_hint": lang, "device_recorded_at": body.recorded_at,
                                                  "received_at": utcnow()},
                              report_id=rid, actor=self.actor(body.crew_id), device=body.device,
                              event_id=body.event_id or det_id(rid, "recorded"), ts=ts)
            self.store.append("report.transcribed", {"kind": "report", "text": body.text, "lang": lang,
                                                     "model": "text-input"},
                              report_id=rid, actor=self.actor(body.crew_id), device=body.device,
                              event_id=det_id(rid, "transcribed", "main"))
        self.pipeline.kick(rid)
        return {"report_id": rid, "status": "transcribed", "duplicate": False}, True

    def clarify(self, rid: str, *, crew_id: str | None, event_id: str | None, text: str | None,
                lang: str | None, audio: BinaryIO | None, mime: str | None, sha256: str | None,
                transcript_hint: str | None, device: str | None) -> tuple[dict, bool]:
        rid = check_uuid(rid, "report_id")
        if event_id:
            event_id = check_uuid(event_id, "event_id")
            if self.store.get(event_id):
                st = self.state(rid)
                return {"report_id": rid, "status": st["status"] if st else None, "duplicate": True}, False
        st = self.state(rid)
        if not st:
            raise ApiError(404, "unknown report")
        if st["status"] != "awaiting_clarification":
            if st["clarifications"] and st["clarifications"][-1]["answered_ts"]:
                return {"report_id": rid, "status": st["status"], "duplicate": True}, False
            raise ApiError(409, f"report is '{st['status']}', not awaiting clarification")
        if not text and audio is None:
            raise ApiError(400, "send 'text' or 'audio'")
        idx = len(st["clarifications"]) - 1
        info = self._save_audio(audio, rid, f"clar-{idx + 1}", mime or "audio/webm", sha256) if audio else None
        with self.store.lock:
            st = self.state(rid)
            if st["status"] != "awaiting_clarification":
                if info:
                    info["tmp"].unlink(missing_ok=True)
                return {"report_id": rid, "status": st["status"], "duplicate": True}, False
            meta = self._commit_audio(info) if info else None
            if meta:
                self._hint(meta["file"], self.s.audio_dir, transcript_hint)
            crew_id = crew_id or st["crew_id"]
            self.store.append("report.clarified", {
                "text": text if not meta else None, "lang": lang or self.crew.get(crew_id or "", {}).get("lang"),
                "audio": meta, "crew_id": crew_id, "client_event_id": event_id},
                report_id=rid, actor=self.actor(crew_id), device=device,
                event_id=event_id or det_id(rid, "clarified", idx))
        self.pipeline.kick(rid)
        return {"report_id": rid, "status": "clarified", "duplicate": False}, True

    def retry(self, rid: str, actor_id: str | None) -> dict:
        st = self.state(check_uuid(rid, "report_id"))
        if not st:
            raise ApiError(404, "unknown report")
        if st["status"] != "failed":
            raise ApiError(409, f"report is '{st['status']}', not failed")
        self.store.append("report.retry", {}, report_id=st["report_id"], actor=self.actor(actor_id) or "operator")
        self.pipeline.kick(st["report_id"])
        return summary(self.state(st["report_id"]))

    # ------------------------------------------------------------ oficer
    def approve(self, rid: str, body: ApproveIn) -> tuple[dict, bool]:
        rid = check_uuid(rid, "report_id")
        if body.event_id:
            body.event_id = check_uuid(body.event_id, "event_id")
        with self.store.lock:
            st = self.state(rid)
            if not st:
                raise ApiError(404, "unknown report")
            if body.event_id and self.store.get(body.event_id):
                return summary(st) | {"duplicate": True}, False
            if st["status"] in FINAL:
                prev = (st.get("approval") or {}).get("decision")
                if prev == body.decision:
                    return summary(st) | {"duplicate": True}, False
                raise ApiError(409, f"report already {st['status']}")
            if st["status"] in ("recorded", "transcribed") and not body.form_patch:
                raise ApiError(409, "report not analysed yet — wait, or send form_patch")
            actor = self.actor(body.officer_id)
            form = {**(st.get("form") or {}), **body.form_patch}
            typ = "report.approved" if body.decision == "approve" else "report.rejected"
            self.store.append(typ, {"note": body.note, "assignee": body.assignee, "form_patch": body.form_patch,
                                    "form": form if body.form_patch else None, "client_event_id": body.event_id},
                              report_id=rid, actor=actor, event_id=body.event_id or det_id(rid, "decision"))
            if body.decision == "approve" and body.assignee:
                task_id = det_id(rid, "task", 1)
                self.store.append("task.assigned", {
                    "task_id": task_id, "assignee": body.assignee,
                    "title": form.get("text_en") or form.get("equipment") or "Inspect reported defect",
                    "priority": form.get("priority") or st.get("priority")},
                    report_id=rid, actor=actor, event_id=det_id(rid, "task.assigned", task_id))
            return summary(self.state(rid)) | {"duplicate": False}, True

    def _task_report(self, task_id: str) -> dict:
        with self.store.lock:
            row = self.store._conn.execute(
                "SELECT report_id FROM events WHERE type='task.assigned' AND json_extract(payload,'$.task_id')=? "
                "LIMIT 1", (task_id,)).fetchone()
        if not row:
            raise ApiError(404, "unknown task")
        return self.state(row[0])

    def task_action(self, task_id: str, action: str, body: TaskActionIn) -> tuple[dict, bool]:
        task_id = check_uuid(task_id, "task_id")
        typ, done = {"ack": ("task.acknowledged", {"acknowledged", "closed"}),
                     "close": ("task.closed", {"closed"})}[action]
        with self.store.lock:
            st = self._task_report(task_id)
            task = next(t for t in st["tasks"] if t["task_id"] == task_id)
            if task["status"] in done or (body.event_id and self.store.get(body.event_id)):
                return task | {"duplicate": True}, False
            self.store.append(typ, {"task_id": task_id, "note": body.note, "client_event_id": body.event_id},
                              report_id=st["report_id"], actor=self.actor(body.crew_id),
                              event_id=body.event_id or det_id(task_id, action))
            st = self.state(st["report_id"])
            return next(t for t in st["tasks"] if t["task_id"] == task_id) | {"duplicate": False}, True

    # ------------------------------------------------------------ odczyty
    def all_states(self) -> list[dict]:
        return [s for s in (self.state(r) for r in self.store.report_ids()) if s]

    def list_reports(self, status: str | None = None, crew_id: str | None = None,
                     role: str | None = None) -> list[dict]:
        wanted = set(status.split(",")) if status else None
        out = []
        for st in self.all_states():
            if wanted and st["status"] not in wanted and not ("open" in wanted and st["status"] in OPEN_STATUSES):
                continue
            if crew_id and st["crew_id"] != crew_id:
                continue
            if role and st["route_role"] != role:
                continue
            out.append(summary(st))
        return sorted(out, key=lambda r: r["created_ts"] or "", reverse=True)

    def list_tasks(self, assignee: str | None = None, status: str | None = None) -> list[dict]:
        out = []
        for st in self.all_states():
            for t in st["tasks"]:
                if assignee and t.get("assignee") != assignee:
                    continue
                if status and t.get("status") not in status.split(","):
                    continue
                out.append(t | {"report_status": st["status"], "equipment": (st.get("form") or {}).get("equipment")})
        return out


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
