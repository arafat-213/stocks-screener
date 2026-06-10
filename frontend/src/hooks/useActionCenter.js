import { useFetch } from './useFetch';
import { getActionCenter } from '../api/client';

export const useActionCenter = (interval = 30000) => {
  const { data, loading, error, refetch } = useFetch(getActionCenter, {
    refreshInterval: interval,
  });

  const defaultData = { entry_candidates: [], sl_risk: [], target_near: [] };
  const finalData = data || defaultData;

  return { ...finalData, loading, error, refetch };
};
