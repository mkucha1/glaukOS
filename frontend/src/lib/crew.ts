// Crew roster: who is on board, where they are stationed and whether they are on duty or resting.
import { useSyncExternalStore } from 'react';
import type { PositionId } from './positions';
import type { SectorId } from './ship';

export interface CrewMember {
  id: string;
  name: string;
  position: PositionId;
  actor: string;
  station: SectorId;
  on_duty: boolean;
  duty_changed_at: string;
}

const byId = new Map<string, CrewMember>();
let snapshot: CrewMember[] = [];
const listeners = new Set<() => void>();

function publish() {
  snapshot = [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
  listeners.forEach((l) => l());
}

export function setCrew(list: CrewMember[]) {
  byId.clear();
  for (const c of list) byId.set(c.id, c);
  publish();
}

export function upsertCrew(c: CrewMember) {
  byId.set(c.id, c);
  publish();
}

export function removeCrew(id: string) {
  if (byId.delete(id)) publish();
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export const useCrew = () => useSyncExternalStore(subscribe, () => snapshot);

export const crewByActor = (crew: CrewMember[], actor?: string) => crew.find((c) => c.actor === actor);
