import { formatDelta, deltaColor } from '../utils/formatters';

interface DeltaBadgeProps {
  delta: number;
  higherIsWorse?: boolean;
  className?: string;
}

export default function DeltaBadge({ delta, higherIsWorse = true, className = '' }: DeltaBadgeProps) {
  if (delta === null || delta === undefined || isNaN(delta)) return <span className="text-text-muted">—</span>;

  const color = deltaColor(delta, higherIsWorse);
  const isRegression = higherIsWorse ? delta > 0 : delta < 0;
  const bgClass = isRegression
    ? Math.abs(delta) > 100 ? 'bg-red-500/15 border border-red-500/30' : 'bg-amber-500/15 border border-amber-500/30'
    : 'bg-emerald-500/15 border border-emerald-500/30';

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-bold ${color} ${bgClass} ${className}`}>
      {delta > 0 ? '▲' : delta < 0 ? '▼' : '—'} {formatDelta(delta)}
    </span>
  );
}
