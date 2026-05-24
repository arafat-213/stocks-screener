import axios from 'axios';
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const journalApi = {
  getOpen: () => axios.get(`${API_BASE}/journal/open`),
  getClosed: () => axios.get(`${API_BASE}/journal/closed`),
  getStats: () => axios.get(`${API_BASE}/journal/stats`),
  create: (data) => axios.post(`${API_BASE}/journal/`, data),
  close: (id, data) => axios.patch(`${API_BASE}/journal/${id}/close`, data),
};
