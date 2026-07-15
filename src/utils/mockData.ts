import { User, Process, ClusterStats } from '../types';

export const generateMockUsers = (): User[] => {
  const usernames = ['zhangsan', 'lisi', 'wangwu', 'zhaoliu', 'qianqi', 'sunba', 'zhoujiu', 'wushi'];
  const vmNames = ['EDA-Worker-01', 'EDA-Worker-02', 'EDA-Worker-03', 'EDA-Worker-04', 'EDA-Worker-05', 'EDA-Worker-06', 'EDA-Worker-07', 'EDA-Worker-08'];
  
  return usernames.map((username, index) => ({
    id: `user-${index + 1}`,
    username,
    vmName: vmNames[index],
    vmIp: `192.168.15.${100 + index}`,
    cpuUsage: Math.floor(Math.random() * 100),
    memoryUsage: Math.floor(Math.random() * 100),
    loginTime: new Date(Date.now() - Math.floor(Math.random() * 86400000))
  }));
};

export const generateMockProcesses = (username: string): Process[] => {
  const processNames = ['vcs', 'verilog', 'synopsys', 'cadence', 'questa', 'vivado', 'modelsim', 'xcelium'];
  const processes: Process[] = [];
  
  for (let i = 0; i < 5; i++) {
    processes.push({
      pid: `${10000 + Math.floor(Math.random() * 90000)}`,
      name: processNames[i % processNames.length],
      user: username,
      cpuUsage: Math.floor(Math.random() * 100),
      memoryUsage: Math.floor(Math.random() * 100),
      startTime: new Date(Date.now() - Math.floor(Math.random() * 3600000))
    });
  }
  
  return processes.sort((a, b) => b.cpuUsage + b.memoryUsage - a.cpuUsage - a.memoryUsage);
};

export const getClusterStats = (users: User[]): ClusterStats => {
  const totalCpuUsage = Math.floor(users.reduce((sum, user) => sum + user.cpuUsage, 0) / users.length);
  const totalMemoryUsage = Math.floor(users.reduce((sum, user) => sum + user.memoryUsage, 0) / users.length);
  
  return {
    onlineUsers: users.length,
    totalVMs: 24,
    totalCpuUsage,
    totalMemoryUsage
  };
};
