import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export const getStocks = () => apiClient.get('/stocks');
export const getTopStocks = () => apiClient.get('/screener/top');
export const runScreener = () => apiClient.post('/screener/run');
export const getLatestReport = () => apiClient.get('/reports/latest');
