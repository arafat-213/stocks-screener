import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
});

export const getTopStocks = () => api.get('/stocks/top');
export const getStatus = () => api.get('/pipeline/status');
export const runScreener = () => api.post('/screener/run');
