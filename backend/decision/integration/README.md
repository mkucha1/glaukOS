# Integracja z serwerem statku (`mozg-statku`, gałąź `offline`)

Serwer należy do zespołu i jest na gałęzi `offline`, więc na `decision-layer` go nie zmieniamy.
Tu leży wszystko, co warstwa decyzyjna potrzebuje po stronie serwera:

| Plik | Co to jest | Gdzie trafia w `mozg-statku/` |
|---|---|---|
| `mozg-statku/decision.py` | plugin: klient Basala (stdlib), sektor do formularza, decyzja | `server/plugins/decision.py` |
| `mozg-statku/decision.json` | pytania, progi i mapowania (`shipdec export-server-config`) | `server/config/decision.json` |
| `mozg-statku/crew.json` | załoga z rolami z frontendu (ivan, kapitan → `officer`, stopień w `rank`) | `server/config/crew.json` |
| `mozg-statku.patch` | wszystkie zmiany w serwerze względem `origin/offline` | cały katalog |

Co zmienia łatka (do uzgodnienia z zespołem):
- priorytet 1–3 jak we frontendzie (P1 = najwyższy) w `contracts.py` i zaślepkach;
- osobna flaga `alarm` (pożar, dym) zamiast „priorytet 5” → alert na mostek (`notify.py`);
- role z frontendu w `crew.json`;
- `brain.py` woła warstwę decyzyjną (Basal raz na treść; bez Basala decyzja z reguł);
- testy pluginu, `BASAL_URL` / `DECISION_ENABLED` w `docker-compose.yml`, opis w `docs/CONTRACTS.md`.

Nałożenie na gałąź z serwerem (z katalogu głównego repo):

```bash
git apply backend/decision/integration/mozg-statku.patch
```

Gdy serwer jest w repo, `shipdec export-server-config` zapisuje `decision.json` prosto do
`mozg-statku/server/config/`; bez serwera — tutaj.
