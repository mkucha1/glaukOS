const env = import.meta.env;

export type Backend = 'mock' | 'supabase' | 'http';

/**
 * Runtime overrides, so one installed app can switch backend without a rebuild:
 *   ?backend=mock                                  plan B: everything in the browser, no network
 *   ?backend=supabase&supabase_url=…&supabase_key=… a ship server running Supabase locally
 *   ?backend=http&api_url=…&mqtt_url=…             the FastAPI + MQTT onboard server
 *   ?backend=default                               back to what this build was made with
 * Values are remembered on the device (localStorage) and removed from the address bar.
 */
const KEYS = ['backend', 'supabase_url', 'supabase_key', 'api_url', 'mqtt_url'] as const;
type Key = (typeof KEYS)[number];
const PREFIX = 'glaukos.cfg.';

function readOverrides(): Partial<Record<Key, string>> {
  const out: Partial<Record<Key, string>> = {};
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get('backend') === 'default') {
      for (const k of KEYS) localStorage.removeItem(PREFIX + k);
      url.searchParams.delete('backend');
    }
    let touched = false;
    for (const k of KEYS) {
      const v = url.searchParams.get(k);
      if (v !== null) {
        localStorage.setItem(PREFIX + k, v);
        url.searchParams.delete(k);
        touched = true;
      }
    }
    if (touched || url.href !== window.location.href) window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    for (const k of KEYS) {
      const v = localStorage.getItem(PREFIX + k);
      if (v) out[k] = v;
    }
  } catch {
    /* no window or storage: build-time values only */
  }
  return out;
}

const o = typeof window !== 'undefined' ? readOverrides() : {};
const isBackend = (v?: string): v is Backend => v === 'mock' || v === 'supabase' || v === 'http';

/** VITE_BACKEND wins over VITE_MOCK; a runtime override wins over both. */
const builtBackend: Backend = isBackend(env.VITE_BACKEND)
  ? env.VITE_BACKEND
  : env.VITE_MOCK === '1' || env.VITE_MOCK === 'true'
    ? 'mock'
    : 'http';
const backend: Backend = isBackend(o.backend) ? o.backend : builtBackend;

export const config = {
  backend,
  builtBackend,
  overridden: backend !== builtBackend || !!(o.supabase_url || o.api_url),
  apiUrl: (o.api_url ?? env.VITE_API_URL ?? '').replace(/\/$/, ''),
  mqttUrl: o.mqtt_url ?? env.VITE_MQTT_URL ?? '',
  shipId: env.VITE_SHIP_ID ?? 'demo-ship',
  supabaseUrl: o.supabase_url ?? env.VITE_SUPABASE_URL ?? '',
  supabaseKey: o.supabase_key ?? env.VITE_SUPABASE_PUBLISHABLE_KEY ?? '',
  mock: backend === 'mock',
};

/** Switch backend on this device and reload. `null` returns to the build's default. */
export function switchBackend(next: Partial<Record<Key, string>> | null) {
  try {
    for (const k of KEYS) localStorage.removeItem(PREFIX + k);
    if (next) for (const [k, v] of Object.entries(next)) if (v) localStorage.setItem(PREFIX + k, v);
  } catch {
    /* ignore */
  }
}

/** crypto.randomUUID only exists in secure contexts; fall back so plain-HTTP LAN testing still works. */
export function uuid(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export const nowIso = () => new Date().toISOString();
