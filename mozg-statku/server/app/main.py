"""Serwer pokładowy „Mózg statku” — składanie aplikacji i endpointy HTTP.

Uruchomienie: `python -m app` (jeden proces! hub, pipeline i kolejka żyją w pamięci procesu).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import ClientDisconnect, Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .config import Settings
from .contracts import ApproveIn, LinkIn, TaskActionIn, TextReportIn
from .eventstore import EventStore
from .hub import Hub
from .notify import Notifier
from .outbox import ShoreLink
from .pipeline import Pipeline
from .plugin_loader import load_plugins
from .projection import project
from .sensors import SensorCache
from .service import ApiError, Service, check_uuid, load_json



class Ship:
    """Wszystkie komponenty w jednym miejscu (łatwo podmienić w testach)."""

    def __init__(self, settings: Settings):
        settings.ensure_dirs()
        self.s = settings
        self.store = EventStore(settings.db_path)
        self.hub = Hub()
        self.sensors = SensorCache()
        crew_list = load_json(settings.config_dir / "crew.json", [])
        self.crew = {c["crew_id"]: c for c in crew_list}
        self.equipment = load_json(settings.config_dir / "equipment.json", {"groups": {}, "equipment": []})
        self.plugins = load_plugins(settings.force_stubs)
        self.pipeline = Pipeline(self.store, self.sensors, self.plugins, settings, self.crew, self.equipment)
        self.service = Service(self.store, self.pipeline, self.plugins, settings, self.crew, self.equipment)
        self.link = ShoreLink(self.store, self.hub, settings)
        self.store.add_listener(Notifier(self.store, self.hub, settings.ship_id))
        self.store.add_listener(self.link.on_event)
        self.hub.on(f"ship/{settings.ship_id}/sensors/+",
                    lambda topic, msg: self.sensors.update(topic.rsplit("/", 1)[-1], msg))

    async def start(self) -> None:
        if self.s.mqtt_enabled:
            self.hub.start_mqtt(self.s.mqtt_host, self.s.mqtt_port, f"ship-server-{self.s.ship_id}",
                                [f"ship/{self.s.ship_id}/sensors/+"])
        self.pipeline.start()
        self.link.start()
        self.pipeline.recover()
        self.link.publish_status()
        print(f"[ship] gotowy: statek={self.s.ship_id} zdarzeń={self.store.count()} pluginy={self.plugins.sources}")

    async def stop(self) -> None:
        await self.pipeline.stop()
        await self.link.stop()
        self.hub.close()
        self.store.close()


# ====================================================================== helpers
def ok(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def err(status: int, msg: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": msg, **extra}, status_code=status)


async def body_json(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise ApiError(400, "invalid JSON body")
    if not isinstance(data, dict):
        raise ApiError(400, "JSON object expected")
    return data


def model(cls, data: dict):
    try:
        return cls.model_validate(data)
    except ValidationError as e:
        raise ApiError(422, "validation error", details=json.loads(e.json()))


def ship(request: Request) -> Ship:
    return request.app.state.ship


async def _form_audio(form) -> tuple[Any, str | None]:
    f = form.get("audio") or form.get("file")
    if f is None or isinstance(f, str):
        return None, None
    return f, (f.content_type or "audio/webm")


def _s(form, key: str) -> str | None:
    v = form.get(key)
    return v if isinstance(v, str) and v != "" else None


# ====================================================================== endpoints
async def health(request: Request):
    sh = ship(request)
    return ok({"ok": True, "ship_id": sh.s.ship_id, "events": sh.store.count(), "hub": sh.hub.status(),
               "plugins": sh.plugins.sources, "pipeline_inflight": list(sh.pipeline.inflight),
               "sat_link": sh.link.link_up})


async def post_audio(request: Request):
    """POST /api/reports/audio (multipart): audio, report_id, crew_id, [event_id, device, lang_hint,
    recorded_at, sha256, transcript_hint]. Ponowna wysyłka tego samego report_id => 200 + duplicate:true."""
    sh = ship(request)
    async with request.form(max_files=2, max_fields=20) as form:
        f, mime = await _form_audio(form)
        if f is None:
            raise ApiError(400, "multipart field 'audio' is required")
        crew_id = _s(form, "crew_id")
        if not crew_id:
            raise ApiError(400, "crew_id is required")
        res, created = await run_in_threadpool(
            lambda: sh.service.ingest_audio(
                report_id=_s(form, "report_id"), crew_id=crew_id, src=f.file, mime=mime,
                device=_s(form, "device"), lang_hint=_s(form, "lang_hint"), recorded_at=_s(form, "recorded_at"),
                event_id=_s(form, "event_id"), sha256=_s(form, "sha256"),
                transcript_hint=_s(form, "transcript_hint")))
    return ok(res, 201 if created else 200)


async def post_text(request: Request):
    sh = ship(request)
    body = model(TextReportIn, await body_json(request))
    res, created = await run_in_threadpool(sh.service.ingest_text, body)
    return ok(res, 201 if created else 200)


async def list_reports(request: Request):
    q = request.query_params
    sh = ship(request)
    return ok(await run_in_threadpool(sh.service.list_reports, q.get("status"), q.get("crew_id"), q.get("role")))


async def get_report(request: Request):
    sh = ship(request)
    rid = check_uuid(request.path_params["rid"], "report_id")
    events = sh.store.for_report(rid)
    if not events:
        raise ApiError(404, "unknown report")
    st = project(events)
    st["timeline"] = [{k: e[k] for k in ("seq", "event_id", "ts", "type", "actor", "device", "payload",
                                          "synced_at", "hash")} for e in events]
    return ok(st)


async def get_audio(request: Request):
    sh = ship(request)
    rid = check_uuid(request.path_params["rid"], "report_id")
    st = sh.service.state(rid)
    which = request.query_params.get("clar")
    meta = None
    if st and which is None:
        meta = st.get("audio")
    elif st and which is not None:
        try:
            meta = st["clarifications"][int(which)].get("answer_audio")
        except (IndexError, ValueError):
            meta = None
    if not meta:
        raise ApiError(404, "no audio")
    return FileResponse(sh.s.audio_dir / meta["file"], media_type=meta.get("mime") or "application/octet-stream",
                        content_disposition_type="inline")


async def post_clarify(request: Request):
    """Odpowiedź na pytanie zwrotne: JSON {text, crew_id, event_id, lang} albo multipart z 'audio'."""
    sh = ship(request)
    rid = request.path_params["rid"]
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/") or ctype.startswith("application/x-www-form-urlencoded"):
        async with request.form(max_files=2, max_fields=20) as form:
            f, mime = await _form_audio(form)
            res, created = await run_in_threadpool(lambda: sh.service.clarify(
                rid, crew_id=_s(form, "crew_id"), event_id=_s(form, "event_id"), text=_s(form, "text"),
                lang=_s(form, "lang"), audio=f.file if f else None, mime=mime, sha256=_s(form, "sha256"),
                transcript_hint=_s(form, "transcript_hint"), device=_s(form, "device")))
    else:
        b = await body_json(request)
        res, created = await run_in_threadpool(lambda: sh.service.clarify(
            rid, crew_id=b.get("crew_id"), event_id=b.get("event_id"), text=b.get("text"), lang=b.get("lang"),
            audio=None, mime=None, sha256=None, transcript_hint=None, device=b.get("device")))
    return ok(res, 201 if created else 200)


async def post_approve(request: Request):
    sh = ship(request)
    body = model(ApproveIn, await body_json(request))
    res, created = await run_in_threadpool(sh.service.approve, request.path_params["rid"], body)
    return ok(res, 201 if created else 200)


async def post_retry(request: Request):
    sh = ship(request)
    actor = request.query_params.get("crew_id")
    return ok(await run_in_threadpool(sh.service.retry, request.path_params["rid"], actor))


async def list_tasks(request: Request):
    q = request.query_params
    return ok(await run_in_threadpool(ship(request).service.list_tasks, q.get("assignee"), q.get("status")))


async def task_ack(request: Request):
    body = model(TaskActionIn, await body_json(request))
    res, created = await run_in_threadpool(ship(request).service.task_action, request.path_params["tid"], "ack", body)
    return ok(res, 201 if created else 200)


async def task_close(request: Request):
    body = model(TaskActionIn, await body_json(request))
    res, created = await run_in_threadpool(ship(request).service.task_action, request.path_params["tid"], "close", body)
    return ok(res, 201 if created else 200)


async def get_events(request: Request):
    q = request.query_params
    sh = ship(request)
    evs = sh.store.events(since_seq=int(q.get("since_seq", 0)), limit=min(int(q.get("limit", 500)), 5000),
                          report_id=q.get("report_id"))
    return ok(evs)


async def audit_verify(request: Request):
    return ok(await run_in_threadpool(ship(request).store.verify_chain))


async def sync_status(request: Request):
    return ok(await run_in_threadpool(ship(request).link.status))


async def sync_link(request: Request):
    body = model(LinkIn, await body_json(request))
    return ok(await run_in_threadpool(ship(request).link.set_link, body.up, body.actor))


async def sync_flush(request: Request):
    sh = ship(request)
    if not sh.link.link_up:
        raise ApiError(409, "satellite link is OFF")
    try:
        n = await run_in_threadpool(sh.link.flush_once)
    except Exception as e:
        raise ApiError(502, f"shore unreachable: {e!r}")
    return ok({"sent": n, **sh.link.status()})


async def get_sensors(request: Request):
    return ok(ship(request).sensors.all())


async def post_sensors(request: Request):
    """Fallback HTTP dla symulatora: {"tag": "...", "value": 1.9, "unit": "bar"} albo lista takich."""
    sh = ship(request)
    data = await request.json()
    items = data if isinstance(data, list) else [data]
    for it in items:
        if isinstance(it, dict) and it.get("tag"):
            sh.sensors.update(it["tag"], it)
            sh.hub.publish(f"ship/{sh.s.ship_id}/sensors/{it['tag']}", it)
    return ok({"accepted": len(items)})


async def get_crew(request: Request):
    return ok(list(ship(request).crew.values()))


async def get_equipment(request: Request):
    return ok(ship(request).equipment)


async def stream(request: Request):
    """SSE fallback dla MQTT: /api/stream?topics=person/marek,role/chief_engineer/approve&since_seq=120
    Każda wiadomość: event: message / data: {"topic": "...", "payload": {...}}.
    since_seq => najpierw powtórka zdarzeń z rejestru (nic nie ginie po zerwaniu połączenia)."""
    sh = ship(request)
    sid = sh.s.ship_id
    topics = [t for t in (request.query_params.get("topics") or f"ship/{sid}/#").split(",") if t]
    since = request.query_params.get("since_seq") or request.headers.get("last-event-id")
    sub = sh.hub.subscribe(topics)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            if since is not None and any(t in (f"ship/{sid}/events", f"ship/{sid}/#", "#") for t in topics):
                for e in sh.store.events(since_seq=int(since), limit=5000):
                    yield (f"id: {e['seq']}\nevent: message\ndata: "
                           f"{json.dumps({'topic': f'ship/{sid}/events', 'payload': e}, ensure_ascii=False)}\n\n")
            while True:
                if await request.is_disconnected():
                    break
                try:
                    topic, payload = await asyncio.wait_for(sub.queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                sid_line = f"id: {payload['seq']}\n" if topic.endswith("/events") and "seq" in payload else ""
                yield (f"{sid_line}event: message\ndata: "
                       f"{json.dumps({'topic': topic, 'payload': payload}, ensure_ascii=False)}\n\n")
        finally:
            sh.hub.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def api_error(request: Request, exc: ApiError):
    return err(exc.status, exc.msg, **exc.extra)


async def client_gone(request: Request, exc: ClientDisconnect):
    # telefon stracił zasięg w trakcie wysyłki: nic nie zapisaliśmy, telefon ponowi z tym samym UUID
    print(f"[api] klient rozłączył się w trakcie {request.method} {request.url.path} — nic nie zapisano")
    return Response(status_code=499)


# ====================================================================== app
def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_env()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        sh = Ship(settings)
        app.state.ship = sh
        await sh.start()
        try:
            yield
        finally:
            await sh.stop()

    R = Route
    routes = [
        R("/api/health", health),
        R("/api/reports/audio", post_audio, methods=["POST"]),
        R("/api/reports/text", post_text, methods=["POST"]),
        R("/api/reports", list_reports),
        R("/api/reports/{rid}", get_report),
        R("/api/reports/{rid}/audio", get_audio),
        R("/api/reports/{rid}/clarify", post_clarify, methods=["POST"]),
        R("/api/reports/{rid}/approve", post_approve, methods=["POST"]),
        R("/api/reports/{rid}/retry", post_retry, methods=["POST"]),
        R("/api/tasks", list_tasks),
        R("/api/tasks/{tid}/ack", task_ack, methods=["POST"]),
        R("/api/tasks/{tid}/close", task_close, methods=["POST"]),
        R("/api/events", get_events),
        R("/api/audit/verify", audit_verify),
        R("/api/sync/status", sync_status),
        R("/api/sync/link", sync_link, methods=["POST"]),
        R("/api/sync/flush", sync_flush, methods=["POST"]),
        R("/api/sensors", get_sensors, methods=["GET"]),
        R("/api/sensors", post_sensors, methods=["POST"]),
        R("/api/crew", get_crew),
        R("/api/equipment", get_equipment),
        R("/api/stream", stream),
    ]
    return Starlette(
        routes=routes,
        lifespan=lifespan,
        exception_handlers={ApiError: api_error, ClientDisconnect: client_gone},
        middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
        max_body_size=(settings.max_upload_mb + 2) * 1024 * 1024,
    )
