import { useState, useMemo } from 'react';
import { useWaitEvents } from '../hooks/useAWR';
import WaitEventChart from '../components/WaitEventChart';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend, BarChart, Bar, XAxis, YAxis } from 'recharts';
import { formatNumber, formatDuration, formatPct } from '../utils/formatters';

const WAIT_CLASS_COLORS: Record<string, string> = {
  'CPU': '#f59e0b',
  'User I/O': '#3b82f6',
  'System I/O': '#6366f1',
  'Concurrency': '#ef4444',
  'Application': '#f97316',
  'Commit': '#14b8a6',
  'Network': '#8b5cf6',
  'Configuration': '#ec4899',
  'Other': '#64748b',
};

const DEFAULT_COLOR = '#64748b';

export default function WaitEvents() {
  const [period, setPeriod] = useState<'good' | 'bad'>('good');
  const { data, loading, error } = useWaitEvents(period);

  /* ── Derived data ──────────────────────────────────────────── */
  const waitEvents = data?.wait_events ?? [];
  const rawWaitClasses = data?.wait_classes ?? [];
  const timeModel = data?.time_model ?? [];
  const ashSummary = data?.ash_summary ?? [];

  /* ── Wait class aggregation for donut chart ────────────────── */
  const waitClassData = useMemo(() => {
    const parseMetric = (value: unknown): number => {
      if (typeof value === 'number') return value;
      if (typeof value !== 'string') return 0;
      const parsed = Number(value.replace(/,/g, '').replace(/%/g, '').trim());
      return Number.isFinite(parsed) ? parsed : 0;
    };

    if (Array.isArray(rawWaitClasses) && rawWaitClasses.length > 0) {
      const normalized = rawWaitClasses
        .map((row: any) => {
          const name =
            row.wait_class ??
            row['Wait Class'] ??
            row['wait class'] ??
            row.Class ??
            'Other';
          const value =
            parseMetric(row.time_waited_secs) ||
            parseMetric(row['Total Wait Time (sec)']) ||
            parseMetric(row['Total Wait Time (s)']) ||
            parseMetric(row['Wait Time (s)']) ||
            parseMetric(row['DB Time (s)']);
          const pct =
            parseMetric(row.pct_db_time) ||
            parseMetric(row['% DB time']) ||
            parseMetric(row['% DB Time']) ||
            parseMetric(row['Pct DB Time']);
          return { name, value, pct };
        })
        .filter((row: any) => row.name && row.value > 0);

      if (normalized.length > 0) {
        return normalized.sort((a: any, b: any) => b.value - a.value);
      }
    }

    const classMap: Record<string, number> = {};
    for (const evt of waitEvents) {
      const cls = evt.wait_class || 'Other';
      classMap[cls] = (classMap[cls] || 0) + (evt.time_waited_secs ?? 0);
    }
    return Object.entries(classMap)
      .map(([name, value]) => ({ name, value, pct: 0 }))
      .sort((a, b) => b.value - a.value);
  }, [rawWaitClasses, waitEvents]);

  /* ── Loading state ─────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full border-4 border-dark-500" />
          <div className="absolute inset-0 rounded-full border-4 border-t-accent-amber animate-spin" />
        </div>
        <p className="text-text-muted text-sm font-mono tracking-wider uppercase">
          Loading wait event data...
        </p>
      </div>
    );
  }

  /* ── Error state ───────────────────────────────────────────── */
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="w-14 h-14 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
          <span className="text-red-400 text-2xl">!</span>
        </div>
        <p className="text-red-400 font-mono text-sm">{error}</p>
        <button
          onClick={() => setPeriod(period)}
          className="px-4 py-2 rounded-lg bg-dark-600 border border-dark-500 text-text-muted text-xs hover:border-accent-amber hover:text-accent-amber transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">

      {/* ═══ Period Selector ═══════════════════════════════════ */}
      <div className="flex items-center gap-3">
        <div className="inline-flex rounded-lg border border-dark-500 overflow-hidden">
          <button
            onClick={() => setPeriod('good')}
            className={`px-4 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              period === 'good'
                ? 'bg-accent-green/20 text-accent-green border-r border-dark-500'
                : 'bg-dark-700 text-text-muted hover:text-text-primary border-r border-dark-500'
            }`}
          >
            Good Period
          </button>
          <button
            onClick={() => setPeriod('bad')}
            className={`px-4 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              period === 'bad'
                ? 'bg-red-500/20 text-red-400'
                : 'bg-dark-700 text-text-muted hover:text-text-primary'
            }`}
          >
            Bad Period
          </button>
        </div>
        <span className="text-[0.65rem] text-text-muted font-mono uppercase tracking-widest">
          Wait Events: {period} period
        </span>
      </div>

      {/* ═══ Wait Class Donut Chart ══════════════════════════ */}
      {waitClassData.length > 0 && (
        <div className="card">
          <div className="section-title">Wait Class Breakdown</div>
          <div className="flex flex-col lg:flex-row items-center gap-6">
            <ResponsiveContainer width="100%" height={340}>
              <PieChart>
                <Pie
                  data={waitClassData}
                  cx="50%"
                  cy="50%"
                  innerRadius={70}
                  outerRadius={120}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) =>
                    percent > 0.03 ? `${name}: ${(percent * 100).toFixed(1)}%` : ''
                  }
                  labelLine={{ stroke: '#475569', strokeWidth: 1 }}
                >
                  {waitClassData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={WAIT_CLASS_COLORS[entry.name] || DEFAULT_COLOR}
                      fillOpacity={0.85}
                      stroke="transparent"
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0d1526',
                    border: '1px solid #1a2744',
                    borderRadius: 8,
                    fontFamily: 'JetBrains Mono',
                    fontSize: 12,
                  }}
                  formatter={(value: number) => [formatDuration(value), 'Wait Time']}
                />
                <Legend
                  formatter={(value: string) => (
                    <span className="text-xs font-mono text-text-muted">{value}</span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>

            {/* Class summary table */}
            <div className="w-full lg:w-80 flex-shrink-0">
              <table className="w-full text-xs">
                <thead>
                  <tr className="table-header">
                    <th className="px-3 py-2 text-left">Wait Class</th>
                    <th className="px-3 py-2 text-right">Time</th>
                    <th className="px-3 py-2 text-right">%</th>
                  </tr>
                </thead>
                <tbody>
                  {waitClassData.map((cls, i) => {
                    const totalTime = waitClassData.reduce((s, c) => s + c.value, 0);
                    const pct = cls.pct > 0 ? cls.pct : (totalTime > 0 ? (cls.value / totalTime) * 100 : 0);
                    return (
                      <tr key={i} className="table-row">
                        <td className="px-3 py-2 flex items-center gap-2">
                          <div
                            className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                            style={{ backgroundColor: WAIT_CLASS_COLORS[cls.name] || DEFAULT_COLOR }}
                          />
                          <span className="text-text-primary">{cls.name}</span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-text-primary">
                          {formatDuration(cls.value)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-text-muted">
                          {formatPct(pct)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ═══ Top Wait Events Bar Chart ═══════════════════════ */}
      {waitEvents.length > 0 && (
        <WaitEventChart events={waitEvents} title="Top Wait Events (% DB Time)" />
      )}

      {/* ═══ Time Model Statistics ═══════════════════════════ */}
      {timeModel.length > 0 && (
        <div className="card overflow-hidden">
          <div className="section-title">Time Model Statistics</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="table-header">
                  <th className="px-4 py-2.5 text-left">Statistic</th>
                  <th className="px-4 py-2.5 text-right">Time (seconds)</th>
                  <th className="px-4 py-2.5 text-right">% DB Time</th>
                  <th className="px-4 py-2.5 text-left w-48">Distribution</th>
                </tr>
              </thead>
              <tbody>
                {timeModel.map((stat: any, i: number) => (
                  <tr key={i} className="table-row">
                    <td className="px-4 py-2.5 text-text-primary text-xs">{stat.stat_name}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-text-primary">
                      {formatNumber(stat.time_secs ?? stat.value_secs ?? 0, 2)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-accent-cyan">
                      {formatPct(stat.pct_db_time ?? 0)}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="w-full bg-dark-600 rounded-full h-2 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-accent-cyan/60 transition-all"
                          style={{ width: `${Math.min(100, stat.pct_db_time ?? 0)}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ═══ ASH Summary ═════════════════════════════════════ */}
      {ashSummary.length > 0 && (
        <div className="card overflow-hidden">
          <div className="section-title">Active Session History (ASH) Summary</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="table-header">
                  <th className="px-4 py-2.5 text-left">Session State</th>
                  <th className="px-4 py-2.5 text-left">Wait Class</th>
                  <th className="px-4 py-2.5 text-left">Event</th>
                  <th className="px-4 py-2.5 text-right">Samples</th>
                  <th className="px-4 py-2.5 text-right">% of Total</th>
                  <th className="px-4 py-2.5 text-left w-40">Distribution</th>
                </tr>
              </thead>
              <tbody>
                {ashSummary.map((row: any, i: number) => {
                  const stateColor =
                    row.session_state === 'ON CPU'
                      ? 'text-amber-400'
                      : row.session_state === 'WAITING'
                      ? 'text-blue-400'
                      : 'text-text-primary';
                  const waitClassColor =
                    WAIT_CLASS_COLORS[row.wait_class] || DEFAULT_COLOR;
                  return (
                    <tr key={i} className="table-row">
                      <td className={`px-4 py-2.5 font-mono text-xs font-bold ${stateColor}`}>
                        {row.session_state}
                      </td>
                      <td className="px-4 py-2.5 text-xs">
                        <span className="flex items-center gap-2">
                          <div
                            className="w-2 h-2 rounded-sm flex-shrink-0"
                            style={{ backgroundColor: waitClassColor }}
                          />
                          <span className="text-text-primary">{row.wait_class || '—'}</span>
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-text-muted font-mono max-w-xs truncate">
                        {row.event || '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-text-primary">
                        {formatNumber(row.sample_count ?? 0)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-accent-cyan">
                        {formatPct(row.pct ?? 0)}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="w-full bg-dark-600 rounded-full h-2 overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${Math.min(100, row.pct ?? 0)}%`,
                              backgroundColor: waitClassColor,
                              opacity: 0.7,
                            }}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ═══ Empty state ═════════════════════════════════════ */}
      {waitEvents.length === 0 && timeModel.length === 0 && ashSummary.length === 0 && (
        <div className="card text-center py-12">
          <p className="text-text-muted text-sm font-mono">No wait event data available for this period.</p>
        </div>
      )}
    </div>
  );
}
