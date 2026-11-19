"""Atrapa serwera armatora na lądzie (DPA / system SMS).

POST /api/ingest   — paczka zdarzeń ze statku (JSON, opcjonalnie gzip). Idempotentny: deduplikacja po
                     event_id, więc ponowna wysyłka po zgubionym potwierdzeniu niczego nie dubluje.
GET  /api/stats, /api/reports, /api/events — co dotarło na ląd (pod wasz własny widok).
"""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

DATA = Path(os.getenv("DATA_DIR", "./data"))
TOKEN = os.getenv("SHORE_TOKEN", "demo-token")
DATA.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(str(DATA / "shore.db"), check_same_thread=False, isolation_level=None)
db.executescript("""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, ship_id TEXT, seq INTEGER, ts TEXT, report_id TEXT, type TEXT,
  actor TEXT, payload TEXT, hash TEXT, batch_id TEXT, received_at TEXT);
CREATE TABLE IF NOT EXISTS batches (
  batch_id TEXT PRIMARY KEY, ship_id TEXT, count INTEGER, new INTEGER, bytes_wire INTEGER, received_at TEXT);
""")
lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


async def ingest(request: Request):
    if request.headers.get("x-ship-token") != TOKEN:
        return JSONResponse({"error": "bad token"}, status_code=401)
    raw = await request.body()
    wire = len(raw)
    if request.headers.get("content-encoding") == "gzip":
        raw = gzip.decompress(raw)
    body = json.loads(raw)
    ship, batch, evs = body.get("ship_id"), body.get("batch_id"), body.get("events", [])
    acked, new = [], 0
    with lock:
        for e in evs:
            cur = db.execute(
                "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (e["event_id"], ship, e.get("seq"), e.get("ts"), e.get("report_id"), e.get("type"), e.get("actor"),
                 json.dumps(e.get("payload"), ensure_ascii=False), e.get("hash"), batch, now()))
            new += cur.rowcount
            acked.append(e["event_id"])
        db.execute("INSERT OR IGNORE INTO batches VALUES (?,?,?,?,?,?)", (batch, ship, len(evs), new, wire, now()))
    return JSONResponse({"acked": acked, "new": new, "duplicates": len(evs) - new})


async def stats(request: Request):
    with lock:
        n, reports = db.execute("SELECT COUNT(*), COUNT(DISTINCT report_id) FROM events").fetchone()
        b, wire, last = db.execute("SELECT COUNT(*), COALESCE(SUM(bytes_wire),0), MAX(received_at) FROM batches").fetchone()
        by_type = dict(db.execute("SELECT type, COUNT(*) FROM events GROUP BY type").fetchall())
    return JSONResponse({"events": n, "reports": reports, "batches": b, "bytes_wire_total": wire,
                         "last_batch_at": last, "by_type": by_type})


async def reports(request: Request):
    with lock:
        rows = db.execute("SELECT report_id, type, payload, ts, actor FROM events WHERE report_id IS NOT NULL "
                          "ORDER BY report_id, seq").fetchall()
    out: dict[str, dict] = {}
    for rid, typ, payload, ts, actor in rows:
        p = json.loads(payload or "{}")
        r = out.setdefault(rid, {"report_id": rid, "first_ts": ts, "events": 0})
        r["events"] += 1
        r["last_type"], r["last_ts"] = typ, ts
        if typ == "report.recorded":
            r["reported_by"] = actor
            r["audio"] = p.get("audio")
        if typ == "report.structured":
            f = p.get("form") or {}
            r.update({k: f.get(k) for k in ("equipment", "sfi_code", "priority", "text_en")})
        if typ == "report.approved":
            r["approved_by"] = actor
        if typ == "report.transcribed" and p.get("kind") != "clarification":
            r["original"] = p.get("text")
    return JSONResponse(sorted(out.values(), key=lambda r: r["first_ts"] or "", reverse=True))


async def events(request: Request):
    with lock:
        rows = db.execute("SELECT event_id, ship_id, ts, report_id, type, actor, received_at FROM events "
                          "ORDER BY received_at DESC, seq DESC LIMIT 50").fetchall()
    keys = ("event_id", "ship_id", "ts", "report_id", "type", "actor", "received_at")
    return JSONResponse([dict(zip(keys, r)) for r in rows])


async def health(request: Request):
    return JSONResponse({"ok": True})


app = Starlette(routes=[
    Route("/api/health", health), Route("/api/ingest", ingest, methods=["POST"]),
    Route("/api/stats", stats), Route("/api/reports", reports), Route("/api/events", events),
])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 9000)))
