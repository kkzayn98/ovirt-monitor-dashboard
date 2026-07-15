import React from 'react';
import { User, Clock, Cpu, Activity, Search, ArrowUpDown } from 'lucide-react';
import { SortKey, useMonitorStore } from '../store';

const formatLoginTime = (date: Date): string => {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  if (hours > 0) {
    return `${hours}小时${minutes}分钟`;
  }
  return `${minutes}分钟`;
};

const getStatusColor = (value: number): string => {
  if (value > 80) return 'bg-red-500';
  if (value > 60) return 'bg-yellow-500';
  return 'bg-green-500';
};

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'username', label: '用户名' },
  { key: 'cpuUsage', label: 'CPU' },
  { key: 'memoryUsage', label: '内存' },
  { key: 'loginTime', label: '在线时长' },
];

const SortableTh: React.FC<{
  label: string;
  sortKey: SortKey;
  hint?: string;
}> = ({ label, sortKey, hint }) => {
  const current = useMonitorStore((s) => s.sortKey);
  const dir = useMonitorStore((s) => s.sortDir);
  const setSort = useMonitorStore((s) => s.setSort);
  const active = current === sortKey;

  return (
    <th className="px-6 py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
      <button
        type="button"
        onClick={() => setSort(sortKey)}
        className="inline-flex flex-col items-start gap-0.5 hover:text-slate-200 transition-colors"
      >
        <span className="inline-flex items-center gap-1">
          {label}
          <ArrowUpDown className={`w-3.5 h-3.5 ${active ? 'text-blue-400' : 'text-slate-600'}`} />
          {active && <span className="text-[10px] text-blue-400">{dir === 'asc' ? '↑' : '↓'}</span>}
        </span>
        {hint && (
          <span className="normal-case font-normal text-[10px] text-slate-500 tracking-normal">
            {hint}
          </span>
        )}
      </button>
    </th>
  );
};

const UsageBar: React.FC<{ value: number; icon: React.ReactNode }> = ({ value, icon }) => (
  <div className="flex items-center gap-2 min-w-0">
    {icon}
    <div className="flex-1 min-w-0">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-mono text-slate-300">{value}%</span>
      </div>
      <div className="w-full max-w-[6rem] h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${getStatusColor(value)} transition-all duration-300`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
    </div>
  </div>
);

const UserList: React.FC = () => {
  const users = useMonitorStore((state) => state.filteredUsers);
  const allCount = useMonitorStore((state) => state.users.length);
  const selectUser = useMonitorStore((state) => state.selectUser);
  const selectHost = useMonitorStore((state) => state.selectHost);
  const selectedUser = useMonitorStore((state) => state.selectedUser);
  const searchQuery = useMonitorStore((state) => state.searchQuery);
  const setSearchQuery = useMonitorStore((state) => state.setSearchQuery);
  const sortKey = useMonitorStore((s) => s.sortKey);
  const sortDir = useMonitorStore((s) => s.sortDir);
  const setSort = useMonitorStore((s) => s.setSort);

  return (
    <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="p-4 sm:p-6 border-b border-slate-700/50 flex flex-col gap-3 sm:gap-4 sm:flex-row sm:items-center justify-between">
        <h2 className="text-lg sm:text-xl font-bold text-slate-200 flex items-center gap-2">
          <User className="w-5 h-5 text-blue-400 shrink-0" />
          在线用户列表
          <span className="text-sm font-normal text-slate-500">
            ({users.length}{users.length !== allCount ? ` / ${allCount}` : ''})
          </span>
        </h2>
        <div className="flex flex-col gap-2 w-full sm:w-auto sm:items-center sm:flex-row">
          <div className="relative w-full sm:w-72">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索用户 / VM / IP"
              className="w-full pl-9 pr-3 py-2.5 sm:py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
          {/* Mobile sort control — desktop uses table headers */}
          <div className="flex md:hidden items-center gap-2">
            <select
              value={sortKey}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="flex-1 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-200 px-3 py-2.5 focus:outline-none focus:border-blue-500"
              aria-label="排序字段"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  按{o.label}排序
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setSort(sortKey)}
              className="shrink-0 px-3 py-2.5 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-300"
              aria-label="切换升降序"
            >
              {sortDir === 'asc' ? '升序' : '降序'}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden divide-y divide-slate-700/50">
        {users.length === 0 ? (
          <div className="px-4 py-12 text-center text-slate-500">暂无在线用户</div>
        ) : (
          users.map((user) => (
            <div
              key={user.id}
              role="button"
              tabIndex={0}
              onClick={() => selectUser(user)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  selectUser(user);
                }
              }}
              className={`p-4 active:bg-slate-800/80 transition-colors ${
                selectedUser?.id === user.id ? 'bg-blue-500/15 border-l-4 border-l-blue-500' : ''
              }`}
            >
              <div className="flex items-start gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shrink-0">
                  <span className="text-white font-bold text-sm">
                    {user.username.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-mono font-medium text-slate-200 truncate">{user.username}</div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void selectHost({ hostname: user.vmName, ip: user.vmIp });
                    }}
                    className="text-left mt-0.5"
                  >
                    <div className="font-mono text-sm text-blue-400 truncate">{user.vmName}</div>
                    <div className="font-mono text-xs text-slate-500">{user.vmIp}</div>
                  </button>
                </div>
                <div className="flex items-center gap-1 text-xs text-slate-400 shrink-0">
                  <Clock className="w-3.5 h-3.5" />
                  <span className="font-mono">{formatLoginTime(user.loginTime)}</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <UsageBar value={user.cpuUsage} icon={<Cpu className="w-4 h-4 text-slate-400 shrink-0" />} />
                <UsageBar
                  value={user.memoryUsage}
                  icon={<Activity className="w-4 h-4 text-slate-400 shrink-0" />}
                />
              </div>
              <p className="mt-2 text-[10px] text-slate-500">点卡片看用户进程 · 点主机名看主机 Top 5</p>
            </div>
          ))
        )}
      </div>

      {/* Desktop table — unchanged layout */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead className="bg-slate-800/50">
            <tr>
              <SortableTh label="用户名" sortKey="username" />
              <th className="px-6 py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                主机名
              </th>
              <SortableTh label="CPU" sortKey="cpuUsage" hint="占主机整体比例" />
              <SortableTh label="内存" sortKey="memoryUsage" hint="占主机整体比例" />
              <SortableTh label="在线时长" sortKey="loginTime" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {users.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-slate-500">
                  暂无在线用户
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr
                  key={user.id}
                  onClick={() => selectUser(user)}
                  className={`cursor-pointer transition-all duration-200 hover:bg-slate-800/70 ${
                    selectedUser?.id === user.id ? 'bg-blue-500/20 border-l-4 border-l-blue-500' : ''
                  }`}
                >
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                        <span className="text-white font-bold text-sm">
                          {user.username.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <div className="font-mono font-medium text-slate-200">{user.username}</div>
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                          在线
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void selectHost({ hostname: user.vmName, ip: user.vmIp });
                      }}
                      className="text-left group"
                      title="查看该主机 Top 5 进程"
                    >
                      <div className="font-mono text-slate-200 font-medium group-hover:text-blue-400 transition-colors underline-offset-2 group-hover:underline">
                        {user.vmName}
                      </div>
                      <div className="font-mono text-xs text-slate-500 mt-0.5">{user.vmIp}</div>
                    </button>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Cpu className="w-4 h-4 text-slate-400" />
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-mono text-slate-300">{user.cpuUsage}%</span>
                        </div>
                        <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${getStatusColor(user.cpuUsage)} transition-all duration-300`}
                            style={{ width: `${Math.min(user.cpuUsage, 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Activity className="w-4 h-4 text-slate-400" />
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-mono text-slate-300">{user.memoryUsage}%</span>
                        </div>
                        <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${getStatusColor(user.memoryUsage)} transition-all duration-300`}
                            style={{ width: `${Math.min(user.memoryUsage, 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2 text-slate-300">
                      <Clock className="w-4 h-4 text-slate-400" />
                      <span className="font-mono text-sm">{formatLoginTime(user.loginTime)}</span>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default UserList;
