"""Kolejka satelitarna na ląd — Store-and-Forward.

* Kolejką jest sam rejestr: wszystko z `synced_at IS NULL` (poza lokalnymi `sync.*`) czeka na łącze.
  Nie ma drugiej kopii danych, która mogłaby się rozjechać — zdarzenie trafia do kolejki
  w tej samej transakcji, w której powstaje (wzorzec transactional outbox).
* Dostawa „co najmniej raz” + idempotentny odbiorca na lądzie (deduplikacja po event_id)
  = w praktyce „dokładnie raz”. Gdy potwierdzenie zginie, wysyłamy ponownie — ląd zignoruje duplikat.
* Przez satelitę idzie WYŁĄCZNIE lekki JSON (gzip). Audio zostaje na statku; na ląd trafia
  tylko jego sha256 i rozmiar (do późniejszej weryfikacji integralności).
* Przełącznik „Satelita ON/OFF” jest trwały (tabela kv) i publikowany na ship/{id}/sync.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from .config import Settings
from .eventstore import EventStore, utcnow
from .hub import Hub

DROP_KEYS = {"file", "path", "audio_path", "debug_transcript_hint"}
MAX_STR = 4000
MAX_EVENT_BYTES = 16_000


def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items() if not str(k).startswith("_") and k not in DROP_KEYS}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None  # nigdy binarne przez satelitę
    if isinstance(v, str) and len(v) > MAX_STR:
        return v[:MAX_STR] + "…[truncated]"
    return v


def to_shore(ev: dict) -> dict:
    out = {k: ev[k] for k in ("event_id", "seq", "ts", "report_id", "type", "actor", "device", "hash")}
    out["payload"] = _clean(ev.get("payload") or {})
    if len(json.dumps(out, ensure_ascii=False).encode()) > MAX_EVENT_BYTES:
        out["payload"] = {"truncated": True, "keys": sorted((ev.get("payload") or {}).keys())}
    return out


class ShoreLink:
    def __init__(self, store: EventStore, hub: Hub, settings: Settings):
        self.store, self.hub, self.s = store, hub, settings
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self.last_error: str | None = None
        self.last_sync_at: str | None = None
        self.shore_reachable: bool | None = None
        if self.store.kv_get("sat_link") is None:
            self.store.kv_set("sat_link", bool(settings.sat_link_default))

    # ------------------------------------------------------------ stan
    @property
    def link_up(self) -> bool:
        return bool(self.store.kv_get("sat_link", True))

    def stats(self) -> dict:
        return self.store.kv_get("sync_stats", {"batches": 0, "events": 0, "bytes_json": 0, "bytes_wire": 0})

    def audio_bytes_aboard(self) -> int:
        d = self.s.audio_dir
        return sum(p.stat().st_size for p in d.rglob("*") if p.is_file() and not p.name.endswith(".hint.txt")) \
            if d.exists() else 0

    def status(self) -> dict:
        q = self.store.queue_stats()
        return {"link_up": self.link_up, **q, "sent": self.stats(), "last_sync_at": self.last_sync_at,
                "last_error": self.last_error, "shore_reachable": self.shore_reachable,
                "shore_url": self.s.shore_url, "audio_bytes_aboard": self.audio_bytes_aboard(),
                "sat_kbps": self.s.sat_kbps}

    def publish_status(self) -> None:
        self.hub.publish(f"ship/{self.s.ship_id}/sync", self.status(), retain=True)

    def set_link(self, up: bool, actor: str | None = None) -> dict:
        prev = self.link_up
        self.store.kv_set("sat_link", bool(up))
        if prev != up:
            self.store.append("sync.link_changed", {"up": bool(up)}, actor=actor or "demo:operator")
        self.publish_status()
        self.wake()
        return self.status()

    # ------------------------------------------------------------ pętla
    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="shore-link")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def wake(self) -> None:
        if self._loop and self._wake:
            self._loop.call_soon_threadsafe(self._wake.set)

    def on_event(self, ev: dict) -> None:
        """Słuchacz rejestru: nowe zdarzenie => licznik kolejki rośnie (na żywo w UI)."""
        if not ev["type"].startswith("sync."):
            self.publish_status()
            self.wake()

    async def _run(self) -> None:
        assert self._wake is not None
        backoff = self.s.sync_interval_s
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
            if not self.link_up:
                backoff = self.s.sync_interval_s
                continue
            try:
                while self.link_up and self.store.queue_stats()["queue_len"] > 0:
                    sent = await asyncio.to_thread(self.flush_once)
                    if sent == 0:
                        break
                backoff = self.s.sync_interval_s
            except Exception as e:
                self.last_error = repr(e)[:300]
                self.shore_reachable = False
                self.publish_status()
                backoff = min(30.0, backoff * 2)  # ląd nieosiągalny mimo „łącza” — wycofanie wykładnicze

    def flush_once(self) -> int:
        events = self.store.unsynced(self.s.sync_batch)
        if not events:
            return 0
        batch_id = str(uuid.uuid4())
        body = {"ship_id": self.s.ship_id, "batch_id": batch_id, "sent_at": utcnow(),
                "events": [to_shore(e) for e in events]}
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        wire = gzip.compress(raw)
        if self.s.sat_kbps > 0:  # symulacja wąskiego łącza
            time.sleep(len(wire) * 8 / (self.s.sat_kbps * 1000))
        if not self.link_up:  # łącze padło w trakcie
            return 0
        req = urllib.request.Request(
            f"{self.s.shore_url}/api/ingest", data=wire, method="POST",
            headers={"Content-Type": "application/json", "Content-Encoding": "gzip",
                     "X-Ship-Id": self.s.ship_id, "X-Ship-Token": self.s.shore_token})
        with urllib.request.urlopen(req, timeout=15) as resp:
            ack = json.loads(resp.read().decode("utf-8"))
        acked = set(ack.get("acked", []))
        n = self.store.mark_synced([e["event_id"] for e in events if e["event_id"] in acked])
        st = self.stats()
        st = {"batches": st["batches"] + 1, "events": st["events"] + n,
              "bytes_json": st["bytes_json"] + len(raw), "bytes_wire": st["bytes_wire"] + len(wire)}
        self.store.kv_set("sync_stats", st)
        self.store.append("sync.sent", {"batch_id": batch_id, "count": n, "bytes_json": len(raw),
                                        "bytes_wire": len(wire), "duplicates_on_shore": ack.get("duplicates", 0)},
                          actor="system:sync")
        self.last_sync_at, self.last_error, self.shore_reachable = utcnow(), None, True
        self.publish_status()
        return n
