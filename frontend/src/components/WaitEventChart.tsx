import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface WaitEvent {
  event_name: string;
  time_waited_secs: number;
  pct_db_time: number;
  wait_class: string;
}

interface WaitEventChartProps {
  events: WaitEvent[];
  title?: string;
}

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

export default function WaitEventChart({ events, title }: WaitEventChartProps) {
  const data = events.slice(0, 10).map(e => ({
    name: e.event_name.length > 25 ? e.event_name.substring(0, 25) + '...' : e.event_name,
    fullName: e.event_name,
    pct: e.pct_db_time,
    time: e.time_waited_secs,
    waitClass: e.wait_class,
  }));

  return (
    <div className="card">
      {title && <div className="section-title">{title}</div>}
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} layout="vertical" margin={{ left: 140, right: 20, top: 5, bottom: 5 }}>
          <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
          <YAxis type="category" dataKey="name" tick={{ fill: '#e2e8f0', fontSize: 11, fontFamily: 'JetBrains Mono' }} width={140} />
          <Tooltip
            contentStyle={{ backgroundColor: '#0d1526', border: '1px solid #1a2744', borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 12 }}
            formatter={(value: number, name: string) => [
              name === 'pct' ? `${value.toFixed(1)}% DB Time` : `${value.toFixed(1)}s`,
              name === 'pct' ? '% DB Time' : 'Wait Time',
            ]}
            labelFormatter={(label) => data.find(d => d.name === label)?.fullName || label}
          />
          <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={WAIT_CLASS_COLORS[entry.waitClass] || '#64748b'} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
