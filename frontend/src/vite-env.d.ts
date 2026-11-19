/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_MQTT_URL?: string;
  readonly VITE_SHIP_ID?: string;
  readonly VITE_MOCK?: string;
  readonly VITE_BACKEND?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
}
