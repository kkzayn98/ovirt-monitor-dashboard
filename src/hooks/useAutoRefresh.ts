import { useEffect } from 'react';
import { USE_MOCK } from '../services/api';
import { pollSnapshot, useMonitorStore } from '../store';

/**
 * Quietly pull cached snapshots. Backend recollect interval is separate (default 120s).
 * Avoids forcing POST /api/refresh on a short timer (that was causing stutter).
 */
export function useAutoRefresh(intervalMs = 30000) {
  const refreshData = useMonitorStore((s) => s.refreshData);

  useEffect(() => {
    if (USE_MOCK) {
      refreshData();
      const id = setInterval(() => refreshData(), intervalMs);
      return () => clearInterval(id);
    }

    pollSnapshot();
    const id = setInterval(() => {
      pollSnapshot();
    }, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, refreshData]);
}