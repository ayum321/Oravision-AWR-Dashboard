import { useState } from 'react';
import { useDashboard } from '../hooks/useAWR';
import MetricCard from '../components/MetricCard';
import HealthScoreMeter from '../components/HealthScoreMeter';
import WaitEventChart from '../components/WaitEventChart';
import SqlTable from '../components/SqlTable';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { formatNumber, formatPct, formatDuration } from '../utils/formatters';

const LOAD_PROFILE_COLORS = [
  '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6',
  '#ef4444', '#14b8a6', '#f97316', '#6366f1',
  '#ec4899', '#64748b',
];

export default function Dashboard() {
  const [period, setPeriod] = useState<'good' | 'bad'>('good');
  const [retryCount, setRetryCount] = useState(0);
  const { data, loading, error } = useDashboard(period, retryCount);

  /* ── Loading state ─────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full border-4 border-dark-500" />
          <div className="absolute inset-0 rounded-full border-4 border-t-accent-amber animate-spin" />
        </div>
        <p className="text-text-muted text-sm font-mono tracking-wider uppercase">
          Loading AWR snapshot data...
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
          onClick={() => setRetryCount(c => c + 1)}
          className="px-4 py-2 rounded-lg bg-dark-600 border border-dark-500 text-text-muted text-xs hover:border-accent-amber hover:text-accent-amber transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const { db_info, snap_range, health, kpis, load_profile, wait_events, top_sql } = data;

  /* ── Derived values ────────────────────────────────────────── */
  const healthScore = health?.score ?? 0;
  const healthGrade = health?.grade ?? '—';
  const healthSeverity = health?.severity ?? 'unknown';
  const healthAlerts: { message: string; severity: string }[] = health?.alerts ?? [];

  const loadProfileData = (load_profile ?? []).map((m: any) => ({
    name: m.stat_name ?? m.metric ?? m.name ?? '',
    perSec: m.per_sec ?? m.per_second ?? m.perSec ?? 0,
    perTxn: m.per_txn ?? m.per_transaction ?? m.perTxn ?? 0,
  }));

  return (
    <div className="space-y-6">

      {/* ═══ Period Selector Toggle ═══════════════════════════ */}
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
          Viewing: {period} period
        </span>
      </div>

      {/* ═══ 1. Connection Info Bar ═══════════════════════════ */}
      <div className="bg-dark-700/60 border border-dark-500 rounded-xl px-5 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
        <InfoPill label="Database" value={db_info?.db_name} accent />
        <InfoPill label="Instance" value={db_info?.instance} />
        <InfoPill label="Host" value={db_info?.host} />
        <InfoPill label="Release" value={db_info?.release} />
        <InfoPill label="CPUs" value={db_info?.cpus} />
        <InfoPill label="Memory" value={db_info?.memory_gb ? `${db_info.memory_gb} GB` : '—'} />
        <div className="w-px h-6 bg-dark-500 mx-1" />
        <InfoPill
          label="Snap Range"
          value={`${snap_range?.begin_snap ?? '—'} → ${snap_range?.end_snap ?? '—'}`}
        />
        <InfoPill label="Elapsed" value={snap_range?.elapsed_min ? `${formatNumber(snap_range.elapsed_min, 1)} min` : '—'} />
        <InfoPill label="DB Time" value={snap_range?.db_time_min ? `${formatNumber(snap_range.db_time_min, 1)} min` : '—'} accent />
      </div>

      {/* ═══ 2. KPI Cards Row ═════════════════════════════════ */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="DB Time"
          value={formatDuration(kpis?.db_time_secs ?? 0)}
          icon={<span className="text-lg">&#9201;</span>}
        />
        <MetricCard
          label="Avg Active Sessions"
          value={formatNumber(kpis?.aas ?? 0, 2)}
          higherIsWorse
          icon={<span className="text-lg">&#9881;</span>}
        />
        <MetricCard
          label="Buffer Cache Hit %"
          value={formatPct(kpis?.buffer_cache_hit ?? 0)}
          higherIsWorse={false}
          icon={<span className="text-lg">&#9670;</span>}
        />
        <MetricCard
          label="Soft Parse %"
          value={formatPct(kpis?.soft_parse ?? 0)}
          higherIsWorse={false}
          icon={<span className="text-lg">&#10697;</span>}
        />
      </div>

      {/* ═══ 3. Health Score Section ══════════════════════════ */}
      <div className="card">
        <div className="section-title">Database Health</div>
        <div className="flex flex-col md:flex-row items-center md:items-start gap-8 py-4">
          {/* Meter */}
          <div className="relative flex-shrink-0">
            <HealthScoreMeter score={healthScore} size={160} />
          </div>

          {/* Grade & severity summary */}
          <div className="flex-1 space-y-4 min-w-0">
            <div className="flex items-center gap-4">
              <span className={`font-mono text-4xl font-black ${
                healthScore >= 80 ? 'text-emerald-400' : healthScore >= 50 ? 'text-amber-400' : 'text-red-400'
              }`}>
                {healthGrade}
              </span>
              <div>
                <div className="text-sm text-text-primary font-bold">{healthSeverity}</div>
                <div className="text-xs text-text-muted">
                  Score: <span className="font-mono text-accent-cyan">{healthScore}</span> / 100
                </div>
              </div>
            </div>

            {/* Alerts */}
            {healthAlerts.length > 0 && (
              <div className="space-y-2">
                <div className="text-[0.65rem] text-text-muted uppercase tracking-widest">Alerts</div>
                <ul className="space-y-1.5">
                  {healthAlerts.map((alert, i) => (
                    <li
                      key={i}
                      className={`flex items-start gap-2 text-xs px-3 py-2 rounded-lg border ${
                        alert.severity === 'critical'
                          ? 'bg-red-500/10 border-red-500/30 text-red-300'
                          : alert.severity === 'warning'
                          ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                          : 'bg-cyan-500/10 border-cyan-500/30 text-cyan-300'
                      }`}
                    >
                      <span className="mt-0.5 flex-shrink-0">
                        {alert.severity === 'critical' ? '!!' : alert.severity === 'warning' ? '!' : 'i'}
                      </span>
                      <span className="font-mono">{alert.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══ 4. Top Wait Events Chart ════════════════════════ */}
      {wait_events && wait_events.length > 0 && (
        <WaitEventChart events={wait_events} title="Top Wait Events" />
      )}

      {/* ═══ 5. Load Profile Section ═════════════════════════ */}
      {loadProfileData.length > 0 && (
        <div className="card">
          <div className="section-title">Load Profile (Per Second)</div>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart
              data={loadProfileData}
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
                formatter={(value: number) => [formatNumber(value, 2), 'Per Second']}
              />
              <Bar dataKey="perSec" radius={[4, 4, 0, 0]}>
                {loadProfileData.map((_: any, i: number) => (
                  <Cell key={i} fill={LOAD_PROFILE_COLORS[i % LOAD_PROFILE_COLORS.length]} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ═══ 6. Top SQL Table ════════════════════════════════ */}
      {top_sql && top_sql.length > 0 && (
        <SqlTable sqls={top_sql} title="Top SQL Statements" />
      )}
    </div>
  );
}

/* ── Tiny helper for the connection info bar ─────────────────── */
function InfoPill({ label, value, accent = false }: { label: string; value?: string | number; accent?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[0.6rem] text-text-muted uppercase tracking-widest">{label}:</span>
      <span className={`font-mono text-xs font-bold ${accent ? 'text-accent-cyan' : 'text-text-primary'}`}>
        {value ?? '—'}
      </span>
    </div>
  );
}
