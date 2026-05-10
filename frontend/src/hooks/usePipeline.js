import { useMemo, useEffect } from 'react';
import { getStatus, runScreener, stopPipeline } from '../api/client';
import { useFetch } from './useFetch';

export const usePipeline = () => {
  const { data: statusData, refetch, loading } = useFetch(getStatus);

  // Manage polling internally based on status
  useEffect(() => {
    const interval = statusData?.status === 'running' ? 5000 : 60000;
    const id = setInterval(refetch, interval);
    return () => clearInterval(id);
  }, [statusData?.status, refetch]);

  const isBusy = useMemo(() => 
    statusData?.status === 'running' || statusData?.status === 'stopping', 
  [statusData]);

  const run = async (limit) => {
    await runScreener(limit);
    refetch();
  };

  const stop = async () => {
    await stopPipeline();
    refetch();
  };

  return {
    status: statusData?.status || 'idle',
    stats: statusData,
    isBusy,
    run,
    stop,
    loading,
    refetch
  };
};
