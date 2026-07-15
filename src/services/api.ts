import { ClusterStats, Process, User } from '../types';

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export interface HostStatus {
  ip: string;
  hostname?: string | null;
  status: 'ok' | 'unreachable' | 'auth_failed' | 'error';
  detail: string;
  onlineUsers: number;
  hostCpuUsage?: number;
  hostMemoryUsage?: number;
}

export interface Alert {
  id: string;
  level: 'warning' | 'critical';
  kind: 'host_cpu' | 'host_mem' | 'host_lost' | 'user_cpu' | 'user_mem';
  hostname: string;
  ip: string;
  message: string;
  suspectedUsers: string[];
  value: number;
  threshold: number;
  createdAt: string;
}

export interface RefreshMeta {
  lastRefresh: string | null;
  refreshing: boolean;
  error: string | null;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function reviveUser(u: User): User {
  return { ...u, loginTime: new Date(u.loginTime) };
}

function reviveProcess(p: Process): Process {
  return { ...p, startTime: new Date(p.startTime) };
}

export async function fetchUsers(): Promise<User[]> {
  const data = await getJson<User[]>('/api/users');
  return data.map(reviveUser);
}

export async function fetchStats(): Promise<ClusterStats> {
  const data = await getJson<ClusterStats>('/api/stats');
  return {
    ...data,
    lastRefresh: data.lastRefresh ? new Date(data.lastRefresh as unknown as string) : undefined,
  };
}

export async function fetchUserProcesses(username: string, vmIp: string): Promise<Process[]> {
  const qs = new URLSearchParams({ vmIp });
  const data = await getJson<Process[]>(`/api/users/${encodeURIComponent(username)}/processes?${qs}`);
  return data.map(reviveProcess);
}

export async function fetchHostProcesses(hostname: string, vmIp?: string): Promise<Process[]> {
  const qs = vmIp ? `?${new URLSearchParams({ vmIp })}` : '';
  const data = await getJson<Process[]>(
    `/api/hosts/${encodeURIComponent(hostname)}/processes${qs}`
  );
  return data.map(reviveProcess);
}

export async function fetchHosts(): Promise<HostStatus[]> {
  return getJson('/api/hosts');
}

export async function fetchAlerts(): Promise<Alert[]> {
  return getJson('/api/alerts');
}

export async function fetchMeta(): Promise<RefreshMeta> {
  return getJson('/api/meta');
}

export async function triggerRefresh(): Promise<void> {
  const res = await fetch('/api/refresh', { method: 'POST' });
  if (!res.ok) {
    throw new Error(`refresh failed: ${res.status}`);
  }
}

export { USE_MOCK };