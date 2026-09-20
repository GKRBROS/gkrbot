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
  (response) => {
    // Vercel rewrites unknown /api paths to index.html (HTTP 200). That means
    // VITE_API_URL is missing or wrong and the bot API was never reached.
    const type = String(response.headers?.['content-type'] || '');
    if (type.includes('text/html') || (typeof response.data === 'string' && response.data.trim().startsWith('<'))) {
      const err = new Error('API returned HTML instead of JSON. Set VITE_API_URL to your bot API URL and redeploy.');
      err.response = { status: 502, data: { error: err.message } };
      return Promise.reject(err);
    }
    return response;
  },
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