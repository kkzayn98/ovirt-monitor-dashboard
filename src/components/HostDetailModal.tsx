import React from 'react';
import { X, Cpu, Activity, Terminal, Server, User } from 'lucide-react';
import { useMonitorStore } from '../store';

const formatProcessTime = (date: Date): string => {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / (1000 * 60));
  if (minutes < 60) {
    return `${minutes}分钟`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}小时${remainingMinutes}分钟`;
};

const HostDetailModal: React.FC = () => {
  const selectedHost = useMonitorStore((s) => s.selectedHost);
  const hostProcesses = useMonitorStore((s) => s.hostProcesses);
  const hosts = useMonitorStore((s) => s.hosts);
  const selectHost = useMonitorStore((s) => s.selectHost);

  if (!selectedHost) return null;

  const info = hosts.find(
    (h) =>
      h.status === 'ok' &&
      ((h.hostname || '') === selectedHost.hostname || h.ip === selectedHost.ip)
  );

  const getStatusColor = (value: number): string => {
    if (value > 80) return 'bg-red-500';
    if (value > 60) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/60 backdrop-blur-sm"
      onClick={() => selectHost(null)}
    >
      <div
        className="relative w-full sm:max-w-4xl max-h-[95vh] sm:max-h-[90vh] bg-slate-900 rounded-t-2xl sm:rounded-2xl border border-slate-700 shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start sm:items-center justify-between gap-3 p-4 sm:p-6 border-b border-slate-700 bg-gradient-to-r from-blue-900/20 to-cyan-900/20">
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            <div className="w-11 h-11 sm:w-14 sm:h-14 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center shrink-0">
              <Server className="w-6 h-6 sm:w-7 sm:h-7 text-white" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg sm:text-2xl font-bold text-slate-200 font-mono truncate">
                {selectedHost.hostname}
              </h2>
              <p className="text-slate-400 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
                <span className="font-mono">{selectedHost.ip}</span>
                {info && (
                  <span className="text-slate-500">· 在线用户 {info.onlineUsers}</span>
                )}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => selectHost(null)}
            className="p-2 hover:bg-slate-800 rounded-lg transition-colors text-slate-400 hover:text-white shrink-0"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="p-4 sm:p-6 overflow-y-auto scrollbar-thin flex-1" style={{ maxHeight: 'calc(95vh - 120px)' }}>
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <Terminal className="w-5 h-5 text-blue-400 shrink-0" />
            <h3 className="text-base sm:text-lg font-bold text-slate-200">主机资源占用 Top 5 进程</h3>
            <span className="text-xs text-slate-500 w-full sm:w-auto">CPU/内存为占主机整体比例</span>
          </div>

          {hostProcesses.length === 0 ? (
            <p className="text-center text-slate-500 py-12">暂无进程数据（采集中或主机无活跃进程）</p>
          ) : (
            <div className="space-y-3">
              {hostProcesses.map((process, index) => (
                <div
                  key={`${process.pid}-${index}`}
                  className="bg-slate-800/50 rounded-xl p-3.5 sm:p-4 border border-slate-700/50 hover:border-blue-500/50 transition-colors"
                >
                  <div className="flex items-start sm:items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                          index === 0
                            ? 'bg-yellow-500/20 text-yellow-400'
                            : index === 1
                              ? 'bg-gray-400/20 text-gray-400'
                              : index === 2
                                ? 'bg-orange-600/20 text-orange-400'
                                : 'bg-blue-500/20 text-blue-400'
                        }`}
                      >
                        <span className="font-bold text-sm">#{index + 1}</span>
                      </div>
                      <div className="min-w-0">
                        <div className="font-mono font-semibold text-slate-200 truncate">{process.name}</div>
                        <div className="text-xs text-slate-500 font-mono flex flex-wrap items-center gap-x-2 gap-y-0.5">
                          <span>PID: {process.pid}</span>
                          <span className="inline-flex items-center gap-1">
                            <User className="w-3 h-3" />
                            {process.user}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-xs text-slate-500">运行时间</div>
                      <div className="text-sm font-mono text-slate-400">
                        {formatProcessTime(process.startTime)}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 sm:gap-4">
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-slate-400 flex items-center gap-1">
                          <Cpu className="w-3 h-3" />
                          CPU
                        </span>
                        <span className="text-sm font-mono font-medium text-slate-300">
                          {process.cpuUsage}%
                        </span>
                      </div>
                      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${getStatusColor(process.cpuUsage)} transition-all duration-300`}
                          style={{ width: `${Math.min(process.cpuUsage, 100)}%` }}
                        />
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-slate-400 flex items-center gap-1">
                          <Activity className="w-3 h-3" />
                          内存
                        </span>
                        <span className="text-sm font-mono font-medium text-slate-300">
                          {process.memoryUsage}%
                        </span>
                      </div>
                      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${getStatusColor(process.memoryUsage)} transition-all duration-300`}
                          style={{ width: `${Math.min(process.memoryUsage, 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="p-3 sm:p-4 border-t border-slate-700 bg-slate-900/50">
          <button
            type="button"
            onClick={() => selectHost(null)}
            className="w-full py-2.5 sm:py-2 px-4 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors font-medium"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
};

export default HostDetailModal;