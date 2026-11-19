import { useMemo } from 'react';
import { config } from '../config';
import { canSeeReport } from './positions';
import { actorOf, useProfile } from './profile';
import { useReports, type ReportView } from './store';

/**
 * Reports this person may see: own department, departments they approve, tasks assigned to them.
 * Supabase already enforces this with RLS; filtering here too keeps mock mode honest and hides
 * anything left in the local cache from a previous user.
 */
export function useVisibleReports(): ReportView[] {
  const reports = useReports();
  const { profile } = useProfile();
  return useMemo(() => {
    if (!profile) return config.mock ? reports : [];
    const me = actorOf(profile);
    return reports.filter((r) => canSeeReport(profile.position, me, r));
  }, [reports, profile]);
}
