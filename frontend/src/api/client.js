import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export const fetchResults = () => apiClient.get('/screener/results');
export const fetchPipelineStatus = () => apiClient.get('/pipeline/latest');
export const runScreener = (limit = null) => apiClient.post('/screener/run', { limit });
export const stopPipeline = () => apiClient.post('/pipeline/stop');
export const getLatestReport = () => apiClient.get('/reports/latest');
export const getReportList = () => apiClient.get('/reports');
export const getReportByDate = (date) => apiClient.get(`/reports/${date}`);
export const getStockDetail = (symbol) => apiClient.get(`/stocks/${symbol}`);
export const getScreensList = () => apiClient.get('/screens');
export const getScreenBySlug = (slug, live = false) =>
  apiClient.get(`/screens/${slug}${live ? '?live=true' : ''}`);
export const getTopStocks = () => apiClient.get('/stocks/top');
export const getStatus = () => apiClient.get('/pipeline/status');
