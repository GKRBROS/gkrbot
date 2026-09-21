import { useRef, useState } from 'react';
import api from '../api';
import { useBotName } from '../BotContext';
import {
  Tv,
  Ticket,
  UserPlus,
  ShieldCheck,
  Music,
  Pin,
  Zap,
  SlidersHorizontal,
  Sparkles,
  Lock,
  Radio,
  Coins
} from 'lucide-react';

const FEATURES = [
  { icon: UserPlus, label: 'Welcome Cards' },
  { icon: Ticket, label: 'Ticket Hubs' },
  { icon: Tv, label: 'Stream Alerts' },
  { icon: ShieldCheck, label: 'Security & AutoMod' },
  { icon: Music, label: 'Music Player' },
  { icon: Radio, label: 'Radio 24/7' },
  { icon: Coins, label: 'Economy & Levels' },
  { icon: Pin, label: 'Sticky Messages' },
  { icon: Zap, label: 'Auto Reactions' },
  { icon: SlidersHorizontal, label: 'Server Sync' },
];

export function Landing() {
  const botName = useBotName();
  const [loading, setLoading] = useState(false);
  const cardRef = useRef(null);

  // Card tilts toward the cursor and a soft light follows it
  const handlePointerMove = (e) => {
    const el = cardRef.current;
    if (!el || e.pointerType === 'touch') return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    el.style.setProperty('--rx', `${((0.5 - py) * 5).toFixed(2)}deg`);
    el.style.setProperty('--ry', `${((px - 0.5) * 7).toFixed(2)}deg`);
    el.style.setProperty('--gx', `${(px * 100).toFixed(1)}%`);
    el.style.setProperty('--gy', `${(py * 100).toFixed(1)}%`);
  };
  const handlePointerLeave = () => {
    const el = cardRef.current;
    if (!el) return;
    el.style.setProperty('--rx', '0deg');
    el.style.setProperty('--ry', '0deg');
  };

  // Normalize bot title so it never becomes "Bot Bot" or empty
  const cleanName = (botName || '').trim();
  const titleName = !cleanName || cleanName.toLowerCase() === 'bot'
    ? 'GKR'
    : cleanName.toLowerCase().endsWith('bot')
      ? cleanName.slice(0, -3).trim()
      : cleanName;

  const handleLogin = async () => {
    setLoading(true);
    try {
      const redirectUri = window.location.origin + '/auth/callback';
      const clientId = import.meta.env.VITE_DISCORD_CLIENT_ID;

      if (clientId) {
        const oauthUrl = `https://discord.com/api/oauth2/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=identify%20guilds&prompt=consent`;
        window.location.href = oauthUrl;
        return;
      }

      const res = await api.get(`/auth/discord?redirect_uri=${encodeURIComponent(redirectUri)}`);
      if (!res.data || typeof res.data !== 'object' || !res.data.url) {
        throw new Error(
          'Bot API did not return a valid login URL. Please make sure your bot is online.'
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
    <div className="landing-viewport">
      {/* Background ambient lighting */}
      {/* Decor lives in its own fixed, clipped layer so it can never make the page scroll */}
      <div className="landing-decor" aria-hidden="true">
        <div className="landing-grid" />
        <div className="landing-beam landing-beam--a" />
        <div className="landing-beam landing-beam--b" />
        <div className="landing-glow-top" />
        <div className="landing-glow-bottom" />
      </div>

      {/* Main Container */}
      <div className="landing-container">
        <main
          ref={cardRef}
          className="landing-card-elevated"
          onPointerMove={handlePointerMove}
          onPointerLeave={handlePointerLeave}
        >
          {/* Brand Logo */}
          <div className="landing-brand-icon landing-brand-icon--logo" style={{ '--n': 0 }}>
            <img src="/logo-wordmark.png" alt="GKR" />
          </div>

          {/* Eyebrow Label */}
          <div className="landing-eyebrow" style={{ '--n': 1 }}>
            <Sparkles size={13} />
            <span>Management Dashboard</span>
          </div>

          {/* Bot Title */}
          <h1 className="landing-heading" style={{ '--n': 2 }}>
            {titleName} Bot Dashboard
          </h1>

          {/* Description */}
          <p className="landing-description" style={{ '--n': 3 }}>
            Configure server automations, tickets, stream alerts, moderation, and community features seamlessly from one unified control center.
          </p>

          {/* Feature Badges */}
          <div className="landing-features-grid" role="list" aria-label="Feature list" style={{ '--n': 4 }}>
            {FEATURES.map((f, i) => {
              const Icon = f.icon;
              return (
                <span key={i} className="landing-feature-chip" role="listitem" style={{ '--i': i }}>
                  <Icon size={13} />
                  <span>{f.label}</span>
                </span>
              );
            })}
          </div>

          {/* Discord Login Button */}
          <div className="landing-btn-wrapper" style={{ '--n': 5 }}>
            <button
              onClick={handleLogin}
              disabled={loading}
              className="landing-discord-btn"
              id="login-btn"
              type="button"
              aria-label="Sign in with Discord"
            >
              {loading ? (
                <>
                  <span
                    style={{
                      width: '18px',
                      height: '18px',
                      border: '2.5px solid rgba(255,255,255,0.3)',
                      borderTopColor: '#ffffff',
                      borderRadius: '50%',
                      animation: 'spin 0.7s linear infinite',
                      display: 'inline-block'
                    }}
                  />
                  <span>Connecting to Discord...</span>
                </>
              ) : (
                <>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
                  </svg>
                  <span>Sign in with Discord</span>
                </>
              )}
            </button>
          </div>

          {/* Permissions note */}
          <p className="landing-permission-note" style={{ '--n': 6 }}>
            <Lock size={12} />
            <span>Requires Administrator or Manage Server permissions.</span>
          </p>

          {/* Decorative layers (absolute, never take part in layout) */}
          <span className="landing-deco landing-card-border" aria-hidden="true" />
          <span className="landing-deco landing-card-sheen" aria-hidden="true" />
        </main>

        {/* Subtle Footer */}
        <footer className="landing-footer">
          <span className="landing-status-dot" aria-hidden="true" />
          <span>Unified Bot Control Panel</span>
        </footer>
      </div>
    </div>
  );
}

export default Landing;