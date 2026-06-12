import { useState, useMemo } from 'react';
import { useRecommendations, useComparisonRecommendations } from '../hooks/useAWR';
import { severityColor } from '../utils/formatters';

interface Recommendation {
  priority: number;
  category: string;
  finding: string;
  action: string;
  oracle_fix?: string;
  impact?: string;
  reference?: string;
}

const PRIORITY_MAP: Record<number, { label: string; color: string; bg: string }> = {
  1: { label: 'CRITICAL', color: 'text-red-400', bg: 'bg-red-500/15 border-red-500/40' },
  2: { label: 'HIGH', color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/40' },
  3: { label: 'MEDIUM', color: 'text-cyan-400', bg: 'bg-cyan-500/15 border-cyan-500/40' },
};

const CATEGORY_COLORS: Record<string, string> = {
  Memory: 'bg-purple-500/15 border-purple-500/40 text-purple-400',
  SQL: 'bg-blue-500/15 border-blue-500/40 text-blue-400',
  'I/O': 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400',
  Concurrency: 'bg-red-500/15 border-red-500/40 text-red-400',
  Configuration: 'bg-amber-500/15 border-amber-500/40 text-amber-400',
};

const CATEGORIES = ['All', 'Memory', 'SQL', 'I/O', 'Concurrency', 'Configuration'];
const PRIORITIES = [
  { value: 0, label: 'All' },
  { value: 1, label: 'Critical' },
  { value: 2, label: 'High' },
  { value: 3, label: 'Medium' },
];

export default function Recommendations() {
  const [period, setPeriod] = useState<'good' | 'bad'>('good');
  const [mode, setMode] = useState<'single' | 'comparison'>('single');
  const [filterPriority, setFilterPriority] = useState(0);
  const [filterCategory, setFilterCategory] = useState('All');
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const singleResult = useRecommendations(period);
  const comparisonResult = useComparisonRecommendations();

  const loading = mode === 'single' ? singleResult.loading : comparisonResult.loading;
  const error = mode === 'single' ? singleResult.error : comparisonResult.error;
  const rawData = mode === 'single' ? singleResult.data : comparisonResult.data;

  const recommendations: Recommendation[] = useMemo(() => {
    if (!rawData) return [];
    // Handle both array and object with recommendations key
    const list = Array.isArray(rawData) ? rawData : rawData.recommendations ?? rawData.items ?? [];
    return Array.isArray(list) ? list : [];
  }, [rawData]);

  const filtered = useMemo(() => {
    return recommendations.filter((rec) => {
      if (filterPriority !== 0 && rec.priority !== filterPriority) return false;
      if (filterCategory !== 'All' && rec.category !== filterCategory) return false;
      return true;
    });
  }, [recommendations, filterPriority, filterCategory]);

  const counts = useMemo(() => {
    const c = { critical: 0, high: 0, medium: 0 };
    for (const rec of recommendations) {
      if (rec.priority === 1) c.critical++;
      else if (rec.priority === 2) c.high++;
      else c.medium++;
    }
    return c;
  }, [recommendations]);

  /* ── Loading state ─────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full border-4 border-dark-500" />
          <div className="absolute inset-0 rounded-full border-4 border-t-accent-amber animate-spin" />
        </div>
        <p className="text-text-muted text-sm font-mono tracking-wider uppercase">
          Generating recommendations...
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

      {/* ═══ Period Selector + Mode Toggle ════════════════════ */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Period toggle */}
        <div className="inline-flex rounded-lg border border-dark-500 overflow-hidden">
          <button
            onClick={() => { setPeriod('good'); setMode('single'); }}
            className={`px-4 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              period === 'good' && mode === 'single'
                ? 'bg-accent-green/20 text-accent-green border-r border-dark-500'
                : 'bg-dark-700 text-text-muted hover:text-text-primary border-r border-dark-500'
            }`}
          >
            Good Period
          </button>
          <button
            onClick={() => { setPeriod('bad'); setMode('single'); }}
            className={`px-4 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              period === 'bad' && mode === 'single'
                ? 'bg-red-500/20 text-red-400 border-r border-dark-500'
                : 'bg-dark-700 text-text-muted hover:text-text-primary border-r border-dark-500'
            }`}
          >
            Bad Period
          </button>
          <button
            onClick={() => setMode('comparison')}
            className={`px-4 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              mode === 'comparison'
                ? 'bg-accent-cyan/20 text-accent-cyan'
                : 'bg-dark-700 text-text-muted hover:text-text-primary'
            }`}
          >
            Comparison
          </button>
        </div>

        <span className="text-[0.65rem] text-text-muted font-mono uppercase tracking-widest">
          {mode === 'comparison' ? 'Good vs Bad comparison' : `${period} period`}
        </span>

        {/* Export placeholder */}
        <div className="ml-auto">
          <button className="px-4 py-1.5 rounded-lg bg-dark-600 border border-dark-500 text-text-muted text-xs font-bold uppercase tracking-wider hover:border-accent-cyan hover:text-accent-cyan transition-colors">
            Export
          </button>
        </div>
      </div>

      {/* ═══ Summary Counts ══════════════════════════════════ */}
      <div className="flex flex-wrap gap-3">
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-2.5 flex items-center gap-3">
          <span className="text-red-400 font-mono text-xl font-black">{counts.critical}</span>
          <span className="text-[0.6rem] text-red-300 uppercase tracking-widest font-bold">Critical</span>
        </div>
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-2.5 flex items-center gap-3">
          <span className="text-amber-400 font-mono text-xl font-black">{counts.high}</span>
          <span className="text-[0.6rem] text-amber-300 uppercase tracking-widest font-bold">High</span>
        </div>
        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-xl px-4 py-2.5 flex items-center gap-3">
          <span className="text-cyan-400 font-mono text-xl font-black">{counts.medium}</span>
          <span className="text-[0.6rem] text-cyan-300 uppercase tracking-widest font-bold">Medium</span>
        </div>
        <div className="bg-dark-700/60 border border-dark-500 rounded-xl px-4 py-2.5 flex items-center gap-3">
          <span className="text-text-primary font-mono text-xl font-black">{recommendations.length}</span>
          <span className="text-[0.6rem] text-text-muted uppercase tracking-widest font-bold">Total</span>
        </div>
      </div>

      {/* ═══ Filters ═════════════════════════════════════════ */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Priority filter */}
        <div>
          <span className="text-[0.6rem] text-text-muted uppercase tracking-widest mr-2">Priority:</span>
          <div className="inline-flex rounded-lg border border-dark-500 overflow-hidden">
            {PRIORITIES.map(p => (
              <button
                key={p.value}
                onClick={() => setFilterPriority(p.value)}
                className={`px-3 py-1 text-xs font-bold transition-colors border-r border-dark-500 last:border-r-0 ${
                  filterPriority === p.value
                    ? 'bg-accent-cyan/15 text-accent-cyan'
                    : 'bg-dark-700 text-text-muted hover:text-text-primary'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Category filter */}
        <div>
          <span className="text-[0.6rem] text-text-muted uppercase tracking-widest mr-2">Category:</span>
          <div className="inline-flex rounded-lg border border-dark-500 overflow-hidden">
            {CATEGORIES.map(cat => (
              <button
                key={cat}
                onClick={() => setFilterCategory(cat)}
                className={`px-3 py-1 text-xs font-bold transition-colors border-r border-dark-500 last:border-r-0 ${
                  filterCategory === cat
                    ? 'bg-accent-cyan/15 text-accent-cyan'
                    : 'bg-dark-700 text-text-muted hover:text-text-primary'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ═══ Recommendation Cards ════════════════════════════ */}
      {filtered.length > 0 ? (
        <div className="space-y-3">
          {filtered.map((rec, i) => {
            const isExpanded = expandedIdx === i;
            const priorityInfo = PRIORITY_MAP[rec.priority] ?? PRIORITY_MAP[3];
            const categoryStyle = CATEGORY_COLORS[rec.category] ?? 'bg-dark-600 border-dark-500 text-text-muted';

            return (
              <div
                key={i}
                className={`border rounded-xl overflow-hidden transition-all ${
                  isExpanded ? 'border-dark-400 bg-dark-700/80' : 'border-dark-500 bg-dark-700/40 hover:border-dark-400'
                }`}
              >
                {/* Card Header (always visible) */}
                <button
                  onClick={() => setExpandedIdx(isExpanded ? null : i)}
                  className="w-full flex items-start gap-3 px-5 py-4 text-left"
                >
                  {/* Expand indicator */}
                  <span className="text-text-muted text-xs mt-0.5 flex-shrink-0 w-4 text-center font-mono">
                    {isExpanded ? '-' : '+'}
                  </span>

                  {/* Priority badge */}
                  <span className={`flex-shrink-0 px-2.5 py-0.5 rounded-md text-[0.6rem] font-black uppercase tracking-wider border ${priorityInfo.bg}`}>
                    <span className={priorityInfo.color}>{priorityInfo.label}</span>
                  </span>

                  {/* Category badge */}
                  <span className={`flex-shrink-0 px-2.5 py-0.5 rounded-md text-[0.6rem] font-bold uppercase tracking-wider border ${categoryStyle}`}>
                    {rec.category}
                  </span>

                  {/* Finding text */}
                  <span className="flex-1 text-sm text-text-primary leading-relaxed min-w-0">
                    {rec.finding}
                  </span>
                </button>

                {/* Expanded Content */}
                {isExpanded && (
                  <div className="px-5 pb-5 pt-0 ml-7 space-y-4 border-t border-dark-500 mt-0 pt-4">
                    {/* Action */}
                    <div>
                      <div className="text-[0.6rem] text-text-muted uppercase tracking-widest mb-1.5">Recommended Action</div>
                      <p className="text-sm text-text-primary leading-relaxed">{rec.action}</p>
                    </div>

                    {/* Oracle Fix */}
                    {rec.oracle_fix && (
                      <div>
                        <div className="text-[0.6rem] text-text-muted uppercase tracking-widest mb-1.5">Oracle Fix</div>
                        <pre className="bg-dark-900 border border-dark-500 rounded-xl p-4 text-xs font-mono text-accent-cyan overflow-x-auto whitespace-pre-wrap break-words leading-relaxed">
                          {rec.oracle_fix}
                        </pre>
                      </div>
                    )}

                    {/* Impact */}
                    {rec.impact && (
                      <div>
                        <div className="text-[0.6rem] text-text-muted uppercase tracking-widest mb-1.5">Expected Impact</div>
                        <p className="text-sm text-emerald-300/80 leading-relaxed">{rec.impact}</p>
                      </div>
                    )}

                    {/* Reference */}
                    {rec.reference && (
                      <div>
                        <div className="text-[0.6rem] text-text-muted uppercase tracking-widest mb-1.5">Reference</div>
                        <a
                          href={rec.reference}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs font-mono text-accent-cyan hover:text-accent-amber transition-colors underline underline-offset-2"
                        >
                          {rec.reference}
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card text-center py-12">
          <p className="text-text-muted text-sm font-mono">
            {recommendations.length === 0
              ? 'No recommendations available for this period.'
              : 'No recommendations match the selected filters.'}
          </p>
        </div>
      )}
    </div>
  );
}
