import { useState, useCallback } from 'react';

const STORAGE_KEY = 'screener_watchlist';

export const useWatchlist = () => {
  const [watchlist, setWatchlist] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });

  const toggle = useCallback((symbol) => {
    setWatchlist((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) {
        next.delete(symbol);
      } else {
        next.add(symbol);
      }
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
      } catch (err) {
        console.warn('Failed to save watchlist to localStorage', err);
      }
      return next;
    });
  }, []);

  const isWatched = useCallback((symbol) => watchlist.has(symbol), [watchlist]);
  const clear = useCallback(() => {
    setWatchlist(new Set());
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return { watchlist, toggle, isWatched, count: watchlist.size, clear };
};
