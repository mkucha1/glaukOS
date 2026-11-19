#!/usr/bin/env python3
"""Test end-to-end całego scenariusza demo — tylko biblioteka standardowa.

    python3 scripts/e2e_test.py                      # serwer :8000, ląd :9000
    python3 scripts/e2e_test.py --api https://192.168.8.100 --shore http://192.168.8.100:9000 --insecure

Sprawdza: idempotencję (5 równoległych duplikatów), przerwany upload (martwa strefa w trakcie),
konflikt report_id, pytanie zwrotne (SSE person/{crew}), weryfikację z czujnikiem, zatwierdzenie,
zadanie, auto-zatwierdzenie przy wysokiej pewności, kolejkę na ląd z satelitą OFF/ON (tylko JSON, bez audio)
i łańcuch audytu.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

P = argparse.ArgumentParser()
P.add_argument("--api", default=os.getenv("API", "http://localhost:8000"))
P.add_argument("--shore", default=os.getenv("SHORE", "http://localhost:9000"))
P.add_argument("--insecure", action="store_true", help="akceptuj certyfikat self-signed")
A = P.parse_args()
CTX = ssl._create_unverified_context() if A.insecure else None
FAILS = 0


def check(cond: bool, msg: str) -> None:
    global FAILS
    print(("  ✔ " if cond else "  ✘ ") + msg)
    if not cond:
        FAILS += 1


def req(method: str, url: str, body: bytes | None = None, headers: dict | None = None) -> tuple[int, dict]:
    r = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=30, context=CTX) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def jpost(path: str, data: dict, base: str | None = None):
    return req("POST", (base or A.api) + path, json.dumps(data).encode(), {"Content-Type": "application/json"})


def get(path: str, base: str | None = None):
    return req("GET", (base or A.api) + path)


def multipart(fields: dict, file_bytes: bytes, mime: str = "audio/webm") -> tuple[bytes, str]:
    b = "----mozg" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.append(f'--{b}\r\nContent-Disposition: form-data; name="audio"; filename="rec.webm"\r\n'
               f"Content-Type: {mime}\r\n\r\n".encode() + file_bytes + b"\r\n")
    out.append(f"--{b}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={b}"


def upload(path: str, fields: dict, audio: bytes):
    body, ct = multipart(fields, audio)
    return req("POST", A.api + path, body, {"Content-Type": ct})


def wait_status(rid: str, want: set[str], timeout: float = 20) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, st = get(f"/api/reports/{rid}")
        if code == 200 and st["status"] in want:
            return st
        time.sleep(0.15)
    return get(f"/api/reports/{rid}")[1]


def sse_listen(topics: str, sink: list, stop: threading.Event) -> None:
    url = f"{A.api}/api/stream?topics={urllib.parse.quote(topics)}"
    try:
        with urllib.request.urlopen(url, timeout=60, context=CTX) as resp:
            for raw in resp:
                if stop.is_set():
                    return
                line = raw.decode().strip()
                if line.startswith("data: "):
                    sink.append(json.loads(line[6:]))
    except Exception as e:
        sink.append({"error": repr(e)})


def interrupted_upload(rid: str) -> None:
    """Symulacja martwej strefy: połączenie zrywa się w połowie wysyłania nagrania."""
    u = urllib.parse.urlparse(A.api)
    port = u.port or (443 if u.scheme == "https" else 80)
    body, ct = multipart({"report_id": rid, "crew_id": "marek"}, os.urandom(200_000))
    s = socket.create_connection((u.hostname, port), timeout=5)
    if u.scheme == "https":
        s = (CTX or ssl.create_default_context()).wrap_socket(s, server_hostname=u.hostname)
    head = (f"POST /api/reports/audio HTTP/1.1\r\nHost: {u.hostname}\r\nContent-Type: {ct}\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
    s.sendall(head + body[: len(body) // 3])
    s.close()


def main() -> int:
    print(f"API {A.api} · LĄD {A.shore}")
    code, h = get("/api/health")
    check(code == 200, f"serwer żyje, pluginy={h.get('plugins')}, MQTT={h.get('hub', {}).get('mqtt')}")
    code, _ = get("/api/health", A.shore)
    check(code == 200, "atrapa lądu żyje")
    _, shore0 = get("/api/stats", A.shore)

    print("\n[1] Satelita OFF")
    _, s = jpost("/api/sync/link", {"up": False, "actor": "e2e"})
    check(s["link_up"] is False, "łącze wyłączone")
    jpost("/api/sensors", [{"tag": "CW_PUMP_2_P", "value": 1.9, "unit": "bar"},
                           {"tag": "CW_PUMP_1_P", "value": 2.4, "unit": "bar"},
                           {"tag": "AE1_EXH_T", "value": 381, "unit": "°C"}])

    print("\n[2] Zgłoszenie nagrane w martwej strefie 7 min temu, 5 równoległych ponowień")
    rid = str(uuid.uuid4())
    audio = os.urandom(120_000)
    rec_at = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()
    fields = {"report_id": rid, "crew_id": "marek", "device": "phone-marek", "recorded_at": rec_at,
              "sha256": hashlib.sha256(audio).hexdigest(),
              "transcript_hint": "Pompa chłodzenia, ciśnienie spada do 1,8 bara, przeciek na uszczelnieniu."}
    sink, stop = [], threading.Event()
    threading.Thread(target=sse_listen, args=("person/marek", sink, stop), daemon=True).start()
    time.sleep(0.5)
    results: list = []
    t0 = time.time()
    ths = [threading.Thread(target=lambda: results.append(upload("/api/reports/audio", fields, audio)))
           for _ in range(5)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    codes = sorted(c for c, _ in results)
    check(codes.count(201) == 1 and codes.count(200) == 4, f"1×201 + 4×200 (duplikaty) — {codes}")
    _, evs = get(f"/api/events?report_id={rid}")
    check(sum(e["type"] == "report.recorded" for e in evs) == 1, "w rejestrze dokładnie jedno report.recorded")
    check(evs[0]["ts"][:16] == rec_at.replace("+00:00", "Z")[:16], "czas zdarzenia = czas nagrania na telefonie")

    code, r = upload("/api/reports/audio", {**fields, "sha256": ""}, os.urandom(1000))
    check(code == 409, f"ten sam report_id z innym nagraniem -> 409 ({code})")

    print("\n[3] Przerwany upload (Wi-Fi znika w połowie)")
    rid_cut = str(uuid.uuid4())
    interrupted_upload(rid_cut)
    time.sleep(0.5)
    code, _ = get(f"/api/reports/{rid_cut}")
    check(code == 404, "niekompletne nagranie nie trafiło do rejestru (telefon ponowi)")
    code, r = upload("/api/reports/audio", {"report_id": rid_cut, "crew_id": "marek",
                                             "transcript_hint": "Agregat numer jeden, wibracje."}, os.urandom(5000))
    check(code == 201, "ponowienie po odzyskaniu zasięgu przyjęte")

    print("\n[4] Pytanie zwrotne")
    st = wait_status(rid, {"awaiting_clarification"})
    dt = time.time() - t0
    check(st["status"] == "awaiting_clarification", f"status awaiting_clarification po {dt:.2f}s")
    q = st["clarifications"][-1]["question"] if st["clarifications"] else ""
    check("dwa" in q.lower() or "two" in q.lower(), f"pytanie: „{q}”")
    time.sleep(0.3)
    check(any(m.get("topic") == "person/marek" and m["payload"].get("type") == "clarification" for m in sink),
          "pytanie dotarło na person/marek (SSE)")

    ans_id = str(uuid.uuid4())
    ans_audio = os.urandom(8000)
    code1, _ = upload(f"/api/reports/{rid}/clarify", {"event_id": ans_id, "crew_id": "marek",
                                                      "transcript_hint": "Dwa"}, ans_audio)
    code2, r2 = upload(f"/api/reports/{rid}/clarify", {"event_id": ans_id, "crew_id": "marek",
                                                       "transcript_hint": "Dwa"}, ans_audio)
    check(code1 == 201 and code2 == 200 and r2.get("duplicate"), f"odpowiedź głosowa + duplikat ({code1}, {code2})")

    print("\n[5] Weryfikacja z czujnikiem")
    st = wait_status(rid, {"pending_approval"})
    f = st.get("form") or {}
    c = ((st.get("decision") or {}).get("checks") or [{}])[0]
    check(st["status"] == "pending_approval",
          f"do oficera, bo pewność mała: {(st.get('decision') or {}).get('approval_reason')}")
    check(any(e["type"] == "report.refined" for e in get(f"/api/events?report_id={rid}")[1]),
          f"raport przerobiony przez Daniela: „{(st.get('refined') or {}).get('text')}”")
    check(f.get("equipment") == "Cooling water pump No. 2", f"urządzenie: {f.get('equipment')} SFI {f.get('sfi_code')}")
    check(c.get("ok") is True, f"czujnik {c.get('tag')}: {c.get('measured')} vs zgłoszone {c.get('reported')} — zgodne")
    check(f.get("priority") == 4, f"priorytet {f.get('priority')}; EN: {f.get('text_en')}")

    print("\n[6] Zatwierdzenie i zadanie")
    appr = {"event_id": str(uuid.uuid4()), "officer_id": "anna", "decision": "approve", "assignee": "tom"}
    c1, a1 = jpost(f"/api/reports/{rid}/approve", appr)
    c2, a2 = jpost(f"/api/reports/{rid}/approve", appr)
    c3, _ = jpost(f"/api/reports/{rid}/approve", {**appr, "event_id": str(uuid.uuid4()), "decision": "reject"})
    check(c1 == 201 and c2 == 200 and c3 == 409, f"zatwierdzenie 201, powtórka 200, sprzeczna decyzja 409 ({c1},{c2},{c3})")
    tid = a1["tasks"][0]["task_id"]
    c, t = jpost(f"/api/tasks/{tid}/ack", {"crew_id": "tom", "event_id": str(uuid.uuid4())})
    check(c == 201 and t["status"] == "acknowledged", "Tom potwierdził zadanie")

    print("\n[6b] Wysoka pewność: zatwierdzenie automatyczne, bez oficera")
    rid_auto = str(uuid.uuid4())
    jpost("/api/reports/text", {"report_id": rid_auto, "crew_id": "marek",
                                "text": "yyy agregat numer jeden, temperatura spalin 380 stopni, wibracje"})
    st = wait_status(rid_auto, {"approved", "assigned"})
    check(st["status"] == "approved" and (st.get("approval") or {}).get("auto") is True,
          f"zatwierdzone automatycznie ({(st.get('decision') or {}).get('approval_reason')})")
    check(not (st.get("refined") or {}).get("text", "").lower().startswith("yyy"), "wtrącenie „yyy” usunięte")

    print("\n[7] Kolejka na ląd przy satelicie OFF")
    _, s = get("/api/sync/status")
    _, shore1 = get("/api/stats", A.shore)
    check(s["queue_len"] > 0, f"kolejka rośnie: {s['queue_len']} zdarzeń")
    check(shore1["events"] == shore0["events"], "na lądzie nic nowego (brak łącza)")

    print("\n[8] Satelita ON")
    jpost("/api/sync/link", {"up": True, "actor": "e2e"})
    t1 = time.time()
    while time.time() - t1 < 20:
        _, s = get("/api/sync/status")
        if s["queue_len"] == 0:
            break
        time.sleep(0.2)
    check(s["queue_len"] == 0, f"kolejka spadła do zera w {time.time() - t1:.1f}s")
    _, shore2 = get("/api/stats", A.shore)
    _, shore_reports = get("/api/reports", A.shore)
    sr = next((x for x in shore_reports if x["report_id"] == rid), {})
    check(sr.get("equipment") == "Cooling water pump No. 2", "ląd widzi zgłoszenie po angielsku")
    check(sr.get("audio") and "file" not in sr["audio"] and sr["audio"]["bytes"] == len(audio),
          "na ląd poszły tylko metadane audio (sha256, rozmiar) — plik został na statku")
    check(s["sent"]["bytes_wire"] < len(audio), f"przez satelitę {s['sent']['bytes_wire']} B vs samo nagranie {len(audio)} B")

    print("\n[9] Audyt")
    _, v = get("/api/audit/verify")
    check(v["ok"], f"łańcuch skrótów nienaruszony ({v.get('checked')} zdarzeń)")
    stop.set()
    print("\nWYNIK:", "WSZYSTKO OK" if FAILS == 0 else f"{FAILS} BŁĘDÓW")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
