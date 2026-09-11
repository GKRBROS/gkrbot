import { useState } from 'react';
import api from '../api';
import { useBotName } from '../BotContext';

const FEATURES = [
  { icon: '📺', label: 'Stream Alerts' },
  { icon: '🎫', label: 'Tickets' },
  { icon: '👋', label: 'Welcome' },
  { icon: '🛡️', label: 'Security' },
  { icon: '🎵', label: 'Music' },
  { icon: '📌', label: 'Stickies' },
  { icon: '⚡', label: 'Auto Reactions' },
  { icon: '🔄', label: 'Multi-Server Sync' },
];

function Landing() {
  const botName = useBotName();
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    try {
      const redirectUri = window.location.origin + '/auth/callback';
      const clientId = import.meta.env.VITE_DISCORD_CLIENT_ID;

      // 1. If client ID is defined directly in environment, navigate immediately
      if (clientId) {
        const oauthUrl = `https://discord.com/api/oauth2/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=identify%20guilds&prompt=consent`;
        window.location.href = oauthUrl;
        return;
      }

      // 2. Otherwise fetch authorization URL from bot API
      const res = await api.get(`/auth/discord?redirect_uri=${encodeURIComponent(redirectUri)}`);

      // Verify response is valid JSON with a url property (not an HTML fallback)
      if (!res.data || typeof res.data !== 'object' || !res.data.url) {
        throw new Error(
          'Bot API did not return a valid login URL. Please make sure your bot is running and that your Vercel rewrites or VITE_API_URL are set to your bot server IP/port.'
        );
      }

      window.location.href = res.data.url;
    } catch (err) {
      console.error('Login error:', err);
      const msg = err.response?.data?.error || err.message || 'Failed to initialize login. Is the bot server online?';
      alert(msg);
      setLoading(false);
    }
  };

  return (
    <div className="landing-bg animate-fade-in">
      {/* Ambient orbs */}
      <div className="landing-orb o1" />
      <div className="landing-orb o2" />
      <div className="landing-orb o3" />

      <div className="landing-card">
        {/* Logo */}
        <div style={{
          width: '80px', height: '80px', borderRadius: '22px',
          background: 'linear-gradient(135deg, #818cf8, #6366f1 45%, #22d3ee)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '38px', margin: '0 auto 20px',
          boxShadow: '0 12px 40px -8px rgba(99,102,241,0.65), inset 0 1px 0 rgba(255,255,255,0.25)'
        }}>
          🤖
        </div>

        <div className="landing-badge">✨ All-in-one control panel</div>

        <h1 className="landing-title">
          {botName} Bot Dashboard
        </h1>

        <p style={{ color: 'var(--text-muted)', fontSize: '15.5px', lineHeight: '1.65', marginBottom: '28px', maxWidth: '440px', margin: '0 auto 28px' }}>
          Manage servers, stream alerts, tickets, music, security and more — across{' '}
          <span style={{ color: '#a5b4fc', fontWeight: 600 }}>all your Discord servers</span> from one beautiful place.
        </p>

        {/* Feature pills */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center', marginBottom: '34px' }}>
          {FEATURES.map(f => (
            <span key={f.label} className="feature-pill">
              <span style={{ fontSize: '14px' }}>{f.icon}</span> {f.label}
            </span>
          ))}
        </div>

        {/* Login button */}
        <button onClick={handleLogin} disabled={loading} className="btn-discord" id="login-btn">
          {loading ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'center' }}>
              <span style={{
                width: '18px', height: '18px', border: '2.5px solid rgba(255,255,255,0.3)',
                borderTopColor: 'white', borderRadius: '50%',
                animation: 'spin 0.7s linear infinite', display: 'inline-block'
              }} />
              Redirecting...
            </span>
          ) : (
            <>
              <svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
                <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
              </svg>
              Login with Discord
            </>
          )}
        </button>

        <p style={{ marginTop: '18px', color: 'var(--text-muted)', fontSize: '12.5px' }}>
          🔒 Only servers where you have Administrator access will be shown.
        </p>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default Landing;
