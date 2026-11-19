# Mózg statku / Ship Brain

Pokładowy rejestr zdarzeń: głos załogi → zatwierdzone wpisy, zadania i briefingi, także bez internetu.
Hackathon Kongsberg Maritime × Wydział Informatyki.

## Struktura repozytorium

| Folder | Co | Właściciel |
| --- | --- | --- |
| `frontend/` | Aplikacja PWA (React + Vite + TS): mechanik, oficer, briefing, przekrój statku | Oliwier |
| `backend/` | FastAPI, Mosquitto, SQLite, kolejka na ląd, Docker Compose | Szymon |
| `speech/` | DeepFilterNet + faster-whisper | Mateusz |
| `llm/` | Formularz, tłumaczenie, reguły, symulator czujników | Maciej |

Wspólne kontrakty (koperta zdarzenia, formularz, tematy MQTT, API HTTP) są w
[`frontend/CLAUDE.md`](frontend/CLAUDE.md), sekcja 6, i w kodzie w [`frontend/src/types.ts`](frontend/src/types.ts).
Zmiany kontraktów tylko po uzgodnieniu z zespołem.

## Szybki start frontendu

```bash
cd frontend
npm install
cp .env.example .env.local   # VITE_MOCK=1 działa bez backendu
npm run dev
```

Podpięcie backendu: w `frontend/.env.local` ustaw `VITE_MOCK=0`, `VITE_API_URL` i `VITE_MQTT_URL`.
Szczegóły w [`frontend/README.md`](frontend/README.md).
