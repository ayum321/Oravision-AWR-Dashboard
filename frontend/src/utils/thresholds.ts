/**
 * Oracle AWR metric thresholds — defines good/bad ranges for all metrics.
 */

export interface ThresholdRule {
  metric: string;
  critical: number;
  warning: number;
  good: number;
  higherIsWorse: boolean;
  unit: string;
  category: string;
}

export const THRESHOLDS: ThresholdRule[] = [
  { metric: 'Buffer Cache Hit Ratio', critical: 90, warning: 95, good: 99, higherIsWorse: false, unit: '%', category: 'Memory' },
  { metric: 'Library Cache Hit Ratio', critical: 90, warning: 95, good: 99, higherIsWorse: false, unit: '%', category: 'Memory' },
  { metric: 'Soft Parse Ratio', critical: 85, warning: 95, good: 98, higherIsWorse: false, unit: '%', category: 'Parse' },
  { metric: 'Execute to Parse Ratio', critical: 60, warning: 75, good: 90, higherIsWorse: false, unit: '%', category: 'Parse' },
  { metric: 'Latch Hit Ratio', critical: 98, warning: 99, good: 99.5, higherIsWorse: false, unit: '%', category: 'Concurrency' },
  { metric: 'Hard Parses per Second', critical: 100, warning: 30, good: 10, higherIsWorse: true, unit: '/s', category: 'Parse' },
  { metric: 'Physical Reads per Second', critical: 10000, warning: 5000, good: 1000, higherIsWorse: true, unit: '/s', category: 'I/O' },
  { metric: 'CPU Busy Percent', critical: 90, warning: 80, good: 50, higherIsWorse: true, unit: '%', category: 'CPU' },
  { metric: 'Log File Sync Avg Wait', critical: 20, warning: 10, good: 3, higherIsWorse: true, unit: 'ms', category: 'I/O' },
  { metric: 'DB File Sequential Read Avg', critical: 20, warning: 10, good: 5, higherIsWorse: true, unit: 'ms', category: 'I/O' },
];

export function evaluateMetric(value: number, rule: ThresholdRule): 'critical' | 'warning' | 'good' | 'ok' {
  if (rule.higherIsWorse) {
    if (value >= rule.critical) return 'critical';
    if (value >= rule.warning) return 'warning';
    if (value <= rule.good) return 'good';
    return 'ok';
  } else {
    if (value <= rule.critical) return 'critical';
    if (value <= rule.warning) return 'warning';
    if (value >= rule.good) return 'good';
    return 'ok';
  }
}

export function getThresholdColor(value: number, rule: ThresholdRule): string {
  const level = evaluateMetric(value, rule);
  switch (level) {
    case 'critical': return '#ef4444';
    case 'warning': return '#f59e0b';
    case 'good': return '#10b981';
    default: return '#22d3ee';
  }
}
