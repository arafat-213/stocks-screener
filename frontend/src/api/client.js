import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export const fetchResults = (params = {}) =>
  apiClient
    .get('/dashboard/screener/results', { params })
    .then((res) => res.data);
export const fetchPipelineStatus = () =>
  apiClient.get('/dashboard/pipeline/latest').then((res) => res.data);
export const runScreener = (limit = null) =>
  apiClient.post('/screener/run', { limit }).then((res) => res.data);
export const stopPipeline = () =>
  apiClient.post('/pipeline/stop').then((res) => res.data);
export const getLatestReport = () =>
  apiClient.get('/reports/latest').then((res) => res.data);
export const getLatestDigest = () =>
  apiClient.get('/reports/digest/latest').then((res) => res.data);
export const getReportList = () =>
  apiClient.get('/reports').then((res) => res.data);
export const getReportByDate = (date) =>
  apiClient.get(`/reports/${date}`).then((res) => res.data);
export const getDigestByDate = (date) =>
  apiClient.get(`/reports/digest/${date}`).then((res) => res.data);
export const getStockDetail = (symbol) =>
  apiClient.get(`/stocks/${symbol}`).then((res) => res.data);
export const getScreensList = () =>
  apiClient.get('/screens').then((res) => res.data);
export const getScreenBySlug = (slug, params = {}) =>
  apiClient.get(`/screens/${slug}`, { params }).then((res) => res.data);
export const getTopStocks = () =>
  apiClient.get('/stocks/top').then((res) => res.data);
export const getDashboardChanges = () =>
  apiClient.get('/dashboard/changes').then((res) => res.data);
export const getActionCenter = () =>
  apiClient.get('/dashboard/action-center').then((res) => res.data);

// --- v2 S3 probation paper book (read-only; specs/v3/11) ---
export const getPaperV2Book = () =>
  apiClient.get('/v2/paper/book').then((res) => res.data);
export const getPaperV2Positions = () =>
  apiClient.get('/v2/paper/positions').then((res) => res.data);
export const getPaperV2Nav = () =>
  apiClient.get('/v2/paper/nav').then((res) => res.data);
export const getPaperV2Parity = () =>
  apiClient.get('/v2/paper/parity').then((res) => res.data);
export const getPaperV2Rebalances = () =>
  apiClient.get('/v2/paper/rebalances').then((res) => res.data);
export const getPaperV2Alerts = ({ limit = 50, kind } = {}) => {
  const params = { limit };
  if (kind) params.kind = kind;
  return apiClient.get('/v2/paper/alerts', { params }).then((res) => res.data);
};

// --- S3 paper pipeline status + manual trigger (System UI) ---
export const fetchPaperPipelineStatus = () =>
  apiClient.get('/v2/paper/pipeline/status').then((res) => res.data);
export const triggerPaperPipeline = () =>
  apiClient.post('/v2/paper/pipeline/run').then((res) => res.data);

export const getStatus = () =>
  apiClient.get('/pipeline/status').then((res) => res.data);
export const searchStocks = (q) =>
  apiClient
    .get(`/stocks/search?q=${encodeURIComponent(q)}`)
    .then((res) => res.data);
export const getSectorRotation = () =>
  apiClient.get('/screens/data/sector-rotation').then((res) => res.data);

// Watchlist
export const getWatchlist = () =>
  apiClient.get('/watchlist').then((res) => res.data);
export const addToWatchlist = (data) =>
  apiClient.post('/watchlist', data).then((res) => res.data);
export const updateWatchlistStatus = (symbol, status) =>
  apiClient.patch(`/watchlist/${symbol}`, { status }).then((res) => res.data);
export const removeFromWatchlist = (symbol) =>
  apiClient.delete(`/watchlist/${symbol}`).then((res) => res.data);

// Backtest
export const runBacktest = (config) =>
  apiClient.post('/backtest/run', config).then((res) => res.data);
export const getBacktestRun = (runId) =>
  apiClient.get(`/backtest/${runId}`).then((res) => res.data);
export const getBacktestRuns = () =>
  apiClient.get('/backtest/runs').then((res) => res.data);
export const getBacktestTrades = (runId, params) =>
  apiClient
    .get(`/backtest/${runId}/trades`, { params })
    .then((res) => res.data);

// Paper Trading
export const getPaperPortfolio = () =>
  apiClient.get('/paper-trading/portfolio').then((res) => res.data);
export const getPaperPending = () =>
  apiClient.get('/paper-trading/pending').then((res) => res.data);
export const getPaperPositions = () =>
  apiClient.get('/paper-trading/positions').then((res) => res.data);
export const getPaperTrades = (params) =>
  apiClient.get('/paper-trading/trades', { params }).then((res) => res.data);

// Journal
export const getJournalOpen = () =>
  apiClient.get('/journal/open').then((res) => res.data);
export const getJournalClosed = () =>
  apiClient.get('/journal/closed').then((res) => res.data);
export const getJournalStats = () =>
  apiClient.get('/journal/stats').then((res) => res.data);
export const createJournalEntry = (data) =>
  apiClient.post('/journal/', data).then((res) => res.data);
export const closeJournalEntry = (id, data) =>
  apiClient.patch(`/journal/${id}/close`, data).then((res) => res.data);
