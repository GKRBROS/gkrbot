import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';

function AuthCallback({ setUser }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState('');

  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      setError('No authorization code found.');
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
        navigate('/dashboard');
      } catch (err) {
        console.error(err);
        const msg = err.response?.data?.error || 'Authentication failed. Please verify your Discord Developer Portal settings.';
        setError(msg);
      }
    };
    exchangeCode();
  }, [searchParams, navigate, setUser]);

  if (error) {
    return (
      <div className="flex-col items-center justify-center" style={{ height: '100vh', textAlign: 'center' }}>
        <h2 style={{ color: 'var(--danger)' }}>{error}</h2>
        <button onClick={() => navigate('/')} className="btn btn-primary" style={{ marginTop: '16px' }}>Back to Home</button>
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
