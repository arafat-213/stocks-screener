import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export const fetchResults = () => apiClient.get('/screener/results');
export const fetchPipelineStatus = () => apiClient.get('/pipeline/latest');
export const runScreener = () => apiClient.post('/screener/run');
export const getLatestReport = () => apiClient.get('/reports/latest');
