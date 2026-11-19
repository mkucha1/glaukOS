"""Testy rdzenia: rejestr tylko-do-dopisywania, audyt, wznawianie po awarii, błędy pluginów, kolejka na ląd.
Uruchom: cd server && python -m pytest -q"""
from __future__ import annotations

import asyncio
import io
import sqlite3
import uuid

import pytest

from app.config import Settings
from app.contracts import ApproveIn, TextReportIn
from app.eventstore import EventStore
from app.main import Ship
from app.outbox import to_shore
from app.projection import project


def settings(tmp_path, **kw) -> Settings:
    s = Settings(data_dir=tmp_path, mqtt_enabled=False, shore_url="http://127.0.0.1:9", sat_link_default=False,
                 sync_interval_s=0.2)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


async def wait_for(fn, timeout=5.0):
    t = 0.0
    while t < timeout:
        r = fn()
        if r:
            return r
        await asyncio.sleep(0.05)
        t += 0.05
    return fn()


# ------------------------------------------------------------------ rejestr
def test_append_only_and_idempotent(tmp_path):
    st = EventStore(tmp_path / "e.db")
    ev, created = st.append("report.recorded", {"a": 1}, report_id="r1", event_id="e1")
    again, created2 = st.append("report.recorded", {"a": 999}, report_id="r1", event_id="e1")
    assert created and not created2 and again["payload"] == {"a": 1}
    assert st.count() == 1
    with pytest.raises(sqlite3.DatabaseError):
        st._conn.execute("UPDATE events SET payload='{}' WHERE event_id='e1'")
    with pytest.raises(sqlite3.DatabaseError):
        st._conn.execute("DELETE FROM events")
    assert st.mark_synced(["e1"]) == 1
    with pytest.raises(sqlite3.DatabaseError):  # synced_at tylko raz
        st._conn.execute("UPDATE events SET synced_at='x' WHERE event_id='e1'")


def test_hash_chain_detects_tampering(tmp_path):
    st = EventStore(tmp_path / "e.db")
    for i in range(5):
        st.append("report.recorded", {"i": i}, report_id=f"r{i}")
    assert st.verify_chain()["ok"]
    # „sprytny” administrator wyłącza trigger i poprawia historię
    st._conn.execute("DROP TRIGGER events_no_update")
    st._conn.execute("UPDATE events SET payload='{\"i\": 42}' WHERE seq=3")
    v = st.verify_chain()
    assert not v["ok"] and v["broken_at_seq"] == 3


def test_shore_payload_never_contains_audio_or_private_fields():
    ev = {"event_id": "e", "seq": 1, "ts": "t", "report_id": "r", "type": "report.structured", "actor": "a",
          "device": "d", "hash": "h",
          "payload": {"audio": {"file": "r/main.webm", "sha256": "abc", "bytes": 10},
                      "form": {"equipment": "x", "_equipment_id": "cw_pump_2"}, "blob": b"\x00\x01"}}
    out = to_shore(ev)
    assert out["payload"]["audio"] == {"sha256": "abc", "bytes": 10}
    assert out["payload"]["form"] == {"equipment": "x"}
    assert out["payload"]["blob"] is None


# ------------------------------------------------------------------ pipeline
def test_full_flow_and_crash_recovery(tmp_path):
    async def run():
        s = settings(tmp_path)
        # 1) „awaria”: serwer zapisał nagranie i padł przed transkrypcją
        sh = Ship(s)
        rid = str(uuid.uuid4())
        sh.service.ingest_audio(report_id=rid, crew_id="marek", src=io.BytesIO(b"x" * 1000), mime="audio/webm",
                                device="p1", lang_hint=None, recorded_at=None, event_id=None, sha256=None,
                                transcript_hint=None)  # pipeline nie wystartował => nic się nie przetworzyło
        assert project(sh.store.for_report(rid))["status"] == "recorded"
        sh.store.close()
        # 2) restart — recover() dokańcza
        sh = Ship(s)
        sh.sensors.update("CW_PUMP_2_P", {"value": 1.9, "unit": "bar"})
        await sh.start()
        st = await wait_for(lambda: (x := sh.service.state(rid)) and x["status"] == "awaiting_clarification" and x)
        assert st, sh.service.state(rid)
        sh.service.clarify(rid, crew_id="marek", event_id=None, text="dwa", lang="pl", audio=None, mime=None,
                           sha256=None, transcript_hint=None, device=None)
        st = await wait_for(lambda: (x := sh.service.state(rid)) and x["status"] == "pending_approval" and x)
        assert st["form"]["equipment"] == "Cooling water pump No. 2"
        assert st["decision"]["checks"][0]["ok"] is True
        # AI dla tego zgłoszenia wykonało się dokładnie raz na krok
        types = [e["type"] for e in sh.store.for_report(rid)]
        assert types.count("report.transcribed") == 1 and types.count("report.structured") == 2
        assert types.count("report.refined") == 1
        assert st["decision"]["needs_officer"] is True  # dopytywanie => mała pewność => oficer
        res, created = sh.service.approve(rid, ApproveIn(officer_id="anna", assignee="tom"))
        assert created and res["status"] == "assigned"
        await sh.stop()
    asyncio.run(run())


def test_plugin_failure_is_logged_and_retry_works(tmp_path):
    async def run():
        sh = Ship(settings(tmp_path, plugin_retries=1))
        calls = {"n": 0}
        good = sh.plugins.structure

        def broken(*a, **k):
            calls["n"] += 1
            raise RuntimeError("Ollama nie odpowiada")
        sh.plugins.structure = broken
        await sh.start()
        rid = str(uuid.uuid4())
        sh.service.ingest_text(TextReportIn(report_id=rid, crew_id="marek", text="Agregat numer jeden, wibracje."))
        st = await wait_for(lambda: (x := sh.service.state(rid)) and x["status"] == "failed" and x)
        assert st and calls["n"] == 2 and "Ollama" in st["failures"][0]["error"]
        sh.plugins.structure = good
        sh.service.retry(rid, "anna")
        st = await wait_for(lambda: (x := sh.service.state(rid)) and x["status"] == "pending_approval" and x)
        assert st and st["form"]["equipment"] == "Auxiliary engine No. 1"
        await sh.stop()
    asyncio.run(run())


def test_clarification_rounds_are_capped(tmp_path):
    async def run():
        sh = Ship(settings(tmp_path, max_clarify_rounds=1))
        await sh.start()
        rid = str(uuid.uuid4())
        sh.service.ingest_text(TextReportIn(report_id=rid, crew_id="marek", text="Pompa chłodzenia przecieka."))
        await wait_for(lambda: sh.service.state(rid)["status"] == "awaiting_clarification")
        sh.service.clarify(rid, crew_id=None, event_id=None, text="nie wiem", lang="pl", audio=None, mime=None,
                           sha256=None, transcript_hint=None, device=None)
        st = await wait_for(lambda: (x := sh.service.state(rid)) and x["status"] == "pending_approval" and x)
        assert st["unresolved_clarification"] is True  # oficer widzi, że pytanie zostało bez odpowiedzi
        await sh.stop()
    asyncio.run(run())


def test_queue_survives_unreachable_shore(tmp_path):
    async def run():
        sh = Ship(settings(tmp_path))  # shore_url wskazuje martwy port
        await sh.start()
        sh.service.ingest_text(TextReportIn(report_id=str(uuid.uuid4()), crew_id="marek", text="Test."))
        q = sh.link.status()["queue_len"]
        assert q > 0
        sh.link.set_link(True)
        await asyncio.sleep(0.6)
        st = sh.link.status()
        assert st["queue_len"] >= q and st["last_error"]  # nic nie zginęło, błąd widoczny
        await sh.stop()
    asyncio.run(run())


def test_high_confidence_is_auto_approved(tmp_path):
    async def run():
        s = settings(tmp_path)
        sh = Ship(s)
        sh.sensors.update("AE1_EXH_T", {"value": 380, "unit": "°C"})
        await sh.start()
        rid = str(uuid.uuid4())
        sh.service.ingest_text(TextReportIn(report_id=rid, crew_id="marek",
                                            text="Agregat numer jeden, temperatura spalin 380 stopni, wibracje."))
        st = await wait_for(lambda: (x := sh.service.state(rid)) and x["status"] == "approved" and x)
        assert st and st["approval"]["auto"] is True and st["approval"]["by"] == "system:auto_approve"
        # oficer próbuje zatwierdzić jeszcze raz -> duplikat, nie nowa decyzja
        res, created = sh.service.approve(rid, ApproveIn(officer_id="anna"))
        assert not created
        # próg > 1 => wszystko idzie do oficera
        sh.s.auto_approve_confidence = 1.1
        rid2 = str(uuid.uuid4())
        sh.service.ingest_text(TextReportIn(report_id=rid2, crew_id="marek",
                                            text="Agregat numer jeden, temperatura spalin 380 stopni, wibracje."))
        st2 = await wait_for(lambda: (x := sh.service.state(rid2)) and x["status"] == "pending_approval" and x)
        assert st2 and st2["decision"]["needs_officer"] is True
        await sh.stop()
    asyncio.run(run())
