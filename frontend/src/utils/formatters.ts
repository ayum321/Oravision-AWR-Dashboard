/**
 * Formatting utilities for AWR metrics display.
 */

export function formatNumber(n: number, decimals = 0): string {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPct(n: number, decimals = 1): string {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return `${n.toFixed(decimals)}%`;
}

export function formatDelta(n: number, decimals = 1): string {
  if (n === null || n === undefined || isNaN(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(decimals)}%`;
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

export function formatDuration(secs: number): string {
  if (secs < 1) return `${(secs * 1000).toFixed(1)}ms`;
  if (secs < 60) return `${secs.toFixed(1)}s`;
  if (secs < 3600) return `${(secs / 60).toFixed(1)}m`;
  return `${(secs / 3600).toFixed(1)}h`;
}

export function formatMs(ms: number): string {
  if (ms < 0.01) return `${(ms * 1000).toFixed(1)}μs`;
  if (ms < 1) return `${ms.toFixed(3)}ms`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function severityColor(severity: string): string {
  switch (severity?.toLowerCase()) {
    case 'critical':
    case 'fail':
      return 'text-red-400';
    case 'warning':
    case 'warn':
    case 'degraded':
      return 'text-amber-400';
    case 'good':
    case 'healthy':
    case 'pass':
      return 'text-emerald-400';
    default:
      return 'text-cyan-400';
  }
}

export function severityBg(severity: string): string {
  switch (severity?.toLowerCase()) {
    case 'critical':
    case 'fail':
      return 'bg-red-500/10 border-red-500/30';
    case 'warning':
    case 'warn':
    case 'degraded':
      return 'bg-amber-500/10 border-amber-500/30';
    case 'good':
    case 'healthy':
    case 'pass':
      return 'bg-emerald-500/10 border-emerald-500/30';
    default:
      return 'bg-cyan-500/10 border-cyan-500/30';
  }
}

export function deltaColor(delta: number, higherIsWorse = true): string {
  if (Math.abs(delta) < 5) return 'text-text-dim';
  if (higherIsWorse) {
    return delta > 0 ? 'text-red-400' : 'text-emerald-400';
  }
  return delta < 0 ? 'text-red-400' : 'text-emerald-400';
}

export function gradeColor(grade: string): string {
  switch (grade) {
    case 'A': return 'text-emerald-400';
    case 'B': return 'text-cyan-400';
    case 'C': return 'text-amber-400';
    case 'D': return 'text-orange-400';
    case 'F': return 'text-red-400';
    default: return 'text-text-dim';
  }
}

export function truncateSql(sql: string, maxLen = 80): string {
  if (!sql) return '';
  return sql.length > maxLen ? sql.substring(0, maxLen) + '...' : sql;
}
