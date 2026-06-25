import { useEffect } from 'react';
import { fetchPaperPipelineStatus, triggerPaperPipeline } from '../api/client';
import { useFetch } from './useFetch';

export const usePaperPipeline = () => {
  const { data, refetch, loading } = useFetch(fetchPaperPipelineStatus);

  // Poll faster when the job is running, slow poll otherwise.
  useEffect(() => {
    const interval = data?.status === 'running' ? 5000 : 30000;
    const id = setInterval(refetch, interval);
    return () => clearInterval(id);
  }, [data?.status, refetch]);

  const trigger = async () => {
    await triggerPaperPipeline();
    refetch();
  };

  return {
    status: data?.status || 'never_run',
    lastProcessedDate: data?.last_processed_date || null,
    goLiveDate: data?.go_live_date || null,
    isRunning: data?.status === 'running',
    trigger,
    loading,
    refetch,
  };
};
