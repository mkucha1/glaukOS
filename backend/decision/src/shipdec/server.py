"""Klient serwera pokładowego (mozg-statku): wysyłka zgłoszeń tekstowych.

POST /api/reports/text  {report_id, crew_id, text, lang, recorded_at, device}
201 = nowe, 200 = duplikat (ten sam report_id — wysyłka jest idempotentna), 409 = konflikt.
Pole `_meta` nie jest wysyłane — to nasze metadane do ewaluacji i do przekroju statku.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

API_FIELDS = ("report_id", "crew_id", "text", "lang", "recorded_at", "device")


def post_report(report: dict, server: str, timeout: float = 10.0) -> int:
    body = json.dumps({k: report[k] for k in API_FIELDS if report.get(k) is not None}).encode("utf-8")
    req = urllib.request.Request(server.rstrip("/") + "/api/reports/text", data=body,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def push_reports(reports: list[dict], server: str) -> dict:
    counts: dict[int, int] = {}
    for r in reports:
        code = post_report(r, server)
        counts[code] = counts.get(code, 0) + 1
    print(f"wysłano {len(reports)} zgłoszeń -> {server}: " +
          ", ".join(f"HTTP {c}: {n}" for c, n in sorted(counts.items())))
    return counts
