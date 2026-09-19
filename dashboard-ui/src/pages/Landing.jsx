import { useState } from 'react';
import api from '../api';
import { useBotName } from '../BotContext';
import { Button } from '../components/Button';
import {
  Tv,
  Ticket,
  UserPlus,
  ShieldCheck,
  Music,
  Pin,
  Zap,
  SlidersHorizontal,
  Bot,
  ArrowRight,
  Sparkles
} from 'lucide-react';

const FEATURES = [
  { icon: UserPlus, label: 'Welcome Cards' },
  { icon: Ticket, label: 'Ticket Hubs' },
  { icon: Tv, label: 'Stream Alerts' },
  { icon: ShieldCheck, label: 'Security' },
  { icon: Music, label: 'Music Player' },
  { icon: Pin, label: 'Sticky Messages' },
  { icon: Zap, label: 'Auto Reactions' },
  { icon: SlidersHorizontal, label: 'Server Sync' },
];

export function Landing() {
  const botName = useBotName();
  const [loading, setLoading] = useState(false);

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
    <div className="min-h-screen flex items-center justify-center p-6 bg-canvas relative overflow-hidden">
      {/* Editorial Card */}
      <div className="card p-8 md:p-12 max-w-xl w-full text-center border-border shadow-elevated relative z-10 animate-fade-in">
        {/* Brand Icon */}
        <div className="w-16 h-16 rounded-2xl bg-primary text-white flex items-center justify-center mx-auto mb-6 shadow-[0_8px_24px_-4px_rgba(88,101,242,0.5)]">
          <Bot size={34} />
        </div>

        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-medium text-primary mb-4">
          <Sparkles size={13} />
          <span>Management Dashboard</span>
        </div>

        <h1 className="text-3xl md:text-4xl font-bold text-main mb-3 tracking-tight">
          {botName || 'GKR'} Bot
        </h1>

        <p className="text-sm text-muted max-w-md mx-auto mb-8 leading-relaxed">
          Configure server automations, tickets, stream alerts, moderation, and community features seamlessly from one unified control center.
        </p>

        {/* Feature Pills */}
        <div className="flex flex-wrap items-center justify-center gap-2 mb-10">
          {FEATURES.map((f, i) => {
            const Icon = f.icon;
            return (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface border border-border text-xs text-sub font-medium"
              >
                <Icon size={13} className="text-primary" />
                <span>{f.label}</span>
              </span>
            );
          })}
        </div>

        {/* Discord Login Button */}
        <button
          onClick={handleLogin}
          disabled={loading}
          className="w-full py-3 px-6 rounded-lg bg-[#5865F2] hover:bg-[#4752c4] text-white font-medium text-sm flex items-center justify-center gap-2.5 shadow-lg shadow-[#5865F2]/25 transition-all disabled:opacity-50"
          id="login-btn"
        >
          {loading ? (
            <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
            </svg>
          )}
          <span>{loading ? 'Connecting...' : 'Sign in with Discord'}</span>
        </button>
      </div>
    </div>
  );
}

export default Landing;
