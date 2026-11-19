"""
Wszystkie pliki JSON z folderu reports/  ->  wyniki pod tymi samymi nazwami w folderze wyniki_reports/.

Każdy plik wejściowy to jeden JSON z STT (albo lista takich JSON-ów). Plik wynikowy ma tę samą nazwę
i zawiera zgłoszenie dla modelu decyzyjnego (albo listę zgłoszeń). Nie wymaga uruchomionego serwera.

Użycie:
    python przetworz_folder.py                          # reports/ -> wyniki_reports/
    python przetworz_folder.py moje_reports -o moje_wyniki
    python przetworz_folder.py --pomin-gotowe           # nie przetwarzaj plików, które mają już wynik
    python przetworz_folder.py --url http://127.0.0.1:8010   # przez działający serwer app.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from przetworz import BladPrzetwarzania, przetworz, wczytaj_json, zapisz_json


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Folder z JSON-ami z STT -> folder z JSON-ami dla modelu decyzyjnego")
    p.add_argument("folder", nargs="?", default="reports", help="folder wejściowy (domyślnie: reports)")
    p.add_argument("-o", "--out", default="wyniki_reports", help="folder wynikowy (domyślnie: wyniki_reports)")
    p.add_argument("--pomin-gotowe", action="store_true", help="pomiń pliki, które mają już wynik")
    p.add_argument("--url", help="użyj działającego serwera app.py zamiast wołać LLM bezpośrednio")
    args = p.parse_args()

    wej, wyj = Path(args.folder), Path(args.out)
    if not wej.is_dir():
        print(f"BŁĄD: nie ma folderu {wej}", file=sys.stderr)
        return 1
    if wej.resolve() == wyj.resolve():
        print("BŁĄD: folder wynikowy musi być inny niż wejściowy (wyniki nadpisałyby wejście)", file=sys.stderr)
        return 1
    pliki = sorted(wej.glob("*.json"))
    if not pliki:
        print(f"Brak plików *.json w {wej}")
        return 0

    print(f"{len(pliki)} plików: {wej}/ -> {wyj}/")
    ok = bledy = pominiete = 0
    start = time.perf_counter()
    for n, plik in enumerate(pliki, 1):
        cel = wyj / plik.name
        if args.pomin_gotowe and cel.exists():
            pominiete += 1
            continue
        t0 = time.perf_counter()
        try:
            dane = wczytaj_json(plik)
            wynik = [przetworz(d, url=args.url) for d in dane] if isinstance(dane, list) else przetworz(dane, url=args.url)
            zapisz_json(wynik, cel)
        except BladPrzetwarzania as exc:
            bledy += 1
            print(f"[{n}/{len(pliki)}] {plik.name}  BŁĄD: {exc}")
            if "nie odpowiada" in str(exc):  # LLM/serwer leży - nie ma sensu męczyć reszty plików
                print("Przerywam: bez modelu pozostałe pliki też się nie przetworzą.")
                break
            continue
        ok += 1
        tresc = (wynik[0] if isinstance(wynik, list) and wynik else wynik).get("tresc", "") if wynik else ""
        print(f"[{n}/{len(pliki)}] {plik.name}  {time.perf_counter() - t0:.1f} s  {tresc[:100]}")

    print(f"\nGotowe: {ok} OK, {bledy} błędów, {pominiete} pominiętych, {time.perf_counter() - start:.0f} s. "
          f"Wyniki w {wyj}/")
    return 1 if bledy else 0


if __name__ == "__main__":
    sys.exit(main())
