/**
 * CompactExecutiveSummary.tsx
 * 
 * Consolidates AWR Intelligence Engine output into:
 * - Executive summary metrics (KPIs)
 * - Tabbed analysis areas (Load, Wait Events, SQL, Efficiency)
 * - Crisp, professional layout with proper typography
 * - Reduced vertical scrolling, all key data visible at once
 */

import { useState } from 'react';
import { DeltaBadge } from './DeltaBadge';
import { formatNumber, formatDuration, formatPct } from '../utils/formatters';

export interface ExecutiveSummaryProps {
  summary: any;
  loadProfileDelta: any[];
  waitEvents: any;
  sqlRegressions: any[];
  instanceEfficiency: any;
  addmFindings: any[];
  recommendations: any[];
}

export default function CompactExecutiveSummary({
  summary,
  loadProfileDelta = [],
  waitEvents = {},
  sqlRegressions = [],
  instanceEfficiency = {},
  addmFindings = [],
  recommendations = [],
}: ExecutiveSummaryProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'metrics' | 'waits' | 'sql' | 'efficiency'>('overview');

  if (!summary) return null;

  // Helper: Get top N items by absolute value
  const topMetrics = [...loadProfileDelta]
    .sort((a, b) => Math.abs(b.change_pct ?? 0) - Math.abs(a.change_pct ?? 0))
    .slice(0, 5);

  // Helper: Severity badge
  const severityBadge = (severity: string) => {
    const styles: Record<string, string> = {
      critical: 'bg-red-500/20 text-red-300 border-red-500/40',
      warning: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
      good: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    };
    return styles[severity] || styles.good;
  };

  return (
    <div className="card space-y-6">
      {/* ═══════════════════════════════════════════
          HEADER: KPI Summary (Always Visible)
          ═══════════════════════════════════════════ */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-text-primary tracking-tight">Performance Analysis</h2>
          <span className={`text-sm font-mono font-bold px-2 py-1 rounded ${
            (summary.db_time_delta_pct ?? 0) > 20 ? 'text-red-400' :
            (summary.db_time_delta_pct ?? 0) > 5 ? 'text-amber-400' :
            'text-emerald-400'
          }`}>
            {(summary.db_time_delta_pct ?? 0) > 0 ? '▲' : '▼'} {Math.abs(summary.db_time_delta_pct ?? 0).toFixed(1)}% DB Time
          </span>
        </div>

        {/* Key Metrics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {/* Bottleneck */}
          <div className="bg-dark-800/40 border border-dark-500 rounded-lg p-3">
            <div className="text-xs text-text-dim font-bold uppercase tracking-widest mb-1">Bottleneck</div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-emerald-400 truncate">{summary.good_bottleneck || '—'}</span>
              <span className="text-text-dim">→</span>
              <span className={`font-mono text-sm font-bold truncate ${
                summary.bottleneck_shift ? 'text-red-400' : 'text-text-primary'
              }`}>{summary.bad_bottleneck || '—'}</span>
            </div>
          </div>

          {/* AAS (Active Active Sessions) */}
          <div className="bg-dark-800/40 border border-dark-500 rounded-lg p-3">
            <div className="text-xs text-text-dim font-bold uppercase tracking-widest mb-1">AAS</div>
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-bold font-mono text-emerald-400">{(summary.aas_good ?? 0).toFixed(1)}</span>
              <span className="text-text-dim text-xs">→</span>
              <span className="text-2xl font-bold font-mono text-red-400">{(summary.aas_bad ?? 0).toFixed(1)}</span>
            </div>
          </div>

          {/* DB Time */}
          <div className="bg-dark-800/40 border border-dark-500 rounded-lg p-3">
            <div className="text-xs text-text-dim font-bold uppercase tracking-widest mb-1">DB Time</div>
            <div className="flex items-baseline gap-1">
              <span className="text-sm font-mono text-emerald-400">{formatDuration(summary.good_period?.db_time_secs || 0)}</span>
              <span className="text-text-dim text-xs">→</span>
              <span className="text-sm font-mono text-red-400">{formatDuration(summary.bad_period?.db_time_secs || 0)}</span>
            </div>
          </div>

          {/* Health Status */}
          <div className="bg-dark-800/40 border border-dark-500 rounded-lg p-3">
            <div className="text-xs text-text-dim font-bold uppercase tracking-widest mb-1">Health Score</div>
            <div className="flex items-baseline gap-1">
              <span className="text-lg font-bold text-emerald-400">{summary.health_score_good || 0}</span>
              <span className="text-text-dim text-xs">→</span>
              <span className="text-lg font-bold text-red-400">{summary.health_score_bad || 0}</span>
            </div>
          </div>
        </div>

        {/* Headline + Evidence */}
        {(summary.headline || summary.overall_regression) && (
          <div className="bg-dark-800/30 border border-dark-500 rounded-lg p-4">
            <div className="text-xs text-accent-amber font-bold uppercase tracking-widest mb-2">Key Finding</div>
            <p className="text-sm text-text-primary leading-relaxed">
              {summary.headline || summary.overall_regression}
            </p>
            {(summary.headline_evidence || []).length > 0 && (
              <div className="mt-3 space-y-1 text-xs text-text-muted font-mono">
                {(summary.headline_evidence || []).slice(0, 3).map((e: string, i: number) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-accent-cyan">→</span>
                    <span>{e}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════
          TAB NAVIGATION
          ═══════════════════════════════════════════ */}
      <div className="border-b border-dark-500 flex gap-1">
        {[
          { id: 'overview', label: 'Overview', icon: '◉' },
          { id: 'metrics', label: 'Load Profile', icon: '▶' },
          { id: 'waits', label: 'Wait Events', icon: '⏱' },
          { id: 'sql', label: 'SQL', icon: '◤' },
          { id: 'efficiency', label: 'Efficiency', icon: '⚙' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-3 py-2 text-xs font-bold uppercase tracking-widest transition ${
              activeTab === tab.id
                ? 'text-accent-amber border-b-2 border-accent-amber'
                : 'text-text-dim hover:text-text-primary'
            }`}
          >
            <span className="mr-1">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* ═══════════════════════════════════════════
          TAB: OVERVIEW (ADDM + Recommendations)
          ═══════════════════════════════════════════ */}
      {activeTab === 'overview' && (
        <div className="space-y-4 max-h-96 overflow-y-auto">
          {/* ADDM Findings */}
          {addmFindings.length > 0 && (
            <div>
              <h3 className="text-xs font-bold text-text-dim uppercase tracking-widest mb-2">Oracle ADDM Findings</h3>
              <div className="space-y-2">
                {addmFindings.slice(0, 5).map((f: any, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-xs p-2 bg-dark-800/40 rounded border border-dark-500">
                    <span className="text-amber-400 mt-0.5">●</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-text-primary">{f.finding_name}</div>
                      {f.pct_active_sessions > 0 && (
                        <div className="text-text-muted font-mono text-[0.7rem]">
                          AAS: {f.avg_active_sessions?.toFixed(1)} ({f.pct_active_sessions?.toFixed(0)}%)
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top Recommendations */}
          {recommendations.length > 0 && (
            <div>
              <h3 className="text-xs font-bold text-text-dim uppercase tracking-widest mb-2">Recommendations</h3>
              <div className="space-y-2">
                {recommendations.slice(0, 5).map((r: any, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-xs p-2 bg-dark-800/40 rounded border border-dark-500">
                    <span className="text-emerald-400 mt-0.5">→</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-text-primary">{r.recommendation || r.title}</div>
                      {r.category && (
                        <div className="text-text-muted text-[0.7rem]">{r.category}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════
          TAB: LOAD PROFILE (Top Changes)
          ═══════════════════════════════════════════ */}
      {activeTab === 'metrics' && (
        <div className="space-y-2 max-h-96 overflow-y-auto">
          <h3 className="text-xs font-bold text-text-dim uppercase tracking-widest mb-3">Top Metrics Changed</h3>
          {topMetrics.length > 0 ? (
            <div className="space-y-2">
              {topMetrics.map((m: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-2.5 bg-dark-800/40 rounded border border-dark-500 text-xs">
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-text-primary truncate">{m.metric}</div>
                    <div className="text-text-muted text-[0.7rem]">
                      Good: <span className="text-emerald-400 font-mono">{formatNumber(m.good_val, 2)}</span>
                      <span className="mx-1">→</span>
                      Bad: <span className="text-red-400 font-mono">{formatNumber(m.bad_val, 2)}</span>
                    </div>
                  </div>
                  <div className="ml-3">
                    <DeltaBadge delta={m.change_pct} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-text-muted italic">No significant load profile changes</div>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════
          TAB: WAIT EVENTS
          ═══════════════════════════════════════════ */}
      {activeTab === 'waits' && (
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {/* New/Worsening Events */}
          {(waitEvents.regressions || []).length > 0 && (
            <div>
              <h3 className="text-xs font-bold text-red-400 uppercase tracking-widest mb-2">
                Regressions ({waitEvents.regressions.length})
              </h3>
              <div className="space-y-2">
                {(waitEvents.regressions || []).slice(0, 5).map((e: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 p-2.5 bg-dark-800/40 rounded border border-dark-500 text-xs">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-text-primary">{e.event_name}</span>
                        {e.is_new && <span className="badge bg-orange-500/20 text-orange-300 border-orange-500/40 text-[0.6rem]">NEW</span>}
                      </div>
                      <div className="text-text-muted font-mono text-[0.7rem] mt-1">
                        Good: {formatDuration(e.good_time || 0)} → Bad: {formatDuration(e.bad_time || 0)}
                      </div>
                      <div className="text-text-muted text-[0.7rem]">{e.wait_class}</div>
                    </div>
                    <div className="ml-2">
                      <DeltaBadge delta={e.change_pct} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Good Wait Events (Baseline) */}
          {(waitEvents.good || []).length > 0 && (
            <div>
              <h3 className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-2">
                Baseline Events ({waitEvents.good.length})
              </h3>
              <div className="space-y-1 text-xs">
                {(waitEvents.good || []).slice(0, 3).map((e: any, i: number) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-dark-800/40 rounded border border-dark-500">
                    <span className="font-mono text-text-primary truncate">{e.event_name}</span>
                    <span className="text-text-muted font-mono ml-2">{formatDuration(e.time_waited_secs)} · {(e.pct_db_time || 0).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════
          TAB: SQL REGRESSIONS
          ═══════════════════════════════════════════ */}
      {activeTab === 'sql' && (
        <div className="space-y-2 max-h-96 overflow-y-auto">
          <h3 className="text-xs font-bold text-text-dim uppercase tracking-widest mb-3">
            SQL Changes ({sqlRegressions.length})
          </h3>
          {sqlRegressions.length > 0 ? (
            <div className="space-y-2">
              {sqlRegressions.slice(0, 5).map((sql: any, i: number) => (
                <div key={i} className="p-2.5 bg-dark-800/40 rounded border border-dark-500 text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-accent-cyan font-bold">{sql.sql_id}</span>
                    <div className="flex items-center gap-2">
                      {sql.tag && (
                        <span className={`badge text-[0.6rem] font-bold border ${
                          sql.tag === 'regression' ? 'bg-red-500/20 text-red-300 border-red-500/40' :
                          sql.tag === 'improved' ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' :
                          sql.tag === 'new_offender' ? 'bg-orange-500/20 text-orange-300 border-orange-500/40' :
                          'bg-slate-500/20 text-slate-300 border-slate-500/40'
                        }`}>
                          {sql.tag?.toUpperCase().replace(/_/g, ' ')}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-text-muted font-mono text-[0.7rem] truncate">{sql.sql_text || 'N/A'}</div>
                  <div className="flex items-center justify-between text-[0.7rem] text-text-dim">
                    <span>Execs: {sql.executions} | CPU: {formatDuration(sql.cpu_time_secs)}</span>
                    {sql.elapsed_time_delta_pct && <DeltaBadge delta={sql.elapsed_time_delta_pct} />}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-text-muted italic">No SQL regressions detected</div>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════
          TAB: INSTANCE EFFICIENCY
          ═══════════════════════════════════════════ */}
      {activeTab === 'efficiency' && (
        <div className="space-y-2 max-h-96 overflow-y-auto">
          <h3 className="text-xs font-bold text-text-dim uppercase tracking-widest mb-3">
            Efficiency Metrics
          </h3>
          {(instanceEfficiency.alerts || []).length > 0 ? (
            <div className="space-y-2">
              {(instanceEfficiency.alerts || []).slice(0, 5).map((alert: any, i: number) => (
                <div key={i} className={`p-2.5 rounded border text-xs space-y-1 ${severityBadge(alert.severity)}`}>
                  <div className="font-bold">{alert.metric}</div>
                  <div className="text-[0.7rem]">
                    {alert.message || `Good: ${alert.good || '—'} → Bad: ${alert.bad || '—'}`}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-text-muted italic">No efficiency alerts</div>
          )}
        </div>
      )}

      {/* Footer: Data Source & Timestamp */}
      <div className="border-t border-dark-500 pt-3 flex items-center justify-between text-[0.7rem] text-text-muted">
        <span>AWR Intelligence Engine v4</span>
        <span className="font-mono">
          Good: {summary.good_period?.label} | Bad: {summary.bad_period?.label}
        </span>
      </div>
    </div>
  );
}
