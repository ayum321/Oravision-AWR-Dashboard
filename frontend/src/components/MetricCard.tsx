import { formatDelta, deltaColor } from '../utils/formatters';

interface MetricCardProps {
  label: string;
  value: string | number;
  delta?: number;
  unit?: string;
  higherIsWorse?: boolean;
  icon?: React.ReactNode;
}

export default function MetricCard({ label, value, delta, unit = '', higherIsWorse = true, icon }: MetricCardProps) {
  return (
    <div className="kpi-card group">
      {icon && <div className="text-accent-amber mb-1">{icon}</div>}
      <div className="font-mono text-2xl font-bold text-accent-amber">
        {value}{unit && <span className="text-sm text-text-muted ml-1">{unit}</span>}
      </div>
      <div className="text-[0.65rem] text-text-muted uppercase tracking-widest mt-1">{label}</div>
      {delta !== undefined && (
        <div className={`text-xs font-mono mt-1 ${deltaColor(delta, higherIsWorse)}`}>
          {formatDelta(delta)}
        </div>
      )}
    </div>
  );
}
