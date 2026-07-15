import React, { useState } from 'react';
import { Users, Server, Cpu, Activity } from 'lucide-react';
import { useMonitorStore } from '../store';
import OverviewListModal, { OverviewListKind } from './OverviewListModal';

const ClusterOverview: React.FC = () => {
  const clusterStats = useMonitorStore((state) => state.clusterStats);
  const [listKind, setListKind] = useState<OverviewListKind>(null);

  const stats = [
    {
      key: 'users' as const,
      label: '在线用户',
      value: clusterStats.onlineUsers,
      icon: Users,
      color: 'text-green-400',
      bgColor: 'bg-green-400/10',
      borderColor: 'border-green-400/30',
      clickable: true,
      hint: '点击查看列表',
    },
    {
      key: 'vms' as const,
      label: '可达 VM',
      value: clusterStats.totalVMs,
      icon: Server,
      color: 'text-blue-400',
      bgColor: 'bg-blue-400/10',
      borderColor: 'border-blue-400/30',
      clickable: true,
      hint: '点击查看列表',
    },
    {
      key: 'cpu' as const,
      label: 'CPU使用率',
      value: `${clusterStats.totalCpuUsage}%`,
      icon: Cpu,
      color:
        clusterStats.totalCpuUsage > 80
          ? 'text-red-400'
          : clusterStats.totalCpuUsage > 60
            ? 'text-yellow-400'
            : 'text-green-400',
      bgColor:
        clusterStats.totalCpuUsage > 80
          ? 'bg-red-400/10'
          : clusterStats.totalCpuUsage > 60
            ? 'bg-yellow-400/10'
            : 'bg-green-400/10',
      borderColor:
        clusterStats.totalCpuUsage > 80
          ? 'border-red-400/30'
          : clusterStats.totalCpuUsage > 60
            ? 'border-yellow-400/30'
            : 'border-green-400/30',
      clickable: false,
      hint: '',
    },
    {
      key: 'mem' as const,
      label: '内存使用率',
      value: `${clusterStats.totalMemoryUsage}%`,
      icon: Activity,
      color:
        clusterStats.totalMemoryUsage > 80
          ? 'text-red-400'
          : clusterStats.totalMemoryUsage > 60
            ? 'text-yellow-400'
            : 'text-green-400',
      bgColor:
        clusterStats.totalMemoryUsage > 80
          ? 'bg-red-400/10'
          : clusterStats.totalMemoryUsage > 60
            ? 'bg-yellow-400/10'
            : 'bg-green-400/10',
      borderColor:
        clusterStats.totalMemoryUsage > 80
          ? 'border-red-400/30'
          : clusterStats.totalMemoryUsage > 60
            ? 'border-yellow-400/30'
            : 'border-green-400/30',
      clickable: false,
      hint: '',
    },
  ];

  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
        {stats.map((stat) => {
          const Icon = stat.icon;
          const clickable = stat.clickable;
          return (
            <div
              key={stat.key}
              role={clickable ? 'button' : undefined}
              tabIndex={clickable ? 0 : undefined}
              onClick={
                clickable
                  ? () => setListKind(stat.key === 'users' ? 'users' : 'vms')
                  : undefined
              }
              onKeyDown={
                clickable
                  ? (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setListKind(stat.key === 'users' ? 'users' : 'vms');
                      }
                    }
                  : undefined
              }
              className={`relative overflow-hidden rounded-xl border ${stat.borderColor} ${stat.bgColor} backdrop-blur-sm p-3.5 sm:p-6 transition-all duration-300 ${
                clickable
                  ? 'cursor-pointer hover:scale-[1.02] hover:border-opacity-80 focus:outline-none focus:ring-2 focus:ring-blue-500/40 active:scale-[0.98]'
                  : 'hover:scale-[1.02]'
              }`}
            >
              <div className="absolute top-0 right-0 w-24 sm:w-32 h-24 sm:h-32 bg-gradient-to-br from-white/5 to-transparent rounded-full -translate-y-1/2 translate-x-1/2" />
              <div className="relative z-10">
                <div className="flex items-center justify-between mb-2 sm:mb-4">
                  <div className={`p-2 sm:p-3 rounded-lg ${stat.bgColor}`}>
                    <Icon className={`w-5 h-5 sm:w-6 sm:h-6 ${stat.color}`} />
                  </div>
                  {clickable && (
                    <span className="hidden sm:inline text-[10px] text-slate-500">{stat.hint}</span>
                  )}
                </div>
                <div>
                  <p className="text-xs sm:text-sm text-slate-400 mb-0.5 sm:mb-1">{stat.label}</p>
                  <p className={`text-xl sm:text-3xl font-bold font-mono ${stat.color}`}>{stat.value}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <OverviewListModal kind={listKind} onClose={() => setListKind(null)} />
    </>
  );
};

export default ClusterOverview;