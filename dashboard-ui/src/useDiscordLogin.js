import { useCallback, useState } from 'react';
import api from './api';

// Shared "sign in with Discord" trigger, used by both the marketing site's
// nav/CTA buttons and the (now-unused-by-default) Landing page. Mirrors the
// OAuth logic that used to live only in Landing.jsx.
export function useDiscordLogin() {
  const [loading, setLoading] = useState(false);

  const login = useCallback(async () => {
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
        throw new Error('Bot API did not return a valid login URL. Please make sure your bot is online.');
      }
      window.location.href = res.data.url;
    } catch (err) {
      console.error('Login error:', err);
      const msg = err.response?.data?.error || err.message || 'Failed to initialize login. Is the bot server online?';
      alert(msg);
      setLoading(false);
    }
  }, []);

  return { login, loading };
}
