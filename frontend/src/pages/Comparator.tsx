import { useState, useEffect } from 'react';
import { useComparison } from '../hooks/useAWR';
import ComparisonSideBySide from '../components/ComparisonSideBySide';
import HealthScoreMeter from '../components/HealthScoreMeter';
import DeltaBadge from '../components/DeltaBadge';
import WaitEventChart from '../components/WaitEventChart';
import CompactExecutiveSummary from '../components/CompactExecutiveSummary';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts';
import { formatNumber, formatPct, formatDelta, formatDuration, severityColor, truncateSql } from '../utils/formatters';

/* ──────────────────────────────────────────────
   Constants
   ────────────────────────────────────────────── */

const INCIDENT_ICONS: Record<string, string> = {
  'LOCK-DRIVEN FREEZE': '🔒',
  'HARD PARSE STORM': '🌩',
  'LOG SYNC BOTTLENECK': '📝',
  'PGA OVER-ALLOCATION': '🧠',
  'IO SATURATION': '💾',
  'CPU SATURATION': '🔥',
  'LATCH CONTENTION': '⚡',
  'UNDO CONTENTION': '🔄',
};

const TAG_COLORS: Record<string, string> = {
  'new_offender': 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  'regression': 'bg-red-500/20 text-red-300 border-red-500/40',
  'load_increase': 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  'improved': 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
};

const TAG_LABELS: Record<string, string> = {
  'new_offender': 'New Offender',
  'regression': 'Regression',
  'load_increase': 'Load Increase',
  'improved': 'Improved',
};

const ASSESSMENT_COLORS: Record<string, string> = {
  'Regressed': 'bg-red-500/20 text-red-300 border-red-500/40',
  'Improved': 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  'Stable': 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
  'New SQL': 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  'Disappeared': 'bg-slate-500/20 text-slate-300 border-slate-500/40',
  'Cannot Determine': 'bg-slate-500/20 text-slate-400 border-slate-500/40',
};

const PLAN_VERDICT_COLORS: Record<string, string> = {
  'Plan Regressed': 'bg-red-500/20 text-red-300 border-red-500/40',
  'Plan Improved': 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  'Plan Changed - Neutral': 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
  'Same Plan': 'bg-slate-500/20 text-slate-400 border-slate-500/40',
};

const LATENCY_FLAG_LABELS: Record<string, { color: string; label: string }> = {
  'volume_increase': { color: 'bg-amber-500/20 text-amber-300 border-amber-500/40', label: 'Volume ↑' },
  'latency_increase': { color: 'bg-red-500/20 text-red-300 border-red-500/40', label: 'Latency ↑' },
  'both': { color: 'bg-red-500/20 text-red-300 border-red-500/40', label: 'Both ↑' },
};

const CURSOR_COLORS: Record<string, string> = {
  green: 'text-emerald-400 border-emerald-500',
  amber: 'text-amber-400 border-amber-500',
  orange: 'text-orange-400 border-orange-500',
  red: 'text-red-400 border-red-500',
  gray: 'text-slate-400 border-slate-500',
};

const WORKLOAD_COLORS = ['#3b82f6', '#f59e0b', '#8b5cf6', '#10b981', '#ef4444', '#ec4899', '#14b8a6', '#f97316', '#6366f1'];

const PRIORITY_STYLES: Record<number, { bg: string; text: string; label: string }> = {
  1: { bg: 'bg-red-500/15 border-red-500/40', text: 'text-red-400', label: 'P1 Critical' },
  2: { bg: 'bg-amber-500/15 border-amber-500/40', text: 'text-amber-400', label: 'P2 High' },
  3: { bg: 'bg-cyan-500/15 border-cyan-500/40', text: 'text-cyan-400', label: 'P3 Medium' },
  4: { bg: 'bg-slate-500/15 border-slate-500/40', text: 'text-slate-400', label: 'P4 Low' },
};

/* ──────────────────────────────────────────────
   Helper: Row severity class
   ────────────────────────────────────────────── */

function rowSeverityClass(severity: string): string {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'border-l-2 border-l-red-500 bg-red-500/5';
    case 'warning': return 'border-l-2 border-l-amber-500 bg-amber-500/5';
    case 'good':
    case 'improved': return 'border-l-2 border-l-emerald-500 bg-emerald-500/5';
    default: return '';
  }
}

function efficiencyCellClass(value: number, threshold: number, higherIsBetter = true): string {
  if (higherIsBetter) {
    if (value >= threshold) return 'text-emerald-400';
    if (value >= threshold * 0.9) return 'text-amber-400';
    return 'text-red-400';
  }
  if (value <= threshold) return 'text-emerald-400';
  if (value <= threshold * 1.1) return 'text-amber-400';
  return 'text-red-400';
}

/* ──────────────────────────────────────────────
   Main Component
   ────────────────────────────────────────────── */

export default function Comparator() {
  const { data, loading, error, compare } = useComparison();

  // Column sort state for Load Profile table
  const [lpSortKey, setLpSortKey] = useState<string>('change_pct');
  const [lpSortAsc, setLpSortAsc] = useState(false);

  // Column sort state for Efficiency table
  const [effSortKey, setEffSortKey] = useState<string>('metric');
  const [effSortAsc, setEffSortAsc] = useState(true);

  // SQL filter tab
  const [sqlFilter, setSqlFilter] = useState<string>('all');

  // Expanded SQL row
  const [expandedSql, setExpandedSql] = useState<string | null>(null);

  // Copied command tracking
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  // Auto-trigger comparison on mount
  useEffect(() => {
    compare();
  }, [compare]);

  /* ─── Copy to clipboard helper ─── */
  const copyToClipboard = (text: string, idx: number) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(null), 2000);
    });
  };

  /* ─── Sort helpers ─── */
  const handleLpSort = (key: string) => {
    if (lpSortKey === key) setLpSortAsc(!lpSortAsc);
    else { setLpSortKey(key); setLpSortAsc(false); }
  };

  const handleEffSort = (key: string) => {
    if (effSortKey === key) setEffSortAsc(!effSortAsc);
    else { setEffSortKey(key); setEffSortAsc(true); }
  };

  /* ──────────────────────────────────────────
     LOADING STATE
     ────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] gap-6">
        <div className="relative">
          <div className="w-20 h-20 rounded-full border-4 border-dark-500 border-t-accent-amber animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-10 h-10 rounded-full border-4 border-dark-500 border-b-accent-cyan animate-spin" style={{ animationDirection: 'reverse', animationDuration: '0.8s' }} />
          </div>
        </div>
        <div className="text-center">
          <div className="text-text-primary font-bold text-lg">Analyzing AWR Snapshots</div>
          <div className="text-text-muted text-sm mt-1">Comparing good vs bad period metrics...</div>
        </div>
      </div>
    );
  }

  /* ──────────────────────────────────────────
     ERROR STATE
     ────────────────────────────────────────── */
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] gap-4">
        <div className="w-16 h-16 rounded-full bg-red-500/15 flex items-center justify-center text-3xl text-red-400">!</div>
        <div className="text-red-400 font-bold text-lg">Comparison Failed</div>
        <div className="text-text-muted text-sm max-w-md text-center">{error}</div>
        <button onClick={compare} className="btn-primary mt-2">
          Retry Comparison
        </button>
      </div>
    );
  }

  /* ──────────────────────────────────────────
     NO DATA — pre-comparison state
     ────────────────────────────────────────── */
  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-6">
        <div className="text-6xl opacity-30">&#x27FA;</div>
        <div className="text-text-primary font-bold text-xl">AWR Period Comparator</div>
        <div className="text-text-muted text-sm max-w-lg text-center">
          Select a baseline (good) period and a problem (bad) period to generate a comprehensive comparison report
          with health scores, wait event analysis, SQL regressions, and actionable recommendations.
        </div>
        <button onClick={compare} className="btn-primary text-lg px-8 py-3 mt-2">
          Compare Now
        </button>
      </div>
    );
  }

  /* ──────────────────────────────────────────
     Extract data sections
     ────────────────────────────────────────── */
  const report = data?.report || data || {};
  const {
    summary,
    load_profile_delta = [],
    top_wait_events: rawWaitEvents = {},
    instance_efficiency: rawEfficiency = {},
    sql_regressions = [],
    recommendations: reportRecs = [],
    incident_indicators = [],
  } = report;

  /* ─── Transform wait events from backend shape ─── */
  const waitComparisons = rawWaitEvents.comparisons || [];
  const top_wait_events = {
    good: waitComparisons.map((e: any) => ({
      event_name: e.event_name,
      time_waited_secs: e.good_time_secs ?? 0,
      pct_db_time: e.good_pct_db_time ?? 0,
      wait_class: e.wait_class || 'Other',
    })).filter((e: any) => e.time_waited_secs > 0),
    bad: waitComparisons.map((e: any) => ({
      event_name: e.event_name,
      time_waited_secs: e.bad_time_secs ?? 0,
      pct_db_time: e.bad_pct_db_time ?? 0,
      wait_class: e.wait_class || 'Other',
    })).filter((e: any) => e.time_waited_secs > 0),
    regressions: [
      ...(rawWaitEvents.new_bottlenecks || []).map((e: any) => ({ ...e, is_new: true, good_time: e.good_time_secs, bad_time: e.bad_time_secs, change_pct: e.delta_pct, good_avg_wait_ms: e.good_avg_wait_ms, bad_avg_wait_ms: e.bad_avg_wait_ms, latency_delta_pct: e.latency_delta_pct, latency_flag: e.latency_flag, extreme_wait_flag: e.extreme_wait_flag })),
      ...(rawWaitEvents.worsening || []).map((e: any) => ({ ...e, is_new: false, good_time: e.good_time_secs, bad_time: e.bad_time_secs, change_pct: e.delta_pct, good_avg_wait_ms: e.good_avg_wait_ms, bad_avg_wait_ms: e.bad_avg_wait_ms, latency_delta_pct: e.latency_delta_pct, latency_flag: e.latency_flag, extreme_wait_flag: e.extreme_wait_flag })),
    ],
  };

  /* ─── Transform instance efficiency from backend shape ─── */
  const effComparisons = rawEfficiency.comparisons || [];
  const instance_efficiency = {
    alerts: rawEfficiency.alerts || [],
  };

  const recommendations = data?.recommendations || reportRecs || [];
  const advanced = data?.advanced || {};
  const workloadComp = advanced.workload_composition || { good: [], bad: [] };
  const cursorHealth = advanced.cursor_health || { good: { score: 0, grade: '?', color: 'gray', components: [] }, bad: { score: 0, grade: '?', color: 'gray', components: [] } };
  const causalChains = advanced.causal_chains || [];
  const batchPurges = advanced.batch_purges || [];
  const bizThroughput = advanced.business_throughput || { good: {}, bad: {}, delta: {} };
  const sqlAssessments = advanced.sql_net_assessments || sql_regressions;
  const batchGroups = report.batch_groups || advanced.batch_groups || [];
  const logonStormExplanation = report.logon_storm_explanation || '';
  const extremeWaits = rawWaitEvents.extreme_waits || [];
  const culprits = advanced.culprits || [];

  // Evidence-based headline
  const headline = summary?.headline || '';
  const headlineEvidence = summary?.headline_evidence || [];

  // SQL Zones
  const sqlHighFrequency = report.sql_high_frequency || [];
  const sqlPlanChanges = report.sql_plan_changes || [];
  const sqlNewInBad = report.sql_new_in_bad || [];
  const sqlMaintenance = report.sql_maintenance || [];

  // ADDM findings
  const addmFindings = report.addm_findings || [];

  /* ─── Sorted load profile data ─── */
  const sortedLoadProfile = [...load_profile_delta].sort((a: any, b: any) => {
    const av = a[lpSortKey] ?? 0;
    const bv = b[lpSortKey] ?? 0;
    if (typeof av === 'string') return lpSortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    return lpSortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
  });

  /* ─── Instance efficiency rows (from backend comparisons) ─── */
  const efficiencyMetrics = effComparisons.map((c: any) => ({
    metric: c.metric,
    good: c.good_val,
    bad: c.bad_val,
    delta: c.delta,
    threshold: c.threshold,
    severity: c.severity,
    message: c.message,
  }));

  const sortedEfficiency = [...efficiencyMetrics].sort((a: any, b: any) => {
    const av = a[effSortKey] ?? 0;
    const bv = b[effSortKey] ?? 0;
    if (typeof av === 'string') return effSortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    return effSortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
  });

  /* ─── Filtered SQL regressions (with net assessments) ─── */
  const filteredSql = sqlFilter === 'all'
    ? sqlAssessments
    : sqlAssessments.filter((s: any) => s.tag === sqlFilter);

  /* ─── Load profile chart data (top 8 by absolute change) ─── */
  const loadProfileChartData = [...load_profile_delta]
    .sort((a: any, b: any) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
    .slice(0, 8)
    .map((m: any) => ({
      name: m.metric?.length > 20 ? m.metric.substring(0, 20) + '...' : m.metric,
      fullName: m.metric,
      change: m.change_pct,
    }));

  /* ─── Recommendation category pie chart data ─── */
  const recCategoryCounts: Record<string, number> = {};
  recommendations.forEach((r: any) => {
    recCategoryCounts[r.category] = (recCategoryCounts[r.category] || 0) + 1;
  });
  const recPieData = Object.entries(recCategoryCounts).map(([name, value]) => ({ name, value }));
  const PIE_COLORS = ['#f59e0b', '#3b82f6', '#ef4444', '#10b981', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

  /* ══════════════════════════════════════════
     RENDER
     ══════════════════════════════════════════ */
  return (
    <div className="space-y-6">

      {/* ────────────────────────────────────
          1. COMPACT HEADER — Periods + Compare
          ──────────────────────────────────── */}
      <div className="card">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          {/* Good Period */}
          <div className="flex-1 min-w-0">
            <div className="text-xs text-emerald-400 uppercase tracking-widest font-bold mb-1">Good (Baseline)</div>
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded-full bg-emerald-500 shadow-lg shadow-emerald-500/30" />
              <div>
                <div className="text-text-primary font-bold">
                  {summary?.good_period?.label || 'Baseline Period'}
                </div>
                <div className="text-xs text-text-muted font-mono">
                  Snap {summary?.good_period?.snap_begin ?? '—'}–{summary?.good_period?.snap_end ?? '—'} · {summary?.good_period?.elapsed_min ?? 0} min · DB Time {summary?.good_period?.db_time_secs != null ? formatDuration(summary.good_period.db_time_secs) : '—'}
                </div>
              </div>
            </div>
          </div>

          {/* Compare */}
          <div className="flex flex-col items-center gap-1">
            <button onClick={compare} disabled={loading} className="btn-primary px-6 py-2 text-sm font-bold tracking-wide">
              {loading ? 'Comparing...' : '⟺ Compare'}
            </button>
          </div>

          {/* Bad Period */}
          <div className="flex-1 min-w-0 text-right">
            <div className="text-xs text-red-400 uppercase tracking-widest font-bold mb-1">Bad (Problem)</div>
            <div className="flex items-center justify-end gap-3">
              <div>
                <div className="text-text-primary font-bold">
                  {summary?.bad_period?.label || 'Problem Period'}
                </div>
                <div className="text-xs text-text-muted font-mono">
                  Snap {summary?.bad_period?.snap_begin ?? '—'}–{summary?.bad_period?.snap_end ?? '—'} · {summary?.bad_period?.elapsed_min ?? 0} min · DB Time {summary?.bad_period?.db_time_secs != null ? formatDuration(summary.bad_period.db_time_secs) : '—'}
                </div>
              </div>
              <div className="w-3 h-3 rounded-full bg-red-500 shadow-lg shadow-red-500/30" />
            </div>
          </div>
        </div>
      </div>

      {/* ────────────────────────────────────
          2. COMPACT EXECUTIVE SUMMARY (NEW)
          ──────────────────────────────────── */}
      {summary && (
        <CompactExecutiveSummary
          summary={summary}
          loadProfileDelta={load_profile_delta}
          waitEvents={top_wait_events}
          sqlRegressions={sqlAssessments}
          instanceEfficiency={instance_efficiency}
          addmFindings={addmFindings}
          recommendations={recommendations}
        />
      )}

      {/* ────────────────────────────────────
          3. AUTOMATED ANALYSIS — Evidence-Based Headline
          ──────────────────────────────────── */}
      {summary && (
        <div className="card border border-dark-400 hidden">
          {/* Health scores compact */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-6">
              <HealthScoreMeter score={summary.health_score_good} label="Good" size={80} />
              <div className="text-center">
                <div className="text-xs text-text-dim uppercase tracking-widest">vs</div>
                <div className={`text-2xl font-mono font-bold ${summary.db_time_delta_pct > 20 ? 'text-red-400' : summary.db_time_delta_pct > 5 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {summary.db_time_delta_pct > 0 ? '▲' : '▼'} {Math.abs(summary.db_time_delta_pct || 0).toFixed(0)}% DB Time
                </div>
              </div>
              <HealthScoreMeter score={summary.health_score_bad} label="Bad" size={80} />
            </div>
            <div className="flex flex-col items-end gap-1">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-text-dim">Bottleneck:</span>
                <span className="font-mono text-text-primary">{summary.good_bottleneck || '—'}</span>
                <span className="text-text-dim">→</span>
                <span className={`font-mono font-bold ${summary.bottleneck_shift ? 'text-amber-400' : 'text-text-primary'}`}>
                  {summary.bad_bottleneck || '—'}
                </span>
              </div>
              <div className="flex items-center gap-4 text-xs font-mono">
                <span className="text-text-dim">AAS: <span className="text-emerald-400">{summary.aas_good?.toFixed(1)}</span> → <span className="text-red-400">{summary.aas_bad?.toFixed(1)}</span></span>
                {summary.cpu_capacity_used_pct > 0 && (
                  <span className="text-text-dim">CPU used: <span className={summary.cpu_capacity_used_pct > 70 ? 'text-red-400' : 'text-text-primary'}>{summary.cpu_capacity_used_pct}%</span></span>
                )}
              </div>
              {summary.congestion_signal && (
                <span className="badge bg-red-500/20 text-red-300 border border-red-500/40 text-[0.6rem]">⚠ Congestion</span>
              )}
            </div>
          </div>

          {/* Headline */}
          <div className="relative group">
            <div className="flex items-start gap-3">
              <span className="text-accent-amber text-xl mt-0.5">◉</span>
              <div className="flex-1">
                <div className="text-xs text-accent-amber uppercase tracking-widest font-bold mb-1">Automated Analysis <span className="text-text-dim font-normal">Rule-based DBA logic</span></div>
                <div className="text-sm text-text-primary font-medium leading-relaxed">
                  {headline || summary.overall_regression || 'Analysis pending...'}
                </div>
              </div>
            </div>
            {/* Evidence tooltip on hover */}
            {headlineEvidence.length > 0 && (
              <div className="mt-2 space-y-1 text-xs bg-dark-800/80 rounded-lg border border-dark-500 p-3">
                <div className="text-text-dim uppercase tracking-widest text-[0.6rem] mb-1 font-bold">Evidence Trail — why this headline</div>
                {headlineEvidence.map((e: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-text-muted font-mono">
                    <span className="text-accent-cyan mt-0.5">→</span>
                    <span>{e}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ADDM findings (authoritative Oracle diagnostics) */}
          {addmFindings.length > 0 && (
            <div className="mt-3 border-t border-dark-500 pt-3">
              <div className="text-xs text-text-dim uppercase tracking-widest font-bold mb-2">ADDM Findings (Oracle Diagnostic Engine)</div>
              <div className="space-y-1">
                {addmFindings.map((f: any, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-amber-400">●</span>
                    <span className="text-text-primary font-medium">{f.finding_name}</span>
                    {f.avg_active_sessions > 0 && (
                      <span className="font-mono text-text-dim">AAS={f.avg_active_sessions.toFixed(1)}</span>
                    )}
                    {f.pct_active_sessions > 0 && (
                      <span className="font-mono text-text-dim">({f.pct_active_sessions.toFixed(0)}%)</span>
                    )}
                    {f.referenced_sql_ids?.length > 0 && (
                      <span className="font-mono text-accent-cyan">[SQL: {f.referenced_sql_ids.join(', ')}]</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Logon storm explanation */}
          {logonStormExplanation && (
            <div className="mt-3 px-4 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-start gap-2">
              <span className="text-amber-400 text-sm mt-0.5">🌩</span>
              <div>
                <span className="text-amber-300 text-xs font-bold">Logon Storm → Parse Storm</span>
                <div className="text-text-muted text-xs mt-0.5">{logonStormExplanation}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ────────────────────────────────────
          2a. KEY METRICS STRIP
          ──────────────────────────────────── */}
      {bizThroughput.good?.txn_per_sec != null && (
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <div className="section-title mb-0">Business Throughput</div>
            <div className="group relative">
              <span className="text-text-dim text-xs cursor-help underline decoration-dotted">Data source</span>
              <div className="hidden group-hover:block absolute right-0 top-6 z-20 w-72 p-3 rounded-lg bg-dark-800 border border-dark-500 shadow-xl text-xs text-text-muted">
                TXN/sec from Load Profile "User Commits + Rollbacks Per Sec". AAS = DB Time / Elapsed Time. Direct AWR values, no inference.
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-dark-800/50 rounded-lg p-4 border border-dark-500 text-center">
              <div className="text-xs text-text-dim uppercase tracking-widest mb-1">TXN/sec (Good)</div>
              <div className="text-2xl font-bold text-emerald-400 font-mono">{formatNumber(bizThroughput.good.txn_per_sec, 1)}</div>
            </div>
            <div className="bg-dark-800/50 rounded-lg p-4 border border-dark-500 text-center">
              <div className="text-xs text-text-dim uppercase tracking-widest mb-1">TXN/sec (Bad)</div>
              <div className="text-2xl font-bold text-red-400 font-mono">{formatNumber(bizThroughput.bad.txn_per_sec, 1)}</div>
              <div className="mt-1">
                <DeltaBadge delta={bizThroughput.delta.txn_per_sec_pct} higherIsWorse={false} />
              </div>
            </div>
            <div className="bg-dark-800/50 rounded-lg p-4 border border-dark-500 text-center">
              <div className="text-xs text-text-dim uppercase tracking-widest mb-1">AAS (Good)</div>
              <div className="text-2xl font-bold text-emerald-400 font-mono">{formatNumber(bizThroughput.good.aas, 2)}</div>
            </div>
            <div className="bg-dark-800/50 rounded-lg p-4 border border-dark-500 text-center">
              <div className="text-xs text-text-dim uppercase tracking-widest mb-1">AAS (Bad)</div>
              <div className="text-2xl font-bold text-red-400 font-mono">{formatNumber(bizThroughput.bad.aas, 2)}</div>
              <div className="mt-1">
                <DeltaBadge delta={bizThroughput.delta.aas_pct} />
              </div>
            </div>
          </div>
          {bizThroughput.delta.congestion_signal && (
            <div className="mt-3 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30 flex items-center gap-2">
              <span className="text-red-400 font-bold text-lg">&#x26A0;</span>
              <span className="text-red-300 text-sm font-medium">Congestion Signal: DB Time rising while TXN/sec falling — system is doing more work per transaction</span>
            </div>
          )}
        </div>
      )}

      {/* ────────────────────────────────────
          2b. DESIGN 1 — Workload Composition Donuts
          ──────────────────────────────────── */}
      {(workloadComp.good?.length > 0 || workloadComp.bad?.length > 0) && (
        <div className="card">
          <div className="section-title mb-3">Workload Composition (by SQL Module)</div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {['good', 'bad'].map((period) => {
              const items = (workloadComp as any)[period] || [];
              const label = period === 'good' ? 'Good Period' : 'Bad Period';
              const dotColor = period === 'good' ? 'bg-emerald-500' : 'bg-red-500';
              return (
                <div key={period}>
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-2 h-2 rounded-full ${dotColor}`} />
                    <span className="text-xs text-text-muted uppercase tracking-widest font-bold">{label}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <ResponsiveContainer width="50%" height={180}>
                      <PieChart>
                        <Pie data={items} dataKey="pct_db_time" nameKey="category" cx="50%" cy="50%"
                          outerRadius={70} innerRadius={35} paddingAngle={2} stroke="none">
                          {items.map((_: any, i: number) => (
                            <Cell key={i} fill={WORKLOAD_COLORS[i % WORKLOAD_COLORS.length]} fillOpacity={0.85} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: '#0d1526', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                          formatter={(v: number) => [`${v.toFixed(1)}%`, 'DB Time']} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="flex-1 space-y-1">
                      {items.map((w: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: WORKLOAD_COLORS[i % WORKLOAD_COLORS.length] }} />
                          <span className="text-text-muted truncate flex-1">{w.category}</span>
                          <span className="font-mono text-text-primary">{w.pct_db_time.toFixed(1)}%</span>
                          <span className="font-mono text-text-dim text-[0.6rem]">{w.sql_count} SQLs</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────
          2c. DESIGN 2 — Cursor Health Score Cards
          ──────────────────────────────────── */}
      {(cursorHealth.good?.score != null || cursorHealth.bad?.score != null) && (
        <div className="card">
          <div className="section-title mb-3">Cursor Health</div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {(['good', 'bad'] as const).map((period) => {
              const ch = (cursorHealth as any)[period];
              if (!ch) return null;
              const label = period === 'good' ? 'Good Period' : 'Bad Period';
              const dotColor = period === 'good' ? 'bg-emerald-500' : 'bg-red-500';
              const colorCls = CURSOR_COLORS[ch.color] || CURSOR_COLORS.gray;
              return (
                <div key={period} className="bg-dark-800/50 rounded-lg p-4 border border-dark-500">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${dotColor}`} />
                      <span className="text-xs text-text-muted uppercase tracking-widest font-bold">{label}</span>
                    </div>
                    <div className={`text-3xl font-black font-mono ${colorCls.split(' ')[0]}`}>
                      {ch.score}<span className="text-lg text-text-dim">/100</span>
                      <span className="ml-2 text-lg">{ch.grade}</span>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {(ch.components || []).map((c: any, i: number) => {
                      const barWidth = Math.min(100, (c.score / c.weight) * 100);
                      const barColor = c.status === 'good' ? 'bg-emerald-500' : c.status === 'warning' ? 'bg-amber-500' : 'bg-red-500';
                      return (
                        <div key={i}>
                          <div className="flex items-center justify-between text-xs mb-0.5">
                            <span className="text-text-muted">{c.name}</span>
                            <span className="font-mono text-text-primary">{c.value}{c.unit}</span>
                          </div>
                          <div className="h-1.5 bg-dark-600 rounded-full overflow-hidden">
                            <div className={`h-full ${barColor} rounded-full transition-all duration-500`} style={{ width: `${barWidth}%` }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────
          2d. DESIGN 3 — Causal Chain Auto-Narrative
          ──────────────────────────────────── */}
      {causalChains.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-amber-400 text-lg">&#x1F517;</span>
            <h2 className="section-title mb-0">Root Cause Chains</h2>
            <span className="badge bg-amber-500/20 text-amber-300 border border-amber-500/40 text-xs ml-2">
              {causalChains.length} chain(s)
            </span>
          </div>
          <div className="space-y-3">
            {causalChains.map((chain: any, idx: number) => (
              <div key={idx} className={`card border ${chain.severity === 'critical' ? 'border-red-500/30 bg-gradient-to-br from-red-500/5 to-transparent' : 'border-amber-500/30 bg-gradient-to-br from-amber-500/5 to-transparent'}`}>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className={`badge border text-[0.6rem] font-bold ${chain.severity === 'critical' ? 'bg-red-500/20 text-red-300 border-red-500/40' : 'bg-amber-500/20 text-amber-300 border-amber-500/40'}`}>
                      {chain.severity.toUpperCase()}
                    </span>
                  </div>
                  <div className="flex flex-col md:flex-row md:items-start gap-2 md:gap-0">
                    <div className="flex-1">
                      <div className="text-xs text-text-dim uppercase tracking-widest mb-0.5">Trigger</div>
                      <div className="text-sm text-red-300 font-bold">{chain.trigger}</div>
                    </div>
                    <div className="hidden md:block text-text-dim text-lg px-3">→</div>
                    <div className="flex-1">
                      <div className="text-xs text-text-dim uppercase tracking-widest mb-0.5">Mechanism</div>
                      <div className="text-xs text-text-muted font-mono leading-relaxed">{chain.mechanism}</div>
                    </div>
                    <div className="hidden md:block text-text-dim text-lg px-3">→</div>
                    <div className="flex-1">
                      <div className="text-xs text-text-dim uppercase tracking-widest mb-0.5">Symptoms</div>
                      <div className="space-y-0.5">
                        {(chain.symptoms || []).map((s: string, si: number) => (
                          <div key={si} className="text-xs text-amber-300 font-mono">• {s}</div>
                        ))}
                      </div>
                    </div>
                  </div>
                  {chain.evidence?.length > 0 && (
                    <div className="mt-1 text-[0.65rem] font-mono text-text-dim bg-dark-800/50 rounded px-2 py-1 border border-dark-500">
                      Evidence: {chain.evidence.join(' | ')}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────
          3. INCIDENT INDICATORS
          ──────────────────────────────────── */}
      {incident_indicators.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-red-400 text-lg">&#x26A0;</span>
            <h2 className="section-title mb-0 text-red-400">Detected Incident Patterns</h2>
            <span className="badge bg-red-500/20 text-red-300 border border-red-500/40 text-xs ml-2">
              {incident_indicators.length} detected
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {incident_indicators.map((incident: any, idx: number) => (
              <div key={idx} className="card border border-red-500/30 bg-gradient-to-br from-red-500/5 to-transparent">
                <div className="flex items-start gap-3">
                  <div className="text-2xl mt-0.5">
                    {INCIDENT_ICONS[incident.pattern] || '&#x26A0;'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-bold text-red-300 text-sm">{incident.pattern}</span>
                      {incident.confidence != null && (
                        <span className="badge bg-red-500/20 text-red-400 border border-red-500/30 text-[0.6rem]">
                          {formatPct(incident.confidence * 100, 0)} confidence
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-text-muted leading-relaxed">{incident.description}</div>
                    {incident.evidence && (
                      <div className="mt-2 text-xs font-mono text-text-dim bg-dark-800/50 rounded px-2 py-1.5 border border-dark-500">
                        Evidence: {incident.evidence}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────
          3a. DESIGN 9 — Culprits Ranked by Impact
          ──────────────────────────────────── */}
      {culprits.length > 0 && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-red-400 text-lg">&#x1F3AF;</span>
              <div className="section-title mb-0">Top Culprits (by Normalized Impact)</div>
            </div>
            <div className="text-xs text-text-dim font-mono">{culprits.length} culprit SQL(s)</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="table-header">
                  <th className="px-3 py-2 text-left w-10">#</th>
                  <th className="px-3 py-2 text-left">SQL ID</th>
                  <th className="px-3 py-2 text-left">Category</th>
                  <th className="px-3 py-2 text-left">Elapsed/min</th>
                  <th className="px-3 py-2 text-left">% DB Time</th>
                  <th className="px-3 py-2 text-left">Tag</th>
                  <th className="px-3 py-2 text-left">Batch Group</th>
                </tr>
              </thead>
              <tbody>
                {culprits.map((c: any) => (
                  <tr key={c.sql_id} className={`table-row ${c.rank <= 3 ? 'border-l-2 border-l-red-500 bg-red-500/5' : ''}`}>
                    <td className="px-3 py-2 font-bold text-text-dim">{c.rank}</td>
                    <td className="px-3 py-2 font-mono text-accent-cyan font-bold text-xs">{c.sql_id}</td>
                    <td className="px-3 py-2">
                      <span className={`badge border text-[0.6rem] ${
                        c.category.includes('Maintenance') ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                        : c.category.includes('Ad-hoc') ? 'bg-slate-500/20 text-slate-300 border-slate-500/40'
                        : 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                      }`}>{c.category}</span>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400 font-bold">{formatNumber(c.elapsed_per_min, 1)}s/min</td>
                    <td className="px-3 py-2 font-mono text-xs text-text-primary">{c.pct_db_time.toFixed(1)}%</td>
                    <td className="px-3 py-2">
                      <span className={`badge border text-[0.6rem] font-bold ${TAG_COLORS[c.tag] || 'bg-slate-500/20 text-slate-300 border-slate-500/40'}`}>
                        {TAG_LABELS[c.tag] || c.tag}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      {c.batch_group ? (
                        <span className="badge bg-violet-500/20 text-violet-300 border border-violet-500/40 text-[0.6rem] font-bold">
                          {c.batch_group}
                        </span>
                      ) : <span className="text-text-dim text-xs">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────
          3b. DESIGN 4 — Batch Purge Detector
          ──────────────────────────────────── */}
      {batchPurges.length > 0 && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-amber-400 text-lg">&#x1F5D1;</span>
              <div className="section-title mb-0">Batch Purge Detection</div>
            </div>
            <span className="badge bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs">
              {batchPurges.length} DELETE statement(s)
            </span>
          </div>
          <div className="space-y-3">
            {batchPurges.map((p: any, idx: number) => (
              <div key={idx} className={`bg-dark-800/50 rounded-lg p-4 border ${p.severity === 'critical' ? 'border-red-500/30' : p.severity === 'warning' ? 'border-amber-500/30' : 'border-dark-500'}`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-accent-cyan font-bold text-xs">{p.sql_id}</span>
                    <span className="badge bg-orange-500/20 text-orange-300 border border-orange-500/40 text-[0.6rem]">
                      DELETE → {p.table_name}
                    </span>
                  </div>
                  <span className={`font-bold text-xs uppercase ${p.severity === 'critical' ? 'text-red-400' : p.severity === 'warning' ? 'text-amber-400' : 'text-text-muted'}`}>
                    {p.severity}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-2">
                  <div><span className="text-text-dim">Elapsed:</span> <span className="font-mono text-text-primary">{formatDuration(p.elapsed_secs)}</span></div>
                  <div><span className="text-text-dim">Execs:</span> <span className="font-mono text-text-primary">{formatNumber(p.executions)}</span></div>
                  <div><span className="text-text-dim">I/O Share:</span> <span className="font-mono text-red-400 font-bold">{p.io_pct.toFixed(1)}%</span></div>
                  <div><span className="text-text-dim">Disk Reads:</span> <span className="font-mono text-text-primary">{formatNumber(p.disk_reads)}</span></div>
                </div>
                {p.remediation?.length > 0 && (
                  <div className="text-[0.65rem] text-amber-300 space-y-0.5 mt-2 bg-dark-900/50 rounded px-2 py-1.5">
                    {p.remediation.map((r: string, ri: number) => (
                      <div key={ri}>&#x2192; {r}</div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────
          3c. DESIGN 8 — Batch Group Detection
          ──────────────────────────────────── */}
      {batchGroups.length > 0 && (
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-violet-400 text-lg">&#x1F4E6;</span>
              <div className="section-title mb-0">Correlated Batch Groups</div>
            </div>
            <span className="badge bg-violet-500/20 text-violet-300 border border-violet-500/30 text-xs">
              {batchGroups.length} group(s)
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {batchGroups.map((bg: any) => (
              <div key={bg.group_id} className="bg-dark-800/50 rounded-lg p-4 border border-violet-500/20">
                <div className="flex items-center justify-between mb-2">
                  <span className="badge bg-violet-500/20 text-violet-300 border border-violet-500/40 text-xs font-bold">
                    {bg.label}
                  </span>
                  <span className="text-xs text-text-dim">{bg.sql_count} SQLs • ~{formatNumber(bg.exec_count)} execs each</span>
                </div>
                <div className="text-xs font-mono text-text-muted mb-2">
                  Combined elapsed: <span className="text-red-400 font-bold">{formatDuration(bg.combined_elapsed_secs)}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {bg.sql_ids.map((id: string) => (
                    <span key={id} className="badge bg-dark-600 text-accent-cyan border border-dark-500 text-[0.55rem] font-mono">{id}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────
          4. LOAD PROFILE DELTA TABLE
          ──────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between mb-2">
          <div className="section-title mb-0">Load Profile Delta</div>
          <div className="flex items-center gap-3">
            <div className="text-xs text-text-dim font-mono">{load_profile_delta.length} metrics</div>
            <div className="group relative">
              <span className="text-text-dim text-xs cursor-help underline decoration-dotted">Data source</span>
              <div className="hidden group-hover:block absolute right-0 top-6 z-20 w-72 p-3 rounded-lg bg-dark-800 border border-dark-500 shadow-xl text-xs text-text-muted">
                From AWR "Load Profile" section. Per-second and per-transaction rates. Delta % = (bad - good) / good × 100.
              </div>
            </div>
          </div>
        </div>

        {/* Mini bar chart of biggest changes */}
        {loadProfileChartData.length > 0 && (
          <div className="mb-4 bg-dark-800/50 rounded-lg p-3 border border-dark-500">
            <div className="text-xs text-text-muted mb-2 uppercase tracking-widest">Top Changes by Magnitude</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={loadProfileChartData} margin={{ left: 10, right: 10, top: 5, bottom: 5 }}>
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                  angle={-30}
                  textAnchor="end"
                  height={60}
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0d1526',
                    border: '1px solid #1a2744',
                    borderRadius: 8,
                    fontFamily: 'JetBrains Mono',
                    fontSize: 12,
                  }}
                  formatter={(value: number) => [`${formatDelta(value)}`, 'Change']}
                  labelFormatter={(label: string) =>
                    loadProfileChartData.find(d => d.name === label)?.fullName || label
                  }
                />
                <Bar dataKey="change" radius={[4, 4, 0, 0]}>
                  {loadProfileChartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.change > 0 ? '#ef4444' : '#10b981'}
                      fillOpacity={0.8}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="table-header">
                {[
                  { key: 'metric', label: 'Metric' },
                  { key: 'good_value', label: 'Good Period' },
                  { key: 'bad_value', label: 'Bad Period' },
                  { key: 'change_pct', label: 'Change %' },
                  { key: 'severity', label: 'Severity' },
                ].map((col) => (
                  <th
                    key={col.key}
                    className="px-3 py-2 text-left cursor-pointer hover:text-accent-amber transition-colors select-none"
                    onClick={() => handleLpSort(col.key)}
                  >
                    {col.label} {lpSortKey === col.key && (lpSortAsc ? '▲' : '▼')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedLoadProfile.map((row: any, idx: number) => (
                <tr key={idx} className={`table-row ${rowSeverityClass(row.severity)}`}>
                  <td className="px-3 py-2 font-medium text-text-primary">{row.metric}</td>
                  <td className="px-3 py-2 font-mono text-xs text-emerald-400">
                    {typeof row.good_value === 'number' ? formatNumber(row.good_value, 2) : row.good_value ?? '—'}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-red-400">
                    {typeof row.bad_value === 'number' ? formatNumber(row.bad_value, 2) : row.bad_value ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    <DeltaBadge delta={row.change_pct} higherIsWorse={row.higher_is_worse !== false} />
                  </td>
                  <td className="px-3 py-2">
                    <span className={`font-bold text-xs uppercase ${severityColor(row.severity)}`}>
                      {row.severity || '—'}
                    </span>
                  </td>
                </tr>
              ))}
              {sortedLoadProfile.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-text-muted">No load profile data available</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ────────────────────────────────────
          5. WAIT EVENTS COMPARISON
          ──────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="section-title mb-0">Wait Events Comparison</div>
          <div className="group relative">
            <span className="text-text-dim text-xs cursor-help underline decoration-dotted">Data source</span>
            <div className="hidden group-hover:block absolute right-0 top-6 z-20 w-72 p-3 rounded-lg bg-dark-800 border border-dark-500 shadow-xl text-xs text-text-muted">
              From AWR "Top Timed Foreground Events" section. Delta = time_waited_bad - time_waited_good. Pct shows %DB Time contribution.
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          <WaitEventChart
            events={top_wait_events.good || []}
            title="Good Period - Top Wait Events"
          />
          <WaitEventChart
            events={top_wait_events.bad || []}
            title="Bad Period - Top Wait Events"
          />
        </div>

        {/* Extreme Wait Events (IMP8) */}
        {extremeWaits.length > 0 && (
          <div className="mb-4 space-y-2">
            {extremeWaits.map((ew: any, idx: number) => (
              <div key={idx} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30">
                <span className="text-red-400 font-bold text-lg">&#x26A0;</span>
                <span className="text-red-300 text-sm font-bold">Extreme Wait:</span>
                <span className="font-mono text-xs text-red-200">{ew.event_name}</span>
                <span className="text-text-dim text-xs">avg</span>
                <span className="font-mono text-xs text-red-400 font-bold">{(ew.bad_avg_wait_ms / 1000).toFixed(1)}s</span>
                <span className="text-text-dim text-xs">({ew.wait_class})</span>
              </div>
            ))}
          </div>
        )}

        {/* Regressions Table */}
        {(top_wait_events.regressions || []).length > 0 && (
          <div className="card overflow-hidden">
            <div className="flex items-center justify-between mb-2">
              <div className="section-title mb-0">Wait Event Regressions</div>
              <span className="badge bg-red-500/20 text-red-300 border border-red-500/30 text-xs">
                {top_wait_events.regressions.length} events worsened
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="table-header">
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-left">Event Name</th>
                    <th className="px-3 py-2 text-left">Wait Class</th>
                    <th className="px-3 py-2 text-left">Good (s)</th>
                    <th className="px-3 py-2 text-left">Bad (s)</th>
                    <th className="px-3 py-2 text-left">Time Change</th>
                    <th className="px-3 py-2 text-left">Good Avg (ms)</th>
                    <th className="px-3 py-2 text-left">Bad Avg (ms)</th>
                    <th className="px-3 py-2 text-left">Latency Δ</th>
                    <th className="px-3 py-2 text-left">Driver</th>
                    <th className="px-3 py-2 text-left">Root Cause Hint</th>
                  </tr>
                </thead>
                <tbody>
                  {top_wait_events.regressions.map((evt: any, idx: number) => (
                    <tr key={idx} className="table-row">
                      <td className="px-3 py-2">
                        {evt.is_new ? (
                          <span className="badge bg-orange-500/20 text-orange-300 border border-orange-500/40 text-[0.6rem] font-bold">
                            NEW
                          </span>
                        ) : (
                          <span className="badge bg-red-500/20 text-red-300 border border-red-500/40 text-[0.6rem] font-bold">
                            WORSE
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-text-primary font-medium">
                        {evt.event_name}
                        {evt.extreme_wait_flag && (
                          <span className="ml-1.5 badge bg-red-500/30 text-red-300 border-red-500/50 text-[0.5rem] font-bold">EXTREME</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-text-muted">{evt.wait_class}</td>
                      <td className="px-3 py-2 font-mono text-xs text-emerald-400">
                        {evt.good_time != null ? formatDuration(evt.good_time) : '—'}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-red-400">
                        {evt.bad_time != null ? formatDuration(evt.bad_time) : '—'}
                      </td>
                      <td className="px-3 py-2">
                        <DeltaBadge delta={evt.change_pct} />
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-emerald-400">
                        {evt.good_avg_wait_ms != null ? evt.good_avg_wait_ms.toFixed(1) : '—'}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-red-400">
                        {evt.bad_avg_wait_ms != null ? evt.bad_avg_wait_ms.toFixed(1) : '—'}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {evt.latency_delta_pct != null ? (
                          <DeltaBadge delta={evt.latency_delta_pct} />
                        ) : '—'}
                      </td>
                      <td className="px-3 py-2">
                        {evt.latency_flag && LATENCY_FLAG_LABELS[evt.latency_flag] ? (
                          <span className={`badge border text-[0.6rem] font-bold ${LATENCY_FLAG_LABELS[evt.latency_flag].color}`}>
                            {LATENCY_FLAG_LABELS[evt.latency_flag].label}
                          </span>
                        ) : <span className="text-text-dim text-xs">—</span>}
                      </td>
                      <td className="px-3 py-2 text-xs text-text-muted italic max-w-xs">
                        {evt.root_cause_hint || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ────────────────────────────────────
          6. INSTANCE EFFICIENCY COMPARISON
          ──────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between mb-2">
          <div className="section-title mb-0">Instance Efficiency Comparison</div>
          <div className="flex items-center gap-3">
            {(instance_efficiency.alerts || []).length > 0 && (
              <span className="badge bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs">
                {instance_efficiency.alerts.length} threshold alerts
              </span>
            )}
            <div className="group relative">
              <span className="text-text-dim text-xs cursor-help underline decoration-dotted">Data source</span>
              <div className="hidden group-hover:block absolute right-0 top-6 z-20 w-72 p-3 rounded-lg bg-dark-800 border border-dark-500 shadow-xl text-xs text-text-muted">
                From AWR "Instance Efficiency Percentages" section. Buffer/library cache hit ratios, parse %s. Alert fires when delta drops below safe threshold.
              </div>
            </div>
          </div>
        </div>

        {/* Alerts */}
        {(instance_efficiency.alerts || []).length > 0 && (
          <div className="mb-4 space-y-2">
            {instance_efficiency.alerts.map((alert: any, idx: number) => (
              <div
                key={idx}
                className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20"
              >
                <span className="text-amber-400 font-bold">&#x26A0;</span>
                <span className="text-amber-300 font-medium">{alert.metric}:</span>
                <span className="text-text-muted">{alert.message || `Value ${alert.bad_value} crossed threshold ${alert.threshold}`}</span>
              </div>
            ))}
          </div>
        )}

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="table-header">
                {[
                  { key: 'metric', label: 'Metric' },
                  { key: 'good', label: 'Good Period' },
                  { key: 'bad', label: 'Bad Period' },
                  { key: 'delta', label: 'Delta' },
                ].map((col) => (
                  <th
                    key={col.key}
                    className="px-3 py-2 text-left cursor-pointer hover:text-accent-amber transition-colors select-none"
                    onClick={() => handleEffSort(col.key)}
                  >
                    {col.label} {effSortKey === col.key && (effSortAsc ? '▲' : '▼')}
                  </th>
                ))}
                <th className="px-3 py-2 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedEfficiency.map((row, idx) => {
                const isRatio = row.metric.toLowerCase().includes('ratio') || row.metric.toLowerCase().includes('%') || row.metric.toLowerCase().includes('hit') || row.metric.toLowerCase().includes('pct');
                const deltaVal = row.delta;
                const isWorse = isRatio ? deltaVal < -2 : deltaVal > 2;
                const isCritical = isRatio ? deltaVal < -10 : deltaVal > 10;

                return (
                  <tr key={idx} className={`table-row ${isCritical ? 'border-l-2 border-l-red-500 bg-red-500/5' : isWorse ? 'border-l-2 border-l-amber-500 bg-amber-500/5' : ''}`}>
                    <td className="px-3 py-2 font-medium text-text-primary">{row.metric}</td>
                    <td className="px-3 py-2 font-mono text-xs text-emerald-400">
                      {typeof row.good === 'number' ? formatPct(row.good) : row.good ?? '—'}
                    </td>
                    <td className={`px-3 py-2 font-mono text-xs ${isCritical ? 'text-red-400' : isWorse ? 'text-amber-400' : 'text-text-primary'}`}>
                      {typeof row.bad === 'number' ? formatPct(row.bad) : row.bad ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      <DeltaBadge delta={deltaVal} higherIsWorse={!isRatio} />
                    </td>
                    <td className="px-3 py-2">
                      {isCritical ? (
                        <span className="text-red-400 text-xs font-bold uppercase">Critical</span>
                      ) : isWorse ? (
                        <span className="text-amber-400 text-xs font-bold uppercase">Warning</span>
                      ) : (
                        <span className="text-emerald-400 text-xs font-bold uppercase">OK</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {sortedEfficiency.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-text-muted">No efficiency data available</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ────────────────────────────────────
          7. SQL ANALYSIS — Structured Zones
          ──────────────────────────────────── */}

      {/* ZONE A: High-Frequency SQLs (exec/min > 50) */}
      {sqlHighFrequency.length > 0 && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-accent-amber text-sm">⚡</span>
              <div className="section-title mb-0">Zone A — High-Frequency SQL</div>
            </div>
            <div className="group relative">
              <span className="text-text-dim text-xs cursor-help underline decoration-dotted">Why this zone?</span>
              <div className="hidden group-hover:block absolute right-0 top-6 z-20 w-80 p-3 rounded-lg bg-dark-800 border border-dark-500 shadow-xl text-xs text-text-muted">
                SQLs executing &gt;50 times/min. Even small per-exec inefficiency compounds into large total impact at this volume. These are the first to profile.
              </div>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="table-header">
                  <th className="px-3 py-2 text-left">SQL ID</th>
                  <th className="px-3 py-2 text-left">Module</th>
                  <th className="px-3 py-2 text-left">Good /exec (s)</th>
                  <th className="px-3 py-2 text-left">Bad /exec (s)</th>
                  <th className="px-3 py-2 text-left">Exec/min Good</th>
                  <th className="px-3 py-2 text-left">Exec/min Bad</th>
                  <th className="px-3 py-2 text-left">% DB Time</th>
                  <th className="px-3 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {sqlHighFrequency.slice(0, 15).map((sql: any) => (
                  <tr key={sql.sql_id} className="table-row cursor-pointer" onClick={() => setExpandedSql(expandedSql === sql.sql_id ? null : sql.sql_id)}>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-accent-cyan font-bold text-xs">{sql.sql_id}</span>
                        {sql.addm_referenced && <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40 text-[0.5rem]">ADDM</span>}
                        {!sql.text_verified && sql.sql_text_truncated && <span className="text-amber-400 text-[0.5rem]" title="SQL text not verified against full text section">⚠</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-xs text-text-muted truncate max-w-[120px]">{sql.sql_module || '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs text-emerald-400">{sql.good_avg_elapsed?.toFixed(3) || '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400">{sql.bad_avg_elapsed?.toFixed(3) || '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs text-emerald-400">{sql.good_execs_per_min?.toFixed(0)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400 font-bold">{sql.bad_execs_per_min?.toFixed(0)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-text-primary">{sql.bad_elapsed_per_min?.toFixed(1)}</td>
                    <td className="px-3 py-2">
                      <span className={`badge border text-[0.6rem] font-bold ${ASSESSMENT_COLORS[sql.net_assessment] || 'bg-slate-500/20 text-slate-400 border-slate-500/40'}`}>
                        {sql.net_assessment || '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ZONE B: Plan Changes */}
      {sqlPlanChanges.length > 0 && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-blue-400 text-sm">📋</span>
              <div className="section-title mb-0">Zone B — Execution Plan Changes</div>
            </div>
            <span className="badge bg-blue-500/20 text-blue-300 border border-blue-500/40 text-xs">{sqlPlanChanges.length} plan(s) changed</span>
          </div>
          <div className="text-xs text-red-300 mb-3 font-medium">
            {sqlPlanChanges.filter((s: any) => s.plan_verdict?.includes('REGRESSED')).length} plan regression(s): execution plan changed and per-exec time worsened.
            {sqlPlanChanges.filter((s: any) => s.plan_verdict?.includes('IMPROVED')).length > 0 && ` ${sqlPlanChanges.filter((s: any) => s.plan_verdict?.includes('IMPROVED')).length} improved.`}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="table-header">
                  <th className="px-3 py-2 text-left">SQL ID</th>
                  <th className="px-3 py-2 text-left">Good Plan Hash</th>
                  <th className="px-3 py-2 text-left">Bad Plan Hash</th>
                  <th className="px-3 py-2 text-left">Good /exec</th>
                  <th className="px-3 py-2 text-left">Bad /exec</th>
                  <th className="px-3 py-2 text-left">Per-exec Δ</th>
                  <th className="px-3 py-2 text-left">Verdict</th>
                  <th className="px-3 py-2 text-left">Action</th>
                </tr>
              </thead>
              <tbody>
                {sqlPlanChanges.map((sql: any) => (
                  <tr key={sql.sql_id} className={`table-row ${sql.plan_verdict?.includes('REGRESSED') ? 'border-l-2 border-l-red-500 bg-red-500/5' : ''}`}>
                    <td className="px-3 py-2 font-mono text-accent-cyan font-bold text-xs">{sql.sql_id}</td>
                    <td className="px-3 py-2 font-mono text-xs text-text-muted">{sql.good_plan_hash || '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs text-text-primary">{sql.bad_plan_hash || '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs text-emerald-400">{sql.good_avg_elapsed?.toFixed(3)}s</td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400">{sql.bad_avg_elapsed?.toFixed(3)}s</td>
                    <td className="px-3 py-2"><DeltaBadge delta={sql.avg_elapsed_delta_pct} /></td>
                    <td className="px-3 py-2">
                      <span className={`badge border text-[0.6rem] font-bold ${
                        sql.plan_verdict?.includes('REGRESSED') ? 'bg-red-500/20 text-red-300 border-red-500/40' :
                        sql.plan_verdict?.includes('IMPROVED') ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' :
                        'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                      }`}>{sql.plan_verdict}</span>
                    </td>
                    <td className="px-3 py-2 text-xs text-text-muted">
                      {sql.plan_verdict?.includes('REGRESSED') && 'Pin good plan via DBMS_SPM'}
                      {sql.plan_verdict?.includes('IMPROVED') && 'Monitor stability'}
                      {sql.plan_verdict?.includes('STABLE') && 'No action needed'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ZONE C: New SQLs in Bad Period */}
      {sqlNewInBad.length > 0 && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-orange-400 text-sm">🆕</span>
              <div className="section-title mb-0">Zone C — New SQL in Problem Period</div>
            </div>
            <span className="badge bg-orange-500/20 text-orange-300 border border-orange-500/40 text-xs">{sqlNewInBad.length} new SQL(s)</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="table-header">
                  <th className="px-3 py-2 text-left">SQL ID</th>
                  <th className="px-3 py-2 text-left">Source</th>
                  <th className="px-3 py-2 text-left">Module</th>
                  <th className="px-3 py-2 text-left">/exec (s)</th>
                  <th className="px-3 py-2 text-left">Exec/min</th>
                  <th className="px-3 py-2 text-left">Total (s)</th>
                  <th className="px-3 py-2 text-left">Tables</th>
                </tr>
              </thead>
              <tbody>
                {sqlNewInBad.map((sql: any) => (
                  <tr key={sql.sql_id} className="table-row cursor-pointer" onClick={() => setExpandedSql(expandedSql === sql.sql_id ? null : sql.sql_id)}>
                    <td className="px-3 py-2 font-mono text-accent-cyan font-bold text-xs">{sql.sql_id}</td>
                    <td className="px-3 py-2 text-xs text-text-muted">{sql.source_category || '—'}</td>
                    <td className="px-3 py-2 text-xs text-text-muted truncate max-w-[120px]">{sql.sql_module || '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400">{sql.bad_avg_elapsed?.toFixed(3)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400">{sql.bad_execs_per_min?.toFixed(1)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400">{formatDuration(sql.bad_elapsed_secs)}</td>
                    <td className="px-3 py-2 text-xs">
                      {sql.tables_referenced?.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {sql.tables_referenced.slice(0, 3).map((t: string) => (
                            <span key={t} className="badge bg-dark-600 text-text-muted border-dark-400 text-[0.55rem]">{t}</span>
                          ))}
                          {sql.tables_referenced.length > 3 && <span className="text-text-dim text-[0.6rem]">+{sql.tables_referenced.length - 3}</span>}
                        </div>
                      ) : <span className="text-text-dim italic">Truncated in AWR</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Oracle Maintenance SQLs (separated, not mixed with app SQL) */}
      {sqlMaintenance.length > 0 && (
        <div className="card overflow-hidden border-slate-500/20">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 text-sm">⚙</span>
              <div className="section-title mb-0 text-slate-400">Oracle Maintenance SQL</div>
            </div>
            <span className="badge bg-slate-500/20 text-slate-300 border border-slate-500/40 text-xs">{sqlMaintenance.length} maintenance task(s)</span>
          </div>
          <div className="text-xs text-text-dim mb-2">Auto-stats, purges, scheduler jobs — separated from application SQL analysis.</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="table-header">
                  <th className="px-3 py-2 text-left">SQL ID</th>
                  <th className="px-3 py-2 text-left">Module</th>
                  <th className="px-3 py-2 text-left">Total Elapsed</th>
                  <th className="px-3 py-2 text-left">Assessment</th>
                </tr>
              </thead>
              <tbody>
                {sqlMaintenance.map((sql: any) => (
                  <tr key={sql.sql_id} className="table-row">
                    <td className="px-3 py-2 font-mono text-xs text-slate-400">{sql.sql_id}</td>
                    <td className="px-3 py-2 text-xs text-text-muted">{sql.sql_module || '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs text-text-primary">{formatDuration(sql.bad_elapsed_secs)}</td>
                    <td className="px-3 py-2">
                      <span className={`badge border text-[0.6rem] font-bold ${ASSESSMENT_COLORS[sql.net_assessment] || 'bg-slate-500/20 text-slate-400 border-slate-500/40'}`}>
                        {sql.net_assessment || 'Maintenance'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────
          7b. COMPLETE SQL TABLE (collapsible)
          ──────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between mb-3">
          <div className="section-title mb-0">Complete SQL Table</div>
          <div className="text-xs text-text-dim font-mono">{sqlAssessments.length} statements</div>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1 mb-4 bg-dark-800/60 rounded-lg p-1 border border-dark-500 w-fit flex-wrap">
          {[
            { key: 'all', label: 'All' },
            { key: 'new_offender', label: 'New Offender' },
            { key: 'regression', label: 'Regression' },
            { key: 'load_increase', label: 'Load Increase' },
          ].map((tab) => {
            const count = tab.key === 'all'
              ? sqlAssessments.length
              : sqlAssessments.filter((s: any) => s.tag === tab.key).length;
            return (
              <button
                key={tab.key}
                onClick={() => setSqlFilter(tab.key)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                  sqlFilter === tab.key
                    ? 'bg-accent-amber/20 text-accent-amber shadow-sm'
                    : 'text-text-muted hover:text-text-primary hover:bg-dark-700/50'
                }`}
              >
                {tab.label}
                <span className={`ml-1.5 px-1.5 py-0.5 rounded text-[0.6rem] font-mono ${
                  sqlFilter === tab.key ? 'bg-accent-amber/30 text-accent-amber' : 'bg-dark-600 text-text-dim'
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="table-header">
                <th className="px-3 py-2 text-left">SQL ID</th>
                <th className="px-3 py-2 text-left">Tag</th>
                <th className="px-3 py-2 text-left">Source</th>
                <th className="px-3 py-2 text-left">Net Assessment</th>
                <th className="px-3 py-2 text-left">Plan Verdict</th>
                <th className="px-3 py-2 text-left">Good El/min</th>
                <th className="px-3 py-2 text-left">Bad El/min</th>
                <th className="px-3 py-2 text-left">Rows Processed (Good)</th>
                <th className="px-3 py-2 text-left">Rows Processed (Bad)</th>
                <th className="px-3 py-2 text-left">Delta %</th>
                <th className="px-3 py-2 text-left">Exec/min</th>
              </tr>
            </thead>
            <tbody>
              {filteredSql.map((sql: any, idx: number) => (
                <>
                  <tr
                    key={sql.sql_id + idx}
                    className="table-row cursor-pointer"
                    onClick={() => setExpandedSql(expandedSql === sql.sql_id ? null : sql.sql_id)}
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="text-text-dim text-[0.6rem] transition-transform duration-200" style={{ transform: expandedSql === sql.sql_id ? 'rotate(90deg)' : 'rotate(0deg)' }}>
                          &#x25B6;
                        </span>
                        <span className="font-mono text-accent-cyan font-bold text-xs">{sql.sql_id}</span>
                        {sql.is_oracle_maintenance && (
                          <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40 text-[0.5rem] font-bold">MAINT</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`badge border text-[0.6rem] font-bold ${TAG_COLORS[sql.tag] || 'bg-slate-500/20 text-slate-300 border-slate-500/40'}`}> 
                        {TAG_LABELS[sql.tag] || sql.tag || '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-text-muted">
                      {sql.source_category || '—'}
                    </td>
                    <td className="px-3 py-2">
                      {sql.net_assessment ? (
                        <span className={`badge border text-[0.6rem] font-bold ${ASSESSMENT_COLORS[sql.net_assessment] || ASSESSMENT_COLORS['Cannot Determine']}`}
                          title={sql.net_assessment_detail || ''}>
                          {sql.net_assessment}
                        </span>
                      ) : <span className="text-text-dim text-xs">—</span>}
                    </td>
                    <td className="px-3 py-2">
                      {sql.plan_verdict ? (
                        <span className={`badge border text-[0.6rem] font-bold ${PLAN_VERDICT_COLORS[sql.plan_verdict] || 'bg-slate-500/20 text-slate-400 border-slate-500/40'}`}>
                          {sql.plan_verdict}
                        </span>
                      ) : <span className="text-text-dim text-xs">—</span>}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-emerald-400">
                      {sql.good_elapsed_per_min != null ? sql.good_elapsed_per_min.toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400">
                      {sql.bad_elapsed_per_min != null ? sql.bad_elapsed_per_min.toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-emerald-400">
                      {sql.good_rows_processed != null ? formatNumber(sql.good_rows_processed) : '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-red-400">
                      {sql.bad_rows_processed != null ? formatNumber(sql.bad_rows_processed) : '—'}
                    </td>
                    <td className="px-3 py-2">
                      <DeltaBadge delta={sql.delta_pct} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-text-primary">
                      {sql.good_execs_per_min != null && sql.bad_execs_per_min != null
                        ? `${sql.good_execs_per_min.toFixed(1)} / ${sql.bad_execs_per_min.toFixed(1)}`
                        : '—'}
                    </td>
                  </tr>

                  {/* Expanded SQL Detail Panel */}
                  {expandedSql === sql.sql_id && (
                    <tr key={`${sql.sql_id}-expanded`}>
                      <td colSpan={9} className="px-4 py-3 bg-dark-800/60 border-t border-dark-500">
                        <div className="space-y-3">
                          {/* Verification + ADDM badges */}
                          <div className="flex items-center gap-2 flex-wrap">
                            {sql.text_verified && (
                              <span className="badge bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[0.6rem]">✓ Text Verified</span>
                            )}
                            {sql.text_verified === false && sql.sql_text_full && (
                              <span className="badge bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[0.6rem]">⚠ Not Verified</span>
                            )}
                            {sql.addm_referenced && (
                              <span className="badge bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[0.6rem]">Referenced in ADDM</span>
                            )}
                            {sql.tables_referenced?.length > 0 && (
                              <span className="text-text-dim text-xs">Tables:</span>
                            )}
                            {sql.tables_referenced?.map((t: string) => (
                              <span key={t} className="badge bg-dark-600 text-text-muted border-dark-400 text-[0.55rem]">{t}</span>
                            ))}
                          </div>
                          {/* SQL Text */}
                          <div>
                            <div className="text-xs text-text-dim uppercase tracking-widest mb-1">
                              {sql.sql_text_full ? 'Full SQL Text (from AWR Complete List)' : sql.sql_text_truncated ? 'SQL Text (inline, may be truncated)' : 'SQL Text'}
                            </div>
                            <pre className="font-mono text-xs text-text-muted bg-dark-900 rounded-lg p-3 border border-dark-500 overflow-x-auto whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                              {sql.sql_text_full || sql.sql_text_truncated || sql.sql_text || 'Not available in AWR report'}
                            </pre>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
              {filteredSql.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-text-muted">
                    {sqlFilter === 'all' ? 'No SQL regression data available' : `No SQL statements with tag "${sqlFilter}"`}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ────────────────────────────────────
          8. RECOMMENDATIONS PANEL
          ──────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="section-title mb-0">Recommendations</div>
          <div className="flex items-center gap-3">
            <div className="text-xs text-text-dim font-mono">{recommendations.length} actions</div>
            <div className="group relative">
              <span className="text-text-dim text-xs cursor-help underline decoration-dotted">How generated</span>
              <div className="hidden group-hover:block absolute right-0 top-6 z-20 w-80 p-3 rounded-lg bg-dark-800 border border-dark-500 shadow-xl text-xs text-text-muted">
                Generated from rule-based DBA logic applied to comparison deltas. Each recommendation cites the specific metric or SQL that triggered it.
              </div>
            </div>
          </div>
        </div>

        {/* Category breakdown pie + list */}
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
          {/* Pie chart */}
          {recPieData.length > 0 && (
            <div className="card xl:col-span-1">
              <div className="text-xs text-text-muted uppercase tracking-widest mb-2">By Category</div>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={recPieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    innerRadius={40}
                    paddingAngle={2}
                    stroke="none"
                  >
                    {recPieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} fillOpacity={0.8} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0d1526',
                      border: '1px solid #1a2744',
                      borderRadius: 8,
                      fontFamily: 'JetBrains Mono',
                      fontSize: 11,
                    }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono' }}
                    iconSize={8}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Recommendation cards */}
          <div className={`space-y-3 ${recPieData.length > 0 ? 'xl:col-span-3' : 'xl:col-span-4'}`}>
            {[...recommendations]
              .sort((a: any, b: any) => (a.priority ?? 99) - (b.priority ?? 99))
              .map((rec: any, idx: number) => {
                const pStyle = PRIORITY_STYLES[rec.priority] || PRIORITY_STYLES[3];
                return (
                  <div
                    key={idx}
                    className={`card border ${pStyle.bg} transition-all duration-200 hover:scale-[1.005]`}
                  >
                    <div className="flex items-start gap-4">
                      {/* Priority Badge */}
                      <div className="flex-shrink-0 flex flex-col items-center gap-1">
                        <span className={`badge border font-bold text-xs ${pStyle.bg} ${pStyle.text}`}>
                          {pStyle.label}
                        </span>
                        {rec.category && (
                          <span className="text-[0.6rem] text-text-dim uppercase tracking-widest text-center">
                            {rec.category}
                          </span>
                        )}
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="font-bold text-sm text-text-primary mb-1">{rec.finding}</div>
                        <div className="text-xs text-text-muted leading-relaxed mb-2">{rec.action}</div>

                        {/* Impact */}
                        {rec.impact && (
                          <div className="text-xs text-text-dim italic mb-2">
                            <span className="text-text-muted font-medium">Impact:</span> {rec.impact}
                          </div>
                        )}

                        {/* Oracle Fix Command */}
                        {rec.fix_command && (
                          <div className="relative group">
                            <pre className="font-mono text-xs bg-dark-900 rounded-lg p-3 border border-dark-500 overflow-x-auto text-accent-cyan whitespace-pre-wrap break-all">
                              {rec.fix_command}
                            </pre>
                            <button
                              onClick={() => copyToClipboard(rec.fix_command, idx)}
                              className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 px-2 py-1 rounded bg-dark-700 border border-dark-500 text-[0.6rem] text-text-muted hover:text-accent-amber hover:border-accent-amber/30"
                            >
                              {copiedIdx === idx ? 'Copied!' : 'Copy'}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            {recommendations.length === 0 && (
              <div className="card text-center py-8 text-text-muted">
                No recommendations generated for this comparison
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ────────────────────────────────────
          FOOTER SPACER
          ──────────────────────────────────── */}
      <div className="h-8" />
    </div>
  );
}
