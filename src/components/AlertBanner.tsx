import React from 'react';
import { AlertTriangle, Bell, Server } from 'lucide-react';
import { useMonitorStore } from '../store';
import { Alert } from '../services/api';

const AlertBanner: React.FC = () => {
  const alerts = useMonitorStore((s) => s.alerts);
  const selectHost = useMonitorStore((s) => s.selectHost);

  if (!alerts.length) return null;

  const critical = alerts.filter((a) => a.level === 'critical');
  const warning = alerts.filter((a) => a.level === 'warning');
  const top = [...critical, ...warning].slice(0, 8);

  const onOpen = (a: Alert) => {
    void selectHost({ hostname: a.hostname, ip: a.ip });
  };

  return (
    <div className="mb-5 sm:mb-8 space-y-3">
      <div
        className={`rounded-xl border px-3 sm:px-4 py-3 ${
          critical.length
            ? 'border-red-500/40 bg-red-500/10'
            : 'border-amber-500/40 bg-amber-500/10'
        }`}
      >
        <div className="flex items-start gap-3">
          <Bell
            className={`w-5 h-5 mt-0.5 shrink-0 ${
              critical.length ? 'text-red-400' : 'text-amber-400'
            }`}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <h2 className="text-sm font-bold text-slate-100">资源预警</h2>
              {critical.length > 0 && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 font-mono">
                  严重 {critical.length}
                </span>
              )}
              {warning.length > 0 && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono">
                  警告 {warning.length}
                </span>
              )}
              <span className="text-[10px] text-slate-500">
                请 IT 根据「建议联系用户」提醒对方释放资源，避免 OOM / SSH 假死
              </span>
            </div>

            <div className="space-y-2">
              {top.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => onOpen(a)}
                  className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
                    a.level === 'critical'
                      ? 'border-red-500/30 bg-slate-900/40 hover:border-red-400/50'
                      : 'border-amber-500/30 bg-slate-900/40 hover:border-amber-400/50'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <AlertTriangle
                      className={`w-4 h-4 mt-0.5 shrink-0 ${
                        a.level === 'critical' ? 'text-red-400' : 'text-amber-400'
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-slate-200 leading-snug">{a.message}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500 font-mono">
                        <span className="inline-flex items-center gap-1">
                          <Server className="w-3 h-3" />
                          {a.hostname} · {a.ip}
                        </span>
                        {a.suspectedUsers.length > 0 && (
                          <span className="text-slate-400">
                            建议联系：{a.suspectedUsers.join('、')}
                          </span>
                        )}
                        <span className="text-blue-400/80">点击查看主机 Top 5</span>
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>

            {alerts.length > top.length && (
              <p className="mt-2 text-[11px] text-slate-500">
                另有 {alerts.length - top.length} 条，详见 server/logs/alerts.log
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AlertBanner;