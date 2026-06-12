interface HealthScoreMeterProps {
  score: number;
  label?: string;
  size?: number;
}

export default function HealthScoreMeter({ score, label = 'Health Score', size = 140 }: HealthScoreMeterProps) {
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (Math.max(0, Math.min(100, score)) / 100) * circumference;

  const color = score >= 80 ? '#10b981' : score >= 50 ? '#f59e0b' : '#ef4444';
  const grade = score >= 90 ? 'A' : score >= 80 ? 'B' : score >= 60 ? 'C' : score >= 40 ? 'D' : 'F';
  const severity = score >= 80 ? 'Healthy' : score >= 50 ? 'Degraded' : 'Critical';

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="#1a2744" strokeWidth="8"
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center" style={{ width: size, height: size }}>
        <span className="font-mono text-3xl font-bold" style={{ color }}>{score}</span>
        <span className="text-xs font-bold" style={{ color }}>{grade}</span>
      </div>
      <div className="mt-2 text-center">
        <div className="text-[0.65rem] text-text-muted uppercase tracking-widest">{label}</div>
        <div className="text-xs font-bold mt-0.5" style={{ color }}>{severity}</div>
      </div>
    </div>
  );
}
