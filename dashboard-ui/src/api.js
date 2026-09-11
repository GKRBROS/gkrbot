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

// If the server returns 401, the session token is invalid or expired.
// Clear it from storage and redirect to the login page so the user
// re-authenticates cleanly instead of getting stuck in a broken state.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const currentToken = localStorage.getItem('bot_dashboard_token');
      if (currentToken) {
        localStorage.removeItem('bot_dashboard_token');
        // Only redirect if not already on the landing/auth pages
        if (!window.location.pathname.startsWith('/auth')) {
          window.location.href = '/';
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
