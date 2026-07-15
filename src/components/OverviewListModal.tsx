import React, { useMemo, useState } from 'react';
import { X, Users, Server, Search, Cpu, Activity } from 'lucide-react';
import { useMonitorStore } from '../store';
import { User } from '../types';
import { HostStatus } from '../services/api';

export type OverviewListKind = 'users' | 'vms' | null;

interface Props {
  kind: OverviewListKind;
  onClose: () => void;
}

const getBar = (value: number) => {
  if (value > 80) return 'bg-red-500';
  if (value > 60) return 'bg-yellow-500';
  return 'bg-green-500';
};

const OverviewListModal: React.FC<Props> = ({ kind, onClose }) => {
  const users = useMonitorStore((s) => s.users);
  const hosts = useMonitorStore((s) => s.hosts);
  const selectUser = useMonitorStore((s) => s.selectUser);
  const selectHost = useMonitorStore((s) => s.selectHost);
  const [query, setQuery] = useState('');

  const vms = useMemo(
    () =>
      hosts
        .filter((h) => h.status === 'ok')
        .slice()
        .sort((a, b) => (a.hostname || a.ip).localeCompare(b.hostname || b.ip)),
    [hosts]
  );

  const filteredUsers = useMemo(() => {
    const q = query.trim().toLowerCase();
    // Dedupe by username: one person may appear on many VMs
    const byName = new Map<
      string,
      { user: User; hosts: string[]; peakCpu: number; peakMem: number }
    >();
    for (const u of users) {
      const prev = byName.get(u.username);
      if (!prev) {
        byName.set(u.username, {
          user: u,
          hosts: [u.vmName],
          peakCpu: u.cpuUsage,
          peakMem: u.memoryUsage,
        });
        continue;
      }
      if (!prev.hosts.includes(u.vmName)) prev.hosts.push(u.vmName);
      prev.peakCpu = Math.max(prev.peakCpu, u.cpuUsage);
      prev.peakMem = Math.max(prev.peakMem, u.memoryUsage);
      if (u.cpuUsage + u.memoryUsage > prev.user.cpuUsage + prev.user.memoryUsage) {
        prev.user = u;
      }
    }
    let list = Array.from(byName.values());
    if (q) {
      list = list.filter(
        (row) =>
          row.user.username.toLowerCase().includes(q) ||
          row.hosts.some((h) => h.toLowerCase().includes(q)) ||
          row.user.vmIp.toLowerCase().includes(q)
      );
    }
    list.sort((a, b) => b.peakCpu + b.peakMem - (a.peakCpu + a.peakMem));
    return list;
  }, [users, query]);

  const filteredVms = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return vms;
    return vms.filter(
      (h) =>
        (h.hostname || '').toLowerCase().includes(q) ||
        h.ip.toLowerCase().includes(q) ||
        (h.detail || '').toLowerCase().includes(q)
    );
  }, [vms, query]);

  if (!kind) return null;

  const title = kind === 'users' ? '在线用户列表' : '可达 VM 列表';
  const Icon = kind === 'users' ? Users : Server;
  const count = kind === 'users' ? filteredUsers.length : filteredVms.length;

  const onPickUser = (user: User) => {
    onClose();
    void selectUser(user);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full sm:max-w-3xl max-h-[92vh] sm:max-h-[85vh] bg-slate-900 rounded-t-2xl sm:rounded-2xl border border-slate-700 shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-slate-700">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 rounded-lg bg-blue-500/10 shrink-0">
              <Icon className="w-5 h-5 text-blue-400" />
            </div>
            <div className="min-w-0">
              <h2 className="text-base sm:text-lg font-bold text-slate-200 truncate">{title}</h2>
              <p className="text-xs text-slate-500 font-mono">
                {kind === 'users' ? `${count} 人（按用户名去重）` : `${count} 项`}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-4 sm:px-5 py-3 border-b border-slate-800">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={kind === 'users' ? '搜索用户 / 主机名 / IP' : '搜索主机名 / IP'}
              className="w-full pl-9 pr-3 py-2.5 sm:py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        <div className="overflow-y-auto scrollbar-thin flex-1 p-3 sm:p-4 space-y-2">
          {kind === 'users' &&
            (filteredUsers.length === 0 ? (
              <p className="text-center text-slate-500 py-10">暂无在线用户</p>
            ) : (
              filteredUsers.map((row) => (
                <button
                  key={row.user.username}
                  type="button"
                  onClick={() => onPickUser(row.user)}
                  className="w-full text-left bg-slate-800/50 hover:bg-slate-800 border border-slate-700/50 hover:border-blue-500/40 rounded-xl px-3.5 sm:px-4 py-3 transition-colors"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-mono font-medium text-slate-200 truncate">
                        {row.user.username}
                      </div>
                      <div className="text-xs text-slate-500 font-mono truncate mt-0.5">
                        {row.hosts.length > 1
                          ? `${row.hosts.length} 台主机：${row.hosts.join('、')}`
                          : `${row.hosts[0]} · ${row.user.vmIp}`}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 sm:gap-4 shrink-0 text-xs font-mono text-slate-400">
                      <span className="inline-flex items-center gap-1" title="各主机峰值（占该主机比例）">
                        <Cpu className="w-3.5 h-3.5" />
                        {row.peakCpu}%
                      </span>
                      <span className="inline-flex items-center gap-1" title="各主机峰值（占该主机比例）">
                        <Activity className="w-3.5 h-3.5" />
                        {row.peakMem}%
                      </span>
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${getBar(row.peakCpu)}`}
                        style={{ width: `${Math.min(row.peakCpu, 100)}%` }}
                      />
                    </div>
                    <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${getBar(row.peakMem)}`}
                        style={{ width: `${Math.min(row.peakMem, 100)}%` }}
                      />
                    </div>
                  </div>
                </button>
              ))
            ))}

          {kind === 'vms' &&
            (filteredVms.length === 0 ? (
              <p className="text-center text-slate-500 py-10">暂无可达 VM</p>
            ) : (
              filteredVms.map((vm: HostStatus) => (
                <button
                  key={`${vm.hostname || vm.ip}-${vm.ip}`}
                  type="button"
                  onClick={() => {
                    onClose();
                    void selectHost({
                      hostname: vm.hostname || vm.ip,
                      ip: vm.ip,
                    });
                  }}
                  className="w-full text-left bg-slate-800/50 hover:bg-slate-800 border border-slate-700/50 hover:border-blue-500/40 rounded-xl px-3.5 sm:px-4 py-3 transition-colors"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-mono font-medium text-slate-200 truncate">
                        {vm.hostname || vm.ip}
                      </div>
                      <div className="text-xs text-slate-500 font-mono mt-0.5 truncate">
                        {vm.ip}
                        {vm.detail && vm.detail !== 'ok' && (
                          <span className="text-slate-600"> · {vm.detail}</span>
                        )}
                      </div>
                    </div>
                    <div className="shrink-0 text-xs font-mono text-slate-400 text-right">
                      在线用户 {vm.onlineUsers}
                      <div className="text-[10px] text-blue-400/80 mt-0.5">查看 Top 5</div>
                    </div>
                  </div>
                </button>
              ))
            ))}
        </div>

        <div className="p-3 sm:p-4 border-t border-slate-700">
          <button
            type="button"
            onClick={onClose}
            className="w-full py-2.5 sm:py-2 px-4 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors font-medium"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
};

export default OverviewListModal;