import { useState } from 'react';
import { truncateSql, formatNumber, formatDuration } from '../utils/formatters';

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
}

interface SqlTableProps {
  sqls: SqlStat[];
  title?: string;
  onRowClick?: (sql: SqlStat) => void;
}

export default function SqlTable({ sqls, title, onRowClick }: SqlTableProps) {
  const [sortKey, setSortKey] = useState<keyof SqlStat>('elapsed_time_secs');
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...sqls].sort((a, b) => {
    const av = a[sortKey] ?? 0;
    const bv = b[sortKey] ?? 0;
    return sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
  });

  const handleSort = (key: keyof SqlStat) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const headers: { key: keyof SqlStat; label: string }[] = [
    { key: 'sql_id', label: 'SQL ID' },
    { key: 'elapsed_time_secs', label: 'Elapsed' },
    { key: 'cpu_time_secs', label: 'CPU' },
    { key: 'executions', label: 'Execs' },
    { key: 'rows_processed', label: 'Rows Processed' },
    { key: 'buffer_gets', label: 'Gets' },
    { key: 'disk_reads', label: 'Reads' },
    { key: 'avg_elapsed_secs', label: 'Avg Elapsed' },
  ];

  return (
    <div className="card overflow-hidden">
      {title && <div className="section-title">{title}</div>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="table-header">
              {headers.map(h => (
                <th
                  key={h.key}
                  className="px-3 py-2 text-left cursor-pointer hover:text-accent-amber transition-colors"
                  onClick={() => handleSort(h.key)}
                >
                  {h.label} {sortKey === h.key && (sortAsc ? '▲' : '▼')}
                </th>
              ))}
              <th className="px-3 py-2 text-left">SQL Text</th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 20).map((sql, i) => (
              <tr
                key={sql.sql_id + i}
                className="table-row cursor-pointer"
                onClick={() => onRowClick?.(sql)}
              >
                <td className="px-3 py-2 font-mono text-accent-cyan font-bold text-xs">{sql.sql_id}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatDuration(sql.elapsed_time_secs)}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatDuration(sql.cpu_time_secs)}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatNumber(sql.executions)}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatNumber(sql.rows_processed ?? 0)}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatNumber(sql.buffer_gets)}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatNumber(sql.disk_reads)}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatDuration(sql.avg_elapsed_secs)}</td>
                <td className="px-3 py-2 font-mono text-xs text-text-muted max-w-xs truncate">{truncateSql(sql.sql_text || '', 60)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
