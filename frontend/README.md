# GlaukOS — PWA (frontend)

React + Vite + TypeScript, Tailwind, Dexie (IndexedDB), MQTT.js, vite-plugin-pwa.
Project context and team contracts: [CLAUDE.md](CLAUDE.md).

## Start

```bash
npm install
cp .env.example .env.local   # VITE_BACKEND=mock works without any backend
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

## Supabase backend

Set `VITE_BACKEND=supabase`, `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` in `.env.local`.
Schema, ranks and the speech-to-text contract: [`../supabase/README.md`](../supabase/README.md).

## FastAPI backend (original onboard plan)

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

## On the phones (PWA)

GlaukOS installs like an app from the production address, no app store:

- **Android (Chrome):** open the address → menu ⋮ → **Install app**.
- **iPhone (Safari):** open the address → Share → **Add to Home Screen**. (Must be Safari.)

After the first open the app works without a network: the screens load from the phone, recordings are
saved on the phone and sent automatically when the ship server is reachable again. Test it in airplane
mode: record a report, it shows *Queued offline*, switch airplane mode off, it goes through without a duplicate.

### Switching server without a rebuild

Add parameters to the address once; the phone remembers them:

| Address | What it does |
| --- | --- |
| `…/?backend=mock` | **Plan B.** Offline demo: the whole scenario runs on the phone, no server. Also in the status menu: *Offline demo mode*. |
| `…/?backend=supabase&supabase_url=https://<ship-server>&supabase_key=<publishable key>` | Use a Supabase running on the ship's laptop (true offline: ship Wi-Fi only). |
| `…/?backend=http&api_url=https://<ship-server>&mqtt_url=wss://<ship-server>/mqtt` | Use the FastAPI + MQTT onboard server. |
| `…/?backend=default` | Back to the production backend. |

A ship server on the local network needs HTTPS with a certificate the phone trusts (microphone and
service worker require it), e.g. mkcert's root CA installed on each phone.

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

PWA icons in `public/icons/` and `public/favicon.png` are rendered from `public/logo.png` on the navy background.
