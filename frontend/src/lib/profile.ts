import { createContext, useContext } from 'react';
import { uuid } from '../config';
import type { Role } from '../types';

export interface Profile {
  name: string;
  role: Role;
}

const PROFILE_KEY = 'shipbrain.profile';
const DEVICE_KEY = 'shipbrain.device';

export const ROLES: { id: Role; label: string; home: string }[] = [
  { id: '2nd_engineer', label: '2nd Engineer', home: '/mechanic' },
  { id: 'chief_engineer', label: 'Chief Engineer', home: '/mechanic' },
  { id: 'officer', label: 'Officer', home: '/officer' },
];

export const homeFor = (role: Role) => ROLES.find((r) => r.id === role)?.home ?? '/';
export const roleLabel = (role: string) => ROLES.find((r) => r.id === role)?.label ?? role;

export function loadProfile(): Profile | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? (JSON.parse(raw) as Profile) : null;
  } catch {
    return null;
  }
}

export function saveProfile(p: Profile | null) {
  try {
    if (p) localStorage.setItem(PROFILE_KEY, JSON.stringify(p));
    else localStorage.removeItem(PROFILE_KEY);
  } catch {
    /* private mode: profile lives for this session only */
  }
}

const slug = (s: string) =>
  s
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ł/g, 'l')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '') || 'crew';

/** "2nd_engineer:mateusz". Also used as crewId in `person/{crewId}` (to confirm with backend). */
export const actorOf = (p: Profile) => `${p.role}:${slug(p.name)}`;

/** Stable per device; used as MQTT clientId so the persistent session survives reconnects. */
export function deviceId(): string {
  try {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = `pwa-${uuid().slice(0, 8)}`;
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    return 'pwa-ephemeral';
  }
}

export const ProfileContext = createContext<{
  profile: Profile | null;
  setProfile: (p: Profile | null) => void;
}>({ profile: null, setProfile: () => {} });

export const useProfile = () => useContext(ProfileContext);
