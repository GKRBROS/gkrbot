import axios from 'axios';

const rawBase = import.meta.env.VITE_API_URL;
const baseURL = rawBase ? `${rawBase.replace(/\/+$/, '')}/api` : '/api';

const api = axios.create({
  baseURL,
});

// Automatically attach the auth token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('bot_dashboard_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
