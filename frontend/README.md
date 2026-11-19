# Ship Brain — PWA (frontend)

React + Vite + TypeScript, Tailwind, Dexie (IndexedDB), MQTT.js, vite-plugin-pwa.
Project context and team contracts: [CLAUDE.md](CLAUDE.md).

## Start

```bash
npm install
cp .env.example .env.local   # VITE_MOCK=1 works without any backend
npm run dev                  # http://localhost:5173
```

Test offline behaviour on the production build, not in dev:

```bash
npm run build && npm run preview   # http://localhost:4173
```

## Mock mode (`VITE_MOCK=1`)

An in-browser fake server (`src/lib/mock.ts`) plays the demo scenario: report → transcript → form →
question "pump 1 or 2?" → sensor check → awaiting approval → approve → task. Tabs of the same
browser share the mock register, so you can open `/mechanic` and `/officer` side by side.

- **Dead zone** button (mock only): simulates losing Wi-Fi to the ship server. Recordings stay in
  the outbox and go out when you leave the dead zone. Chrome DevTools → Network → Offline works too.
- **Cut satellite link** (officer screen): the shore queue counter grows; restoring it drains to 0.
- **Reset demo** (officer screen): clears mock events and the local cache.

## Real backend

`.env.local`:

```
VITE_API_URL=https://192.168.50.10:8443
VITE_MQTT_URL=wss://192.168.50.10:8084
VITE_SHIP_ID=demo-ship
VITE_MOCK=0
```

If the server answers differently than the contract, fix the adapter in `src/lib/api.ts`, not `src/types.ts`.

## HTTPS for phones (microphone + service worker need it)

```bash
brew install mkcert && mkcert -install
mkdir -p certs && mkcert -cert-file certs/cert.pem -key-file certs/key.pem 192.168.50.10 localhost
```

Vite picks up `certs/` automatically (dev and preview, bound to `0.0.0.0`). On each phone install
the mkcert root CA (`mkcert -CAROOT` → `rootCA.pem`): on iOS, AirDrop it, install the profile, then
enable it under Settings → General → About → Certificate Trust Settings. The API and the MQTT
WebSocket must use a certificate the phone trusts as well.

Install the app: Android Chrome → menu → Install app; iOS Safari → Share → Add to Home Screen.

## Layout

```
src/
  types.ts              team contracts (section 6), do not change alone
  config.ts             env, uuid()
  app/                  App (routing, bootstrap), StatusBar
  features/role|mechanic|officer|handover
  components/ui.tsx     badges, buttons, cards
  lib/
    api.ts              ApiClient: HTTP + mock
    mqtt.ts             EventBus: MQTT.js + mock
    mock.ts             in-browser fake server
    outbox.ts           IndexedDB-first send queue with backoff
    db.ts               Dexie schema (outbox, events cache)
    store.ts            event store, dedupe by event_id, status derivation
    recorder.ts         MediaRecorder, mime selection
    speech.ts           speechSynthesis
    profile.ts          name/role "login", device id
```

`node scripts/gen-icons.mjs` regenerates the PWA icons.
