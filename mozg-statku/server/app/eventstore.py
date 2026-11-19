"""Rejestr zdarzeń — jedyne źródło prawdy (Single Source of Truth).

Gwarancje:
  * tylko dopisywanie: triggery SQLite blokują DELETE i każdy UPDATE poza jednorazowym
    ustawieniem `synced_at` (kiedy zdarzenie poszło na ląd),
  * idempotencja: `event_id` jest UNIQUE; ponowne dopisanie tego samego `event_id`
    zwraca istniejące zdarzenie i `created=False` (nic się nie dubluje),
  * łańcuch skrótów (hash chain): każde zdarzenie zawiera sha256(prev_hash + treść),
    więc każda zmiana historii „po cichu” jest wykrywalna (`verify_chain`) — pod audyt ISM,
  * trwałość: SQLite WAL + synchronous=FULL — po odpowiedzi 2xx zdarzenie jest na dysku.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

GENESIS = "0" * 64
NS = uuid.UUID("6f1c3a52-6d0e-4c8b-9a41-5a1f0b7e2c11")  # przestrzeń nazw dla deterministycznych ID

# Zdarzenia lokalne — nie idą na ląd (dotyczą samej synchronizacji).
LOCAL_ONLY_PREFIX = "sync."

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL UNIQUE,
    ts          TEXT NOT NULL,           -- czas zdarzenia (ISO 8601 UTC)
    report_id   TEXT,                    -- wiąże zdarzenia jednego zgłoszenia
    type        TEXT NOT NULL,
    actor       TEXT,                    -- np. 2nd_engineer:mateusz
    device      TEXT,
    payload     TEXT NOT NULL,           -- JSON
    received_at TEXT NOT NULL,           -- kiedy serwer to zapisał
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL,
    synced_at   TEXT                     -- kiedy poszło na ląd (ustawiane raz)
);
CREATE INDEX IF NOT EXISTS ix_events_report ON events(report_id, seq);
CREATE INDEX IF NOT EXISTS ix_events_type ON events(type);
CREATE INDEX IF NOT EXISTS ix_events_unsynced ON events(seq) WHERE synced_at IS NULL;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only: DELETE forbidden');
END;

CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
WHEN NEW.seq IS NOT OLD.seq
  OR NEW.event_id IS NOT OLD.event_id
  OR NEW.ts IS NOT OLD.ts
  OR NEW.report_id IS NOT OLD.report_id
  OR NEW.type IS NOT OLD.type
  OR NEW.actor IS NOT OLD.actor
  OR NEW.device IS NOT OLD.device
  OR NEW.payload IS NOT OLD.payload
  OR NEW.received_at IS NOT OLD.received_at
  OR NEW.prev_hash IS NOT OLD.prev_hash
  OR NEW.hash IS NOT OLD.hash
  OR (OLD.synced_at IS NOT NULL AND NEW.synced_at IS NOT OLD.synced_at)
BEGIN
    SELECT RAISE(ABORT, 'events are append-only: only synced_at may be set, once');
END;

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

COLUMNS = ("seq", "event_id", "ts", "report_id", "type", "actor", "device",
           "payload", "received_at", "prev_hash", "hash", "synced_at")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def det_id(*parts: Any) -> str:
    """Deterministyczny UUID z części — ten sam krok przetwarzania zawsze ma ten sam event_id."""
    return str(uuid.uuid5(NS, "|".join(str(p) for p in parts)))


def canonical(ev: dict) -> str:
    body = {k: ev.get(k) for k in ("event_id", "ts", "report_id", "type", "actor", "device", "payload")}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, ev: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(ev)).encode("utf-8")).hexdigest()


def _row_to_event(row: sqlite3.Row | tuple) -> dict:
    ev = dict(zip(COLUMNS, row))
    ev["payload"] = json.loads(ev["payload"])
    return ev


Listener = Callable[[dict], None]


class EventStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.executescript(SCHEMA)
        self.lock = threading.RLock()  # jedna ścieżka zapisu => brak wyścigów na łańcuchu skrótów
        self._listeners: list[Listener] = []

    # ------------------------------------------------------------------ zapis
    def add_listener(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def append(
        self,
        type: str,
        payload: dict | None = None,
        *,
        report_id: str | None = None,
        actor: str | None = None,
        device: str | None = None,
        event_id: str | None = None,
        ts: str | None = None,
    ) -> tuple[dict, bool]:
        """Dopisz zdarzenie. Zwraca (zdarzenie, created). created=False => duplikat (nic nie zapisano)."""
        event_id = str(event_id or uuid.uuid4())
        with self.lock:
            existing = self.get(event_id)
            if existing is not None:
                return existing, False
            row = self._conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            prev_hash = row[0] if row else GENESIS
            ev = {
                "event_id": event_id,
                "ts": ts or utcnow(),
                "report_id": report_id,
                "type": type,
                "actor": actor,
                "device": device,
                "payload": payload or {},
                "received_at": utcnow(),
                "prev_hash": prev_hash,
            }
            ev["hash"] = compute_hash(prev_hash, ev)
            cur = self._conn.execute(
                "INSERT INTO events(event_id, ts, report_id, type, actor, device, payload,"
                " received_at, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ev["event_id"], ev["ts"], ev["report_id"], ev["type"], ev["actor"], ev["device"],
                 json.dumps(ev["payload"], ensure_ascii=False), ev["received_at"], prev_hash, ev["hash"]),
            )
            ev["seq"] = cur.lastrowid
            ev["synced_at"] = None
        for fn in list(self._listeners):
            try:
                fn(ev)
            except Exception as e:  # słuchacz nigdy nie psuje zapisu
                print(f"[eventstore] listener error: {e!r}")
        return ev, True

    def mark_synced(self, event_ids: Iterable[str], at: str | None = None) -> int:
        at = at or utcnow()
        ids = list(event_ids)
        if not ids:
            return 0
        with self.lock:
            n = 0
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                q = ",".join("?" * len(chunk))
                cur = self._conn.execute(
                    f"UPDATE events SET synced_at=? WHERE synced_at IS NULL AND event_id IN ({q})",
                    (at, *chunk))
                n += cur.rowcount
            return n

    # ------------------------------------------------------------------ odczyt
    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [_row_to_event(r) for r in rows]

    def get(self, event_id: str) -> dict | None:
        r = self._q(f"SELECT {','.join(COLUMNS)} FROM events WHERE event_id=?", (event_id,))
        return r[0] if r else None

    def for_report(self, report_id: str) -> list[dict]:
        return self._q(f"SELECT {','.join(COLUMNS)} FROM events WHERE report_id=? ORDER BY seq", (report_id,))

    def events(self, since_seq: int = 0, limit: int = 1000, report_id: str | None = None,
               since_ts: str | None = None) -> list[dict]:
        sql = f"SELECT {','.join(COLUMNS)} FROM events WHERE seq>?"
        args: list[Any] = [since_seq]
        if report_id:
            sql += " AND report_id=?"
            args.append(report_id)
        if since_ts:
            sql += " AND ts>=?"
            args.append(since_ts)
        sql += " ORDER BY seq LIMIT ?"
        args.append(limit)
        return self._q(sql, tuple(args))

    def report_ids(self) -> list[str]:
        with self.lock:
            rows = self._conn.execute(
                "SELECT report_id FROM events WHERE report_id IS NOT NULL "
                "GROUP BY report_id ORDER BY MIN(seq)").fetchall()
        return [r[0] for r in rows]

    def has_type(self, report_id: str, type: str) -> bool:
        with self.lock:
            return self._conn.execute(
                "SELECT 1 FROM events WHERE report_id=? AND type=? LIMIT 1", (report_id, type)
            ).fetchone() is not None

    def unsynced(self, limit: int = 50) -> list[dict]:
        return self._q(
            f"SELECT {','.join(COLUMNS)} FROM events WHERE synced_at IS NULL "
            f"AND type NOT LIKE '{LOCAL_ONLY_PREFIX}%' ORDER BY seq LIMIT ?", (limit,))

    def queue_stats(self) -> dict:
        with self.lock:
            n, size = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(payload)),0) FROM events "
                f"WHERE synced_at IS NULL AND type NOT LIKE '{LOCAL_ONLY_PREFIX}%'").fetchone()
        return {"queue_len": n, "queue_payload_bytes": size}

    def count(self) -> int:
        with self.lock:
            return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    # ------------------------------------------------------------------ audyt
    def verify_chain(self) -> dict:
        """Przelicz cały łańcuch skrótów. Wykrywa każdą modyfikację/usunięcie wiersza."""
        with self.lock:
            rows = self._conn.execute(f"SELECT {','.join(COLUMNS)} FROM events ORDER BY seq").fetchall()
        prev = GENESIS
        for r in rows:
            ev = _row_to_event(r)
            if ev["prev_hash"] != prev or compute_hash(prev, ev) != ev["hash"]:
                return {"ok": False, "checked": ev["seq"] - 1, "broken_at_seq": ev["seq"],
                        "event_id": ev["event_id"]}
            prev = ev["hash"]
        return {"ok": True, "checked": len(rows), "head": prev}

    # ------------------------------------------------------------------ kv (stan przełączników)
    def kv_get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            r = self._conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def kv_set(self, key: str, value: Any) -> None:
        with self.lock:
            self._conn.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               (key, json.dumps(value)))

    def close(self) -> None:
        with self.lock:
            self._conn.close()
