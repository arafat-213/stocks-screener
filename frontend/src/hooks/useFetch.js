import { useState, useEffect, useCallback, useRef } from 'react';

export const useFetch = (apiFn, options = {}) => {
  const { deps = [], autoFetch = true, refreshInterval = null, onSuccess } = options;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(autoFetch);
  const [error, setError] = useState(null);
  const isMounted = useRef(true);

  // Prevent onSuccess infinite loop
  const onSuccessRef = useRef(onSuccess);
  useEffect(() => { onSuccessRef.current = onSuccess; }, [onSuccess]);

  const fetchData = useCallback(async (...args) => {
    try {
      setLoading(true);
      const res = await apiFn(...args);
      if (isMounted.current) {
        setData(res.data);
        setError(null);
        if (onSuccessRef.current) onSuccessRef.current(res.data);
      }
    } catch (err) {
      if (isMounted.current) setError(err.message || 'An error occurred');
    } finally {
      if (isMounted.current) setLoading(false);
    }
  }, [apiFn]);

  useEffect(() => {
    if (autoFetch) fetchData();
  }, [fetchData, autoFetch, ...deps]);

  // Handle polling directly via setInterval or external trigger
  useEffect(() => {
    if (!refreshInterval) return;
    const interval = typeof refreshInterval === 'function' ? refreshInterval(data) : refreshInterval;
    if (!interval) return;

    const id = setInterval(fetchData, interval);
    return () => clearInterval(id);
  }, [fetchData, refreshInterval, data]);

  useEffect(() => () => { isMounted.current = false; }, []);

  return { data, loading, error, refetch: fetchData, setData };
};
