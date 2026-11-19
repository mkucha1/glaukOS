import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { config } from '../config';

/** Only created when VITE_BACKEND=supabase; other modes never touch the network for Supabase. */
export const supabase: SupabaseClient | null =
  config.backend === 'supabase' && config.supabaseUrl && config.supabaseKey
    ? createClient(config.supabaseUrl, config.supabaseKey, {
        auth: { persistSession: true, autoRefreshToken: true, storageKey: 'glaukos.auth' },
        realtime: { params: { eventsPerSecond: 20 } },
      })
    : null;

export function requireSupabase(): SupabaseClient {
  if (!supabase) throw new Error('Supabase is not configured: set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY');
  return supabase;
}

/** Make sure this device has an (anonymous) Supabase user. */
export async function ensureSession() {
  const sb = requireSupabase();
  const { data } = await sb.auth.getSession();
  if (data.session) return data.session;
  const { data: signed, error } = await sb.auth.signInAnonymously();
  if (error) throw error;
  return signed.session!;
}
