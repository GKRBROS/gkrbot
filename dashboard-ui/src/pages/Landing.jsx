import { useState } from 'react';
import api from '../api';

function Landing() {
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    try {
      const res = await api.get('/auth/discord');
      window.location.href = res.data.url;
    } catch (err) {
      console.error(err);
      alert('Failed to initialize login. Is the bot running?');
      setLoading(false);
    }
  };

  return (
    <div className="landing-bg animate-fade-in">
      <div className="landing-card">
        {/* Logo/Icon */}
        <div style={{ marginBottom: '28px' }}>
          <div style={{
            width: '72px', height: '72px', borderRadius: '18px',
            background: 'linear-gradient(135deg, #5865F2, #00d4ff)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '36px', margin: '0 auto 16px', boxShadow: '0 8px 32px rgba(88,101,242,0.4)'
          }}>
            🤖
          </div>
          <h1 style={{
            fontSize: '32px', fontWeight: 800, marginBottom: '8px',
            background: 'linear-gradient(135deg, #ffffff, #a5b4fc)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent'
          }}>
            GKR Bot Dashboard
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '15px', lineHeight: '1.5' }}>
            Manage your Discord server settings, stream alerts, tickets, music, and more — all in one place.
          </p>
        </div>

        {/* Feature pills */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center', marginBottom: '32px' }}>
          {['📺 Stream Alerts', '🎫 Tickets', '👋 Welcome', '🎵 Music', '🎂 Birthdays'].map(f => (
            <span key={f} style={{
              padding: '5px 14px', borderRadius: '999px', fontSize: '13px',
              background: 'rgba(255,255,255,0.06)', border: '1px solid var(--border)',
              color: 'var(--text-sub)', fontWeight: 500
            }}>{f}</span>
          ))}
        </div>

        {/* Login button */}
        <button
          onClick={handleLogin}
          disabled={loading}
          className="btn btn-primary"
          id="login-btn"
          style={{ width: '100%', padding: '14px', fontSize: '16px', borderRadius: '10px' }}
        >
          {loading ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
              <span style={{
                width: '16px', height: '16px', border: '2px solid rgba(255,255,255,0.3)',
                borderTopColor: 'white', borderRadius: '50%',
                animation: 'spin 0.7s linear infinite', display: 'inline-block'
              }} />
              Redirecting...
            </span>
          ) : (
            <>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
                <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03z"/>
              </svg>
              Login with Discord
            </>
          )}
        </button>

        <p style={{ marginTop: '16px', color: 'var(--text-muted)', fontSize: '12px' }}>
          Only servers where you have Administrator access will be shown.
        </p>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

export default Landing;
