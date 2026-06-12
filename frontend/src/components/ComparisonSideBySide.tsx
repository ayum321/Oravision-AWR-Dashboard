import HealthScoreMeter from './HealthScoreMeter';
import DeltaBadge from './DeltaBadge';

interface ComparisonSideBySideProps {
  summary: {
    good_period: { label: string; snap_begin: number; snap_end: number; db_time_secs: number };
    bad_period: { label: string; snap_begin: number; snap_end: number; db_time_secs: number };
    health_score_good: number;
    health_score_bad: number;
    overall_regression: string;
    severity: string;
  };
}

export default function ComparisonSideBySide({ summary }: ComparisonSideBySideProps) {
  const scoreDelta = summary.health_score_bad - summary.health_score_good;
  const severityColors: Record<string, string> = {
    healthy: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    degraded: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    critical: 'bg-red-500/15 text-red-400 border-red-500/30',
  };

  return (
    <div className="card">
      <div className="section-title">Overall Health Comparison</div>

      <div className="flex items-center justify-around gap-8 py-4">
        {/* Good Period */}
        <div className="flex flex-col items-center">
          <div className="text-xs text-text-muted uppercase tracking-widest mb-2">
            {summary.good_period.label || 'Good Period'}
          </div>
          <div className="relative">
            <HealthScoreMeter score={summary.health_score_good} label="Baseline" size={150} />
          </div>
          <div className="mt-2 text-xs font-mono text-text-dim">
            Snaps {summary.good_period.snap_begin}–{summary.good_period.snap_end}
          </div>
        </div>

        {/* Delta Indicator */}
        <div className="flex flex-col items-center gap-2">
          <div className={`text-4xl font-mono font-bold ${scoreDelta < -20 ? 'text-red-400' : scoreDelta < -5 ? 'text-amber-400' : 'text-emerald-400'}`}>
            {scoreDelta > 0 ? '+' : ''}{scoreDelta}
          </div>
          <div className="text-xs text-text-muted">point change</div>
          <span className={`badge border ${severityColors[summary.severity] || severityColors.degraded}`}>
            {summary.severity?.toUpperCase()}
          </span>
          {summary.overall_regression && (
            <div className="text-xs text-text-dim mt-1">{summary.overall_regression}</div>
          )}
        </div>

        {/* Bad Period */}
        <div className="flex flex-col items-center">
          <div className="text-xs text-text-muted uppercase tracking-widest mb-2">
            {summary.bad_period.label || 'Problem Period'}
          </div>
          <div className="relative">
            <HealthScoreMeter score={summary.health_score_bad} label="Current" size={150} />
          </div>
          <div className="mt-2 text-xs font-mono text-text-dim">
            Snaps {summary.bad_period.snap_begin}–{summary.bad_period.snap_end}
          </div>
        </div>
      </div>
    </div>
  );
}
