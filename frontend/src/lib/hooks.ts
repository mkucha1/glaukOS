import { liveQuery } from 'dexie';
import { useEffect, useState } from 'react';
import { api } from './api';
import { bus, type BusState } from './mqtt';
import type { SyncStatus } from '../types';

export function useLiveQuery<T>(query: () => Promise<T>, deps: unknown[], initial: T): T {
  const [value, setValue] = useState<T>(initial);
  useEffect(() => {
    const sub = liveQuery(query).subscribe({ next: setValue, error: (e) => console.error(e) });
    return () => sub.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return value;
}

export function useBusState(): BusState {
  const [s, setS] = useState<BusState>(bus.state);
  useEffect(() => bus.onState(setS), []);
  return s;
}

/** Shore-link status from the server; null while unknown (server unreachable). */
export function useSyncStatus(intervalMs = 2000) {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    const poll = () =>
      api
        .syncStatus()
        .then((s) => alive && setStatus(s))
        .catch(() => alive && setStatus(null));
    poll();
    const t = setInterval(poll, intervalMs);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [intervalMs, tick]);
  return { status, refresh: () => setTick((x) => x + 1) };
}
