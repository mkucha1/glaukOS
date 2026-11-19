import { createContext, useContext } from 'react';
import { uuid } from '../config';
import { positionById, positionLabel, type PositionId } from './positions';
import type { SectorId } from './ship';

/** The "login": a name, a position on board and the station you work at. */
export interface Profile {
  name: string;
  position: PositionId;
  station: SectorId;
}

const PROFILE_KEY = 'shipbrain.profile';
const DEVICE_KEY = 'shipbrain.device';

export const homeFor = (p: Pick<Profile, 'position'>) => ((positionById(p.position)?.approves.length ?? 0) > 0 ? '/officer' : '/mechanic');
export const roleLabel = (position: string) => positionLabel(position);

export function loadProfile(): Profile | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<Profile> & { role?: string };
    // Profiles from before positions existed.
    if (!p.position && p.role) p.position = (p.role === 'officer' ? 'chief_officer' : p.role) as PositionId;
    if (!p.name || !positionById(p.position)) return null;
    return { name: p.name, position: p.position!, station: p.station ?? positionById(p.position)!.station };
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

export const slug = (s: string) =>
  s
    .trim()
    .toLowerCase()
    .replace(/ł/g, 'l')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '') || 'crew';

/** "2nd_engineer:mateusz". Also the crewId in `person/{crewId}` and the assignee in tasks. */
export const actorOf = (p: Pick<Profile, 'name' | 'position'>) => `${p.position}:${slug(p.name)}`;

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
  setProfile: (p: Profile | null) => Promise<void>;
}>({ profile: null, setProfile: async () => {} });

export const useProfile = () => useContext(ProfileContext);
