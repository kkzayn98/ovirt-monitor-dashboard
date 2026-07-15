import React from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import ClusterOverview from './components/ClusterOverview';
import AlertBanner from './components/AlertBanner';
import UserList from './components/UserList';
import UserDetailModal from './components/UserDetailModal';
import HostDetailModal from './components/HostDetailModal';
import { useMonitorStore } from './store';
import { useAutoRefresh } from './hooks/useAutoRefresh';
import { USE_MOCK } from './services/api';

const App: React.FC = () => {
  const refreshData = useMonitorStore((state) => state.refreshData);
  const loading = useMonitorStore((state) => state.loading);
  const meta = useMonitorStore((state) => state.meta);
  const error = useMonitorStore((state) => state.error);
  const stats = useMonitorStore((state) => state.clusterStats);
  const alerts = useMonitorStore((state) => state.alerts);

  useAutoRefresh(30000);

  const lastRefresh =
    stats.lastRefresh ||
    (meta.lastRefresh ? new Date(meta.lastRefresh) : null);

  const criticalCount = alerts.filter((a) => a.level === 'critical').length;

  return (
    <div className="min-h-screen">
      <header className="bg-slate-900/80 backdrop-blur-md border-b border-slate-700/50 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-3 sm:px-6 py-3 sm:py-4">
          <div className="flex items-center justify-between gap-2 sm:gap-4 flex-wrap">
            <div className="flex items-center gap-2.5 sm:gap-4 min-w-0">
              <div className="p-2 sm:p-3 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg sm:rounded-xl shrink-0">
                <Activity className="w-6 h-6 sm:w-8 sm:h-8 text-white" />
              </div>
              <div className="min-w-0">
                <h1 className="text-lg sm:text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent truncate">
                  Raina集群监控大屏
                </h1>
                <p className="hidden sm:block text-sm text-slate-400">
                  实时监控 oVirt VM 上用户活动与资源占用
                  {USE_MOCK ? ' · Mock 模式' : ''}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 sm:gap-4 ml-auto">
              {alerts.length > 0 && (
                <div
                  className={`text-[10px] sm:text-xs font-mono px-1.5 sm:px-2 py-1 rounded-lg border ${
                    criticalCount
                      ? 'text-red-300 border-red-500/40 bg-red-500/10'
                      : 'text-amber-300 border-amber-500/40 bg-amber-500/10'
                  }`}
                >
                  预警 {alerts.length}
                  {criticalCount ? ` · 严重 ${criticalCount}` : ''}
                </div>
              )}
              <div className="hidden sm:block text-right text-xs text-slate-500 font-mono">
                <div>
                  上次刷新{' '}
                  {lastRefresh
                    ? lastRefresh.toLocaleTimeString('zh-CN', { hour12: false })
                    : '—'}
                </div>
                {loading && <div className="text-blue-400">采集中…</div>}
              </div>
              <button
                onClick={() => refreshData()}
                disabled={loading}
                className="flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors text-sm"
                aria-label="刷新数据"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                <span className="sm:hidden">刷新</span>
                <span className="hidden sm:inline">刷新数据</span>
              </button>
            </div>
          </div>
          {loading && (
            <div className="sm:hidden mt-2 text-xs text-blue-400 font-mono">采集中…</div>
          )}
          {error && (
            <div className="mt-3 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 break-words">
              {error}
            </div>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-3 sm:px-6 py-4 sm:py-8">
        <AlertBanner />
        <div className="mb-5 sm:mb-8">
          <ClusterOverview />
        </div>
        <div>
          <UserList />
        </div>
      </main>

      <UserDetailModal />
      <HostDetailModal />

      <footer className="border-t border-slate-700/50 mt-8 sm:mt-12 py-4 sm:py-6">
        <div className="max-w-7xl mx-auto px-3 sm:px-6">
          <p className="text-center text-xs sm:text-sm text-slate-500 px-2">
            Raina 集群监控系统 · 资源预警写入 server/logs/alerts.log · 可配置 webhook 通知 IT
          </p>
        </div>
      </footer>
    </div>
  );
};

export default App;