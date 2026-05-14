import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';

export const useMarketData = (refreshInterval = 300000) => {
  const [data, setData] = useState({ market_context: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchMarketData = useCallback(async () => {
    try {
      const res = await apiClient.get('/dashboard/market/live');
      setData(res.data);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch market data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMarketData();
    const interval = setInterval(fetchMarketData, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchMarketData, refreshInterval]);

  return { ...data, loading, error, refetch: fetchMarketData };
};
