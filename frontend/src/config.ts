const env = import.meta.env;

export type Backend = 'mock' | 'supabase' | 'http';

/** VITE_BACKEND wins; older envs with only VITE_MOCK keep working. */
const backend: Backend =
  env.VITE_BACKEND === 'supabase' || env.VITE_BACKEND === 'http' || env.VITE_BACKEND === 'mock'
    ? env.VITE_BACKEND
    : env.VITE_MOCK === '1' || env.VITE_MOCK === 'true'
      ? 'mock'
      : 'http';

export const config = {
  backend,
  apiUrl: (env.VITE_API_URL ?? '').replace(/\/$/, ''),
  mqttUrl: env.VITE_MQTT_URL ?? '',
  shipId: env.VITE_SHIP_ID ?? 'demo-ship',
  supabaseUrl: env.VITE_SUPABASE_URL ?? '',
  supabaseKey: env.VITE_SUPABASE_PUBLISHABLE_KEY ?? '',
  mock: backend === 'mock',
};

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
