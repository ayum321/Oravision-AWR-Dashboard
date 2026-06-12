/**
 * React hooks for fetching AWR data from the FastAPI backend.
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_BASE = '/api';

export function useApiGet<T>(url: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    axios
      .get(`${API_BASE}${url}`)
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'API request failed');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, deps);

  return { data, loading, error };
}

export function useDashboard(period: string, retryCount: number = 0) {
  return useApiGet<any>(`/overview/${period}`, [period, retryCount]);
}

export function useComparison() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const compare = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/compare/mock`);
      // Pass the full response — report, advanced analytics, health, recommendations
      setData(res.data);
    } catch (err: any) {
      setError(err.message || 'Comparison failed');
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, compare };
}

export function useTopSql(period: string, orderBy = 'elapsed_time') {
  return useApiGet<any>(`/sql/top/${period}?order_by=${orderBy}`, [period, orderBy]);
}

export function useWaitEvents(period: string) {
  return useApiGet<any>(`/waits/${period}`, [period]);
}

export function useHealthScore(period: string) {
  return useApiGet<any>(`/compare/health/${period}`, [period]);
}

export function useRecommendations(period: string) {
  return useApiGet<any>(`/recommendations/${period}`, [period]);
}

export function useComparisonRecommendations() {
  return useApiGet<any>('/recommendations/compare/good-vs-bad', []);
}

export async function uploadAwrFile(file: File, label: string): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', label);
  const res = await axios.post(`${API_BASE}/upload/awr`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}
