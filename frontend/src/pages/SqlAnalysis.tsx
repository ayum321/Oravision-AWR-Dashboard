import { useState } from 'react';
import { useTopSql } from '../hooks/useAWR';
import SqlTable from '../components/SqlTable';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts';
import { formatNumber, formatDuration, formatPct } from '../utils/formatters';

const ORDER_TABS = [
  { key: 'elapsed_time', label: 'Elapsed Time' },
  { key: 'cpu_time', label: 'CPU Time' },
  { key: 'disk_reads', label: 'Physical Reads' },
  { key: 'executions', label: 'Executions' },
  { key: 'buffer_gets', label: 'Buffer Gets' },
];

const BAR_COLORS = [
  '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6',
  '#ef4444', '#14b8a6', '#f97316', '#6366f1',
  '#ec4899', '#64748b',
];

interface SqlStat {
  sql_id: string;
  sql_text?: string;
  executions: number;
  elapsed_time_secs: number;
  cpu_time_secs: number;
  disk_reads: number;
  buffer_gets: number;
  avg_elapsed_secs: number;
  rows_processed?: number;
  rows_per_exec?: number;
}

export default function SqlAnalysis() {
  const [period, setPeriod] = useState<'good' | 'bad'>('good');
  const [orderBy, setOrderBy] = useState('elapsed_time');
  const [selectedSql, setSelectedSql] = useState<SqlStat | null>(null);
  const { data, loading, error } = useTopSql(period, orderBy);

  /* ── Loading state ─────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full border-4 border-dark-500" />
          <div className="absolute inset-0 rounded-full border-4 border-t-accent-amber animate-spin" />
        </div>
        <p className="text-text-muted text-sm font-mono tracking-wider uppercase">
          Loading SQL analysis...
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

  const sqls: SqlStat[] = data?.sql_stats ?? [];

  /* ── Map order key to the SqlStat field for the bar chart ── */
  const metricField = (sql: SqlStat): number => {
    switch (orderBy) {
      case 'elapsed_time': return sql.elapsed_time_secs;
      case 'cpu_time': return sql.cpu_time_secs;
      case 'disk_reads': return sql.disk_reads;
      case 'executions': return sql.executions;
      case 'buffer_gets': return sql.buffer_gets;
      default: return sql.elapsed_time_secs;
    }
  };

  const metricLabel = ORDER_TABS.find(t => t.key === orderBy)?.label ?? 'Elapsed Time';

  const chartData = sqls.slice(0, 10).map(sql => ({
    name: sql.sql_id,
    value: metricField(sql),
  }));

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
          SQL Analysis: {period} period
        </span>
      </div>

      {/* ═══ Metric Tab Bar ═══════════════════════════════════ */}
      <div className="flex flex-wrap gap-1 bg-dark-700/60 border border-dark-500 rounded-xl p-1.5">
        {ORDER_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setOrderBy(tab.key)}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${
              orderBy === tab.key
                ? 'bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30 shadow-lg shadow-accent-cyan/5'
                : 'text-text-muted hover:text-text-primary hover:bg-dark-600'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ═══ Top 10 Bar Chart ════════════════════════════════ */}
      {chartData.length > 0 && (
        <div className="card">
          <div className="section-title">Top 10 SQL by {metricLabel}</div>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart
              data={chartData}
              margin={{ top: 10, right: 20, left: 10, bottom: 40 }}
            >
              <XAxis
                dataKey="name"
                tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                angle={-35}
                textAnchor="end"
                interval={0}
                height={70}
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'JetBrains Mono' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0d1526',
                  border: '1px solid #1a2744',
                  borderRadius: 8,
                  fontFamily: 'JetBrains Mono',
                  fontSize: 12,
                }}
                formatter={(value: number) => {
                  if (orderBy === 'elapsed_time' || orderBy === 'cpu_time') {
                    return [formatDuration(value), metricLabel];
                  }
                  return [formatNumber(value), metricLabel];
                }}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ═══ SQL Table ═══════════════════════════════════════ */}
      {sqls.length > 0 ? (
        <SqlTable
          sqls={sqls}
          title="SQL Statements"
          onRowClick={(sql) => setSelectedSql(sql as SqlStat)}
        />
      ) : (
        <div className="card text-center py-12">
          <p className="text-text-muted text-sm font-mono">No SQL data available for this period.</p>
        </div>
      )}

      {/* ═══ Detail Modal ════════════════════════════════════ */}
      {selectedSql && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={() => setSelectedSql(null)}
        >
          <div
            className="bg-dark-800 border border-dark-500 rounded-2xl shadow-2xl w-full max-w-3xl mx-4 max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-dark-500">
              <div className="flex items-center gap-3">
                <span className="text-[0.6rem] text-text-muted uppercase tracking-widest">SQL ID</span>
                <span className="font-mono text-accent-cyan font-bold text-sm">{selectedSql.sql_id}</span>
              </div>
              <button
                onClick={() => setSelectedSql(null)}
                className="w-8 h-8 rounded-lg bg-dark-600 border border-dark-500 flex items-center justify-center text-text-muted hover:text-red-400 hover:border-red-500/30 transition-colors text-sm"
              >
                X
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-6">

              {/* SQL Text */}
              <div>
                <div className="text-[0.65rem] text-text-muted uppercase tracking-widest mb-2">SQL Text</div>
                <pre className="bg-dark-900 border border-dark-500 rounded-xl p-4 text-xs font-mono text-text-primary overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap break-words leading-relaxed">
                  {selectedSql.sql_text || 'SQL text not available'}
                </pre>
              </div>

              {/* Stats Grid */}
              <div>
                <div className="text-[0.65rem] text-text-muted uppercase tracking-widest mb-3">Execution Statistics</div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <StatBlock label="Elapsed Time" value={formatDuration(selectedSql.elapsed_time_secs)} />
                  <StatBlock label="CPU Time" value={formatDuration(selectedSql.cpu_time_secs)} />
                  <StatBlock label="Executions" value={formatNumber(selectedSql.executions)} />
                  <StatBlock label="Rows Processed" value={formatNumber(selectedSql.rows_processed ?? 0)} />
                  <StatBlock label="Rows / Exec" value={formatNumber(selectedSql.rows_per_exec ?? 0, 2)} />
                  <StatBlock label="Buffer Gets" value={formatNumber(selectedSql.buffer_gets)} />
                  <StatBlock label="Physical Reads" value={formatNumber(selectedSql.disk_reads)} />
                  <StatBlock label="Avg Elapsed" value={formatDuration(selectedSql.avg_elapsed_secs)} />
                </div>
              </div>

              {/* Pie Chart: CPU vs I/O */}
              <div>
                <div className="text-[0.65rem] text-text-muted uppercase tracking-widest mb-3">CPU vs I/O Time Breakdown</div>
                <div className="flex items-center justify-center">
                  <ResponsiveContainer width="100%" height={240}>
                    <PieChart>
                      <Pie
                        data={[
                          { name: 'CPU Time', value: selectedSql.cpu_time_secs },
                          { name: 'I/O Time', value: Math.max(0, selectedSql.elapsed_time_secs - selectedSql.cpu_time_secs) },
                        ]}
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={90}
                        paddingAngle={3}
                        dataKey="value"
                        label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(1)}%`}
                      >
                        <Cell fill="#f59e0b" />
                        <Cell fill="#3b82f6" />
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0d1526',
                          border: '1px solid #1a2744',
                          borderRadius: 8,
                          fontFamily: 'JetBrains Mono',
                          fontSize: 12,
                        }}
                        formatter={(value: number) => [formatDuration(value), '']}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex items-center justify-center gap-6 mt-2">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-sm bg-amber-500" />
                    <span className="text-xs text-text-muted font-mono">CPU Time ({formatDuration(selectedSql.cpu_time_secs)})</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-sm bg-blue-500" />
                    <span className="text-xs text-text-muted font-mono">
                      I/O Time ({formatDuration(Math.max(0, selectedSql.elapsed_time_secs - selectedSql.cpu_time_secs))})
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-dark-500 flex justify-end">
              <button
                onClick={() => setSelectedSql(null)}
                className="px-5 py-2 rounded-lg bg-dark-600 border border-dark-500 text-text-muted text-xs font-bold uppercase tracking-wider hover:border-accent-cyan hover:text-accent-cyan transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Tiny stat block for the modal ───────────────────────────── */
function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-dark-700/60 border border-dark-500 rounded-xl px-4 py-3">
      <div className="text-[0.6rem] text-text-muted uppercase tracking-widest mb-1">{label}</div>
      <div className="font-mono text-sm font-bold text-text-primary">{value}</div>
    </div>
  );
}
