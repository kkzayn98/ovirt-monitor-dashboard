export interface User {
  id: string;
  username: string;
  vmName: string;
  vmIp: string;
  cpuUsage: number;
  memoryUsage: number;
  loginTime: Date;
}

export interface Process {
  pid: string;
  name: string;
  user: string;
  cpuUsage: number;
  memoryUsage: number;
  startTime: Date;
}

export interface ClusterStats {
  onlineUsers: number;
  totalVMs: number;
  totalCpuUsage: number;
  totalMemoryUsage: number;
  reachableHosts?: number;
  failedHosts?: number;
  lastRefresh?: Date;
}