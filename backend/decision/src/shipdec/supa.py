"""Minimalny klient Supabase dla workera (PostgREST + Storage przez HTTP, tylko biblioteka standardowa).

Klucz: secret / service role (SUPABASE_SECRET_KEY) — omija RLS, jak w supabase/README.md.
Nigdy nie trafia do frontendu ani do repo (tylko .env).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class SupabaseError(RuntimeError):
    pass


class Supabase:
    def __init__(self, url: str, key: str, timeout: float = 30.0):
        if not url or not key:
            raise SupabaseError("Brak SUPABASE_URL albo SUPABASE_SECRET_KEY w .env")
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout

    def _req(self, method: str, path: str, body=None, headers: dict | None = None, raw: bool = False):
        h = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        req = urllib.request.Request(self.url + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                content = r.read()
        except urllib.error.HTTPError as e:
            raise SupabaseError(f"{method} {path.split('?')[0]}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        if raw:
            return content
        return json.loads(content) if content else None

    # ---- PostgREST
    def select(self, table: str, **params) -> list[dict]:
        return self._req("GET", f"/rest/v1/{table}?" + urllib.parse.urlencode(params))

    def insert(self, table: str, rows: dict | list[dict]) -> None:
        self._req("POST", f"/rest/v1/{table}", rows, {"Prefer": "return=minimal"})

    def update(self, table: str, values: dict, **filters) -> None:
        self._req("PATCH", f"/rest/v1/{table}?" + urllib.parse.urlencode(filters), values, {"Prefer": "return=minimal"})

    # ---- Storage
    def download(self, bucket: str, path: str) -> bytes:
        return self._req("GET", f"/storage/v1/object/{bucket}/{urllib.parse.quote(path)}", raw=True)
