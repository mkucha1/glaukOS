"""Backendy decyzyjne: prawdziwy serwer Basala (HTTP) i atrapa do testów bez GPU."""
from __future__ import annotations

import json
import random
import time
import urllib.request

from .config import api_questions


class BasalHTTP:
    """Klient serwera `basal-serve` (POST /v1/systemone)."""

    def __init__(self, url: str = "http://127.0.0.1:8000/v1/systemone", timeout: float = 600.0):
        self.url = url
        self.timeout = timeout

    def decide(self, state: str, questions: dict) -> dict:
        body = json.dumps({"state": state, "questions": api_questions(questions)}).encode("utf-8")
        req = urllib.request.Request(self.url, data=body,
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())


class MockBackend:
    """Atrapa zwracająca odpowiedzi w formacie Basala.

    Służy wyłącznie do sprawdzenia, czy cały potok działa (bez GPU i bez modelu).
    Wyniki NIE mówią nic o jakości modelu.
    """

    KEYWORDS = {
        "maszynownia": ["pomp", "silnik", "cylind", "generator", "lamp", "light", "olej", "oil", "separator"],
        "pokład": ["lin", "mooring", "ładowni", "reling", "farb", "dziob", "ruf", "trap"],
        "kuchnia": ["chłodni", "freezer", "kuchar", "mięso", "meat", "frytown"],
    }

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def _probs(self, keys: list[str], favourite: str | None) -> dict:
        raw = {k: self.rng.random() * 0.3 for k in keys}
        if favourite in raw:
            raw[favourite] += self.rng.uniform(0.5, 2.0)
        s = sum(raw.values())
        return {k: v / s for k, v in raw.items()}

    def decide(self, state: str, questions: dict) -> dict:
        t0 = time.perf_counter()
        low = state.lower()
        answers = {}
        for name, q in questions.items():
            if q["type"] == "noul":
                keys, fav = ["true", "false"], ("true" if any(
                    w in low for w in ["prawie", "almost", "ranny", "oparz", "ogień", "dym", "slippery", "wejść woda"]
                ) else "false")
            elif q["type"] == "score":
                keys = [str(i) for i in range(len(q["criteria"]))]
                fav = self.rng.choice(keys)
            else:
                keys = list(q["criteria"].keys())
                fav = next((d for d, ws in self.KEYWORDS.items() if d in keys and any(w in low for w in ws)), None)
                fav = fav or self.rng.choice(keys)
            p = self._probs(keys, fav)
            conf = max(p.values())
            ans = {"type": q["type"], "probabilities": p, "confidence": conf}
            if q["type"] == "noul":
                ans["noul"] = p["true"]
            elif q["type"] == "score":
                ans["score"] = sum(int(k) * v for k, v in p.items())
            else:
                ans["choice"] = max(p, key=p.get)
            answers[name] = ans
        return {"model": "mock", "answers": answers,
                "usage": {"latency_ms": round((time.perf_counter() - t0) * 1000, 2)}}


def get_backend(name: str, url: str | None = None, timeout: float | None = None):
    from . import settings
    if name == "mock":
        return MockBackend()
    if name == "basal":
        return BasalHTTP(url or settings.get("BASAL_URL"),
                         timeout=timeout if timeout is not None else float(settings.get("BASAL_TIMEOUT")))
    raise ValueError(f"nieznany backend: {name}")
