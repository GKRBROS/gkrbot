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
        const res = await api.post('/auth/callback', { code });
        localStorage.setItem('bot_dashboard_token', res.data.token);
        setUser(res.data.user);
        navigate('/dashboard');
      } catch (err) {
        console.error(err);
        setError('Authentication failed. Please try again.');
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
