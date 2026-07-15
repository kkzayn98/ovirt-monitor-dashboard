import { create } from 'zustand';
import { User, Process, ClusterStats } from '../types';
import { generateMockUsers, generateMockProcesses, getClusterStats } from '../utils/mockData';
import {
  USE_MOCK,
  fetchUsers,
  fetchStats,
  fetchUserProcesses,
  fetchHostProcesses,
  fetchHosts,
  fetchAlerts,
  fetchMeta,
  triggerRefresh,
  HostStatus,
  RefreshMeta,
  Alert,
} from '../services/api';

export type SortKey = 'username' | 'cpuUsage' | 'memoryUsage' | 'loginTime';
export type SortDir = 'asc' | 'desc';

export interface SelectedHost {
  hostname: string;
  ip: string;
}

interface MonitorStore {
  users: User[];
  filteredUsers: User[];
  selectedUser: User | null;
  userProcesses: Process[];
  selectedHost: SelectedHost | null;
  hostProcesses: Process[];
  clusterStats: ClusterStats;
  hosts: HostStatus[];
  alerts: Alert[];
  meta: RefreshMeta;
  searchQuery: string;
  sortKey: SortKey;
  sortDir: SortDir;
  loading: boolean;
  error: string | null;
  setSearchQuery: (q: string) => void;
  setSort: (key: SortKey) => void;
  selectUser: (user: User | null) => Promise<void>;
  selectHost: (host: SelectedHost | null) => Promise<void>;
  refreshData: () => Promise<void>;
}

function applyFilterSort(
  users: User[],
  searchQuery: string,
  sortKey: SortKey,
  sortDir: SortDir
): User[] {
  const q = searchQuery.trim().toLowerCase();
  let list = q
    ? users.filter(
        (u) =>
          u.username.toLowerCase().includes(q) ||
          u.vmName.toLowerCase().includes(q) ||
          u.vmIp.toLowerCase().includes(q)
      )
    : [...users];

  list.sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    let cmp = 0;
    if (av instanceof Date && bv instanceof Date) {
      cmp = av.getTime() - bv.getTime();
    } else if (typeof av === 'string' && typeof bv === 'string') {
      cmp = av.localeCompare(bv);
    } else {
      cmp = Number(av) - Number(bv);
    }
    return sortDir === 'asc' ? cmp : -cmp;
  });
  return list;
}

const emptyMeta: RefreshMeta = { lastRefresh: null, refreshing: false, error: null };

export const useMonitorStore = create<MonitorStore>((set, get) => {
  const initialUsers = USE_MOCK ? generateMockUsers() : [];

  return {
    users: initialUsers,
    filteredUsers: initialUsers,
    selectedUser: null,
    userProcesses: [],
    selectedHost: null,
    hostProcesses: [],
    clusterStats: USE_MOCK
      ? getClusterStats(initialUsers)
      : { onlineUsers: 0, totalVMs: 0, totalCpuUsage: 0, totalMemoryUsage: 0 },
    hosts: [],
    alerts: [],
    meta: emptyMeta,
    searchQuery: '',
    sortKey: 'cpuUsage',
    sortDir: 'desc',
    loading: false,
    error: null,

    setSearchQuery: (q: string) => {
      const { users, sortKey, sortDir } = get();
      set({
        searchQuery: q,
        filteredUsers: applyFilterSort(users, q, sortKey, sortDir),
      });
    },

    setSort: (key: SortKey) => {
      const { users, searchQuery, sortKey, sortDir } = get();
      const nextDir: SortDir = sortKey === key && sortDir === 'desc' ? 'asc' : 'desc';
      set({
        sortKey: key,
        sortDir: nextDir,
        filteredUsers: applyFilterSort(users, searchQuery, key, nextDir),
      });
    },

    selectUser: async (user: User | null) => {
      if (!user) {
        set({ selectedUser: null, userProcesses: [] });
        return;
      }
      set({ selectedUser: user, userProcesses: [], selectedHost: null, hostProcesses: [] });
      if (USE_MOCK) {
        set({ userProcesses: generateMockProcesses(user.username) });
        return;
      }
      try {
        const processes = await fetchUserProcesses(user.username, user.vmIp);
        if (get().selectedUser?.id === user.id) {
          set({ userProcesses: processes });
        }
      } catch (err) {
        console.error(err);
        if (get().selectedUser?.id === user.id) {
          set({ userProcesses: [], error: String(err) });
        }
      }
    },

    selectHost: async (host: SelectedHost | null) => {
      if (!host) {
        set({ selectedHost: null, hostProcesses: [] });
        return;
      }
      set({ selectedHost: host, hostProcesses: [], selectedUser: null, userProcesses: [] });
      if (USE_MOCK) {
        set({ hostProcesses: generateMockProcesses('host') });
        return;
      }
      try {
        const processes = await fetchHostProcesses(host.hostname, host.ip);
        if (
          get().selectedHost?.hostname === host.hostname &&
          get().selectedHost?.ip === host.ip
        ) {
          set({ hostProcesses: processes });
        }
      } catch (err) {
        console.error(err);
        if (get().selectedHost?.hostname === host.hostname) {
          set({ hostProcesses: [], error: String(err) });
        }
      }
    },

    refreshData: async () => {
      const { searchQuery, sortKey, sortDir, selectedUser } = get();
      set({ loading: true, error: null });

      if (USE_MOCK) {
        const newUsers = generateMockUsers();
        set({
          users: newUsers,
          filteredUsers: applyFilterSort(newUsers, searchQuery, sortKey, sortDir),
          clusterStats: getClusterStats(newUsers),
          meta: {
            lastRefresh: new Date().toISOString(),
            refreshing: false,
            error: null,
          },
          loading: false,
        });
        return;
      }

      try {
        const before = get().meta.lastRefresh;
        await triggerRefresh(); // non-blocking on server; returns immediately
        // Poll until snapshot timestamp advances or timeout (~3 min)
        const deadline = Date.now() + 180000;
        while (Date.now() < deadline) {
          await new Promise((r) => setTimeout(r, 2000));
          await pollSnapshot();
          const { meta, users } = get();
          if (meta.lastRefresh && meta.lastRefresh !== before && !meta.refreshing) {
            if (selectedUser) {
              const still = users.find((u) => u.id === selectedUser.id);
              if (still) await get().selectUser(still);
            }
            break;
          }
        }
        set({ loading: false });
      } catch (err) {
        console.error(err);
        set({ loading: false, error: String(err) });
      }
    },
  };
});

/** Quiet poll without forcing a full recollect (use cached snapshot). */
export async function pollSnapshot(): Promise<void> {
  if (USE_MOCK) {
    useMonitorStore.getState().refreshData();
    return;
  }
  const state = useMonitorStore.getState();
  const { searchQuery, sortKey, sortDir, meta: prevMeta } = state;
  try {
    const meta = await fetchMeta();
    // Skip full list rewrite when snapshot stamp unchanged (avoids UI jank)
    if (meta.lastRefresh && prevMeta.lastRefresh && meta.lastRefresh === prevMeta.lastRefresh) {
      if (meta.refreshing !== prevMeta.refreshing) {
        useMonitorStore.setState({ meta });
      }
      return;
    }
    const [users, stats, hosts, alerts] = await Promise.all([
      fetchUsers(),
      fetchStats(),
      fetchHosts(),
      fetchAlerts(),
    ]);
    useMonitorStore.setState({
      users,
      filteredUsers: applyFilterSort(users, searchQuery, sortKey, sortDir),
      clusterStats: stats,
      hosts,
      alerts,
      meta,
      error: null,
    });
  } catch (err) {
    useMonitorStore.setState({ error: String(err) });
  }
}