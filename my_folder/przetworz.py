"""
JSON z STT  ->  JSON dla modelu decyzyjnego.  Jedno zgłoszenie.

Nie wymaga uruchomionego serwera (app.py): woła lokalny LLM bezpośrednio. Musi działać tylko Ollama
(albo inny serwer z LLM_BASE_URL).

Użycie:
    python przetworz.py wejscie.json                  # wynik -> wejscie_wynik.json (obok pliku wejściowego)
    python przetworz.py wejscie.json -o wynik.json    # wynik -> wynik.json
    python przetworz.py - < wejscie.json              # stdin -> stdout (do potoków)
    python przetworz.py --text "yyy pompa numer dwa cieknie"   # sam tekst z STT, wynik na ekran

    python przetworz.py wejscie.json --url http://127.0.0.1:8010   # przez działający serwer app.py

Wejście: JSON z polem `text` (albo `tresc` / `transcript`). Opcjonalnie metadane zgłoszenia
(id, statek, czas_utc, zglaszajacy, lokalizacja, ...) - przechodzą bez zmian.
Wyjście: zgłoszenie w formacie github/backend/decision (schema_version 0.1); model decyzyjny czyta `tresc`.

W kodzie:
    from przetworz import przetworz
    wynik = przetworz({"text": "yyy pompa numer dwa cieknie"})
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("LOG_LEVEL", "WARNING")  # bez logów serwera na ekranie

_app = None


def _get_app():
    global _app
    if _app is None:
        import app  # app.py z tego samego folderu
        _app = app
    return _app


class BladPrzetwarzania(Exception):
    """Czytelny błąd do pokazania użytkownikowi."""


def przetworz(dane: dict, url: str | None = None, timeout: float = 120.0) -> dict:
    """Jeden JSON z STT -> zgłoszenie dla modelu decyzyjnego (dict)."""
    if not isinstance(dane, dict):
        raise BladPrzetwarzania("wejście musi być obiektem JSON, np. {\"text\": \"...\"}")
    if url:
        return _przez_serwer(dane, url, timeout)

    app = _get_app()
    try:
        stt = app.STTInput.model_validate(dane)
    except app.ValidationError as exc:
        bledy = "; ".join(
            "brak tekstu z STT - podaj pole `text` (albo `tresc` / `transcript`)"
            if e["type"] == "missing" and e["loc"] == ("text",)
            else f"{'.'.join(map(str, e['loc'])) or 'wejście'}: {e['msg']}"
            for e in exc.errors())
        raise BladPrzetwarzania(f"niepoprawne wejście: {bledy}") from exc
    try:
        return app.process(stt).model_dump(mode="json")
    except app.LLMUnavailable as exc:
        raise BladPrzetwarzania(f"LLM nie odpowiada ({app.LLM_BASE_URL}). Czy działa Ollama?") from exc
    except app.LLMBadOutput as exc:
        raise BladPrzetwarzania(f"LLM zwrócił niepoprawny wynik: {exc}") from exc


def _przez_serwer(dane: dict, url: str, timeout: float) -> dict:
    req = urllib.request.Request(
        url.rstrip("/") + "/parse?forward=false",
        data=json.dumps(dane, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise BladPrzetwarzania(f"serwer zwrócił HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.URLError as e:
        raise BladPrzetwarzania(f"serwer {url} nie odpowiada: {e.reason}")


def wczytaj_json(sciezka: str | Path) -> dict | list:
    try:
        # utf-8-sig: pliki zapisane w Notatniku/PowerShell często mają BOM
        return json.loads(Path(sciezka).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise BladPrzetwarzania(f"{sciezka}: niepoprawny JSON ({exc})") from exc


def zapisz_json(dane, sciezka: str | Path) -> None:
    sciezka = Path(sciezka)
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text(json.dumps(dane, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="JSON z STT -> JSON dla modelu decyzyjnego (jedno zgłoszenie)",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("wejscie", nargs="?", help="plik JSON z STT albo '-' dla stdin")
    p.add_argument("-o", "--out", help="plik wynikowy (domyślnie <wejscie>_wynik.json; dla stdin: stdout)")
    p.add_argument("--text", help="zamiast pliku: sam tekst z STT")
    p.add_argument("--url", help="użyj działającego serwera app.py zamiast wołać LLM bezpośrednio")
    args = p.parse_args()

    try:
        if args.text:
            dane, domyslne_wyjscie = {"text": args.text}, None
        elif args.wejscie == "-":
            try:
                dane = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
            except json.JSONDecodeError as exc:
                raise BladPrzetwarzania(f"stdin: niepoprawny JSON ({exc})") from exc
            domyslne_wyjscie = None
        elif args.wejscie:
            wej = Path(args.wejscie)
            dane, domyslne_wyjscie = wczytaj_json(wej), wej.with_name(f"{wej.stem}_wynik.json")
        else:
            p.print_help()
            return 2
        wynik = przetworz(dane, url=args.url)
    except (BladPrzetwarzania, json.JSONDecodeError, OSError) as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1

    wyjscie = args.out or domyslne_wyjscie
    if wyjscie:
        zapisz_json(wynik, wyjscie)
        print(f"zapisano: {wyjscie}", file=sys.stderr)
        print(f"tresc:    {wynik['tresc']}", file=sys.stderr)
    else:
        print(json.dumps(wynik, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
