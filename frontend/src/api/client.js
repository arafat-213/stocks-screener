import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export const fetchResults = (params = {}) =>
  apiClient.get('/dashboard/screener/results', { params }).then(res => res.data);
export const fetchPipelineStatus = () => apiClient.get('/dashboard/pipeline/latest');
export const runScreener = (limit = null) => apiClient.post('/screener/run', { limit });
export const stopPipeline = () => apiClient.post('/pipeline/stop');
export const getLatestReport = () => apiClient.get('/reports/latest');
export const getReportList = () => apiClient.get('/reports');
export const getReportByDate = (date) => apiClient.get(`/reports/${date}`);
export const getStockDetail = (symbol) => apiClient.get(`/stocks/${symbol}`);
export const getScreensList = () => apiClient.get('/screens');
export const getScreenBySlug = (slug, params = {}) =>
  apiClient.get(`/screens/${slug}`, { params });
export const getTopStocks = () => apiClient.get('/stocks/top');
export const getDashboardChanges = () => apiClient.get('/dashboard/changes');
export const getStatus = () => apiClient.get('/pipeline/status');
export const searchStocks = (q) => apiClient.get(`/stocks/search?q=${encodeURIComponent(q)}`);
export const getSectorRotation = () => apiClient.get('/screens/data/sector-rotation');

// Watchlist
export const getWatchlist = () => apiClient.get('/watchlist');
export const addToWatchlist = (data) => apiClient.post('/watchlist', data);
export const updateWatchlistStatus = (symbol, status) => apiClient.patch(`/watchlist/${symbol}`, { status });
export const removeFromWatchlist = (symbol) => apiClient.delete(`/watchlist/${symbol}`);

// Backtest
export const runBacktest    = (config) => apiClient.post('/backtest/run', config);
export const getBacktestRun = (runId)  => apiClient.get(`/backtest/${runId}`);
export const getBacktestRuns = ()      => apiClient.get('/backtest/runs');
export const getBacktestTrades = (runId, params) =>
  apiClient.get(`/backtest/${runId}/trades`, { params });

// Paper Trading
export const getPaperPortfolio = () => apiClient.get('/paper-trading/portfolio');
export const getPaperPending   = () => apiClient.get('/paper-trading/pending');
export const getPaperPositions = () => apiClient.get('/paper-trading/positions');
export const getPaperTrades    = (params) => apiClient.get('/paper-trading/trades', { params });

// Journal
export const getJournalOpen = () => apiClient.get('/journal/open');
export const getJournalClosed = () => apiClient.get('/journal/closed');
export const getJournalStats = () => apiClient.get('/journal/stats');
export const createJournalEntry = (data) => apiClient.post('/journal/', data);
export const closeJournalEntry = (id, data) => apiClient.patch(`/journal/${id}/close`, data);
