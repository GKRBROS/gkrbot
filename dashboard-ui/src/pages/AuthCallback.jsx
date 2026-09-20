import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';

function AuthCallback({ setUser }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  // Guards against React StrictMode running the effect twice.
  // A Discord code is single-use, so a second exchange would always fail.
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const code = searchParams.get('code');
    const discordError = searchParams.get('error');

    if (discordError) {
      setError(searchParams.get('error_description') || 'Discord authorization was cancelled or denied.');
      return;
    }

    if (!code) {
      // Opened /auth/callback directly (refresh, bookmark, back button).
      // Already logged in: go to dashboard. Otherwise go back to login.
      if (localStorage.getItem('bot_dashboard_token')) {
        navigate('/dashboard', { replace: true });
      } else {
        navigate('/', { replace: true });
      }
      return;
    }

    const exchangeCode = async () => {
      try {
        const res = await api.post('/auth/callback', {
          code,
          redirect_uri: window.location.origin + '/auth/callback'
        });

        if (!res.data || typeof res.data !== 'object' || !res.data.token) {
          throw new Error('Bot server returned an invalid response. Is your bot API online and reachable from Vercel?');
        }

        localStorage.setItem('bot_dashboard_token', res.data.token);
        setUser(res.data.user);
        navigate('/dashboard', { replace: true });
      } catch (err) {
        console.error(err);
        const msg = err.response?.data?.error || err.message || 'Authentication failed. Please verify your Discord Developer Portal settings.';
        setError(msg);
      }
    };
    exchangeCode();
  }, [searchParams, navigate, setUser]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 text-center px-6" style={{ height: '100vh' }}>
        <h2 style={{ color: 'var(--danger)' }}>{error}</h2>
        <button onClick={() => navigate('/', { replace: true })} className="btn btn-primary">Back to Home</button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center animate-fade-in" style={{ height: '100vh' }}>
      <h2>Authenticating...</h2>
    </div>
  );
}

export default AuthCallback;