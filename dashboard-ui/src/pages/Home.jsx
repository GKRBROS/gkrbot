import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import api from '../api';
import { useBotName } from '../BotContext';
import { useDiscordLogin } from '../useDiscordLogin';
import { SitePage, LOGO_URL } from '../components/SiteLayout';
import {
  ArrowRight, Plus, BookOpen, LifeBuoy, ShieldAlert, Ticket, Music, Radio,
  Coins, Gift, Users, Cake, Sparkles, Trophy, Pin, Zap, Terminal, Mic,
  RefreshCw, Bot, Volume2, FileText, ScrollText, BarChart3, UserPlus,
  Tv, SlidersHorizontal, CalendarClock, MessageSquareText, ShieldCheck,
} from 'lucide-react';

// One card per bot cog (see the `extensions` list in main.py). Grouped loosely
// so the grid reads well; add/remove entries here as cogs are added or removed.
const FEATURES = [
  { icon: UserPlus, title: 'Welcome & Leave Cards', desc: 'Animated, fully customizable join/leave cards with avatars, member counts and live previews.' },
  { icon: Ticket, title: 'Ticket Hubs', desc: 'Category-based support tickets with transcripts, claiming, and staff-only controls.' },
  { icon: ShieldAlert, title: 'Advanced Security', desc: 'Anti-nuke, anti-raid, anti-hacked account detection, and honeypot traps for scammers.' },
  { icon: ShieldCheck, title: 'Moderation Suite', desc: 'Mute, warn, staff roles, mod-logs and configurable moderation permissions.' },
  { icon: Music, title: 'Music Player', desc: 'High-quality music playback with queues, filters, and full voice-channel control.' },
  { icon: Radio, title: '24/7 Radio', desc: 'Always-on, low-CPU radio streaming for your voice channels.' },
  { icon: Coins, title: 'Economy & Levels', desc: 'A full currency system with shops, gambling games, and voice/text XP leveling.' },
  { icon: Gift, title: 'Giveaways', desc: 'Multi-winner giveaways with requirements, rerolls, and scheduled endings.' },
  { icon: Trophy, title: 'Leaderboards', desc: 'Server-wide XP and coin leaderboards that update in real time.' },
  { icon: BarChart3, title: 'Polls & Voting', desc: 'Interactive polls with live result bars and multiple-choice support.' },
  { icon: Users, title: 'Community & Suggestions', desc: 'Verification flows, suggestion boxes with voting, and member profiles.' },
  { icon: Cake, title: 'Birthdays', desc: 'Automatic birthday announcements and role assignment on the big day.' },
  { icon: Sparkles, title: 'Self Roles', desc: 'Button and dropdown self-role menus your members can use anytime.' },
  { icon: Pin, title: 'Sticky Messages', desc: 'Keep important messages pinned to the bottom of any channel automatically.' },
  { icon: Zap, title: 'Auto Reactions', desc: 'Automatically react to messages matching your own custom triggers.' },
  { icon: Terminal, title: 'Custom Commands', desc: 'Build your own `!commands` with dynamic replies — no coding required.' },
  { icon: Mic, title: 'Temp Voice Channels', desc: 'On-demand private voice channels that clean themselves up when empty.' },
  { icon: Bot, title: 'AI System Studio', desc: 'A self-hosted, zero-API-cost AI assistant you can fully customize per server.' },
  { icon: Volume2, title: 'Voice Announcer', desc: 'Natural neural text-to-speech announcements when members join voice.' },
  { icon: RefreshCw, title: 'Role Sync & Server Sync', desc: 'Mirror roles and settings automatically across all of your servers.' },
  { icon: Tv, title: 'Stream Alerts', desc: 'Live Twitch/YouTube alerts posted straight to your announcement channel.' },
  { icon: FileText, title: 'Registration & Forms', desc: 'Dynamic application forms with staff review and approval workflows.' },
  { icon: ScrollText, title: 'Server Logs', desc: 'Detailed audit logs for messages, roles, joins, bans and more.' },
  { icon: CalendarClock, title: 'Server Events & RSVP', desc: 'Schedule events with automatic reminders and one-click RSVPs.' },
  { icon: MessageSquareText, title: 'Festival Announcements', desc: 'Automatic seasonal and festival greetings for your community.' },
  { icon: SlidersHorizontal, title: 'Server Backups', desc: 'Automated backups and templates so you can restore your server in one click.' },
];

const NUMBER_FMT = new Intl.NumberFormat();

function useCountUp(target, active) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!active || typeof target !== 'number') return undefined;
    let raf; const start = performance.now(); const from = 0; const dur = 1100;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / dur);
      setVal(Math.round(from + (target - from) * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, active]);
  return val;
}

function StatCell({ label, value, suffix = '' }) {
  const n = useCountUp(typeof value === 'number' ? value : null, value != null);
  return (
    <div className="site-stat">
      <div className="site-stat-num">{value == null ? '—' : `${NUMBER_FMT.format(n)}${suffix}`}</div>
      <div className="site-stat-label">{label}</div>
    </div>
  );
}

export function Home({ user }) {
  const botName = useBotName();
  const brand = (botName || 'Bot').trim();
  const [stats, setStats] = useState(null);
  const [botClientId, setBotClientId] = useState('');
  const { login, loading: loggingIn } = useDiscordLogin();
  const location = useLocation();

  // Nav links to "/#features" land here via client-side routing now (no page
  // reload), so the browser never auto-scrolls to the anchor on its own --
  // do it manually whenever the hash is (or becomes) #features.
  useEffect(() => {
    if (location.hash === '#features') {
      document.getElementById('features')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [location.hash]);

  useEffect(() => {
    api.get('/public/stats').then(res => setStats(res.data)).catch(() => setStats(false));
    api.get('/public/config').then(() => {}).catch(() => {});
    api.get('/users/@me').then(res => { if (res.data.bot_client_id) setBotClientId(res.data.bot_client_id); }).catch(() => {});
  }, []);

  const inviteUrl = botClientId
    ? `https://discord.com/api/oauth2/authorize?client_id=${botClientId}&permissions=8&scope=bot%20applications.commands`
    : '#';

  return (
    <SitePage user={user}>
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="site-hero">
        <div className="container">
          <span className="site-hero-badge"><span className="dot" /> Your server. Your rules. Your bot.</span>
          <img src={LOGO_URL} alt={brand} className="site-hero-logo" />
          <h1>The Ultimate <span className="grad">All-in-One</span><br />Discord Bot</h1>
          <p className="lead">
            Moderation, security, music, AI, tickets, automation and everything your Discord
            server needs — in one powerful, unified platform.
          </p>
          <div className="site-hero-ctas">
            <a href={inviteUrl} className="site-btn site-btn-primary" target="_blank" rel="noreferrer">
              <Plus size={16} /> <span>Add to Discord</span>
            </a>
            {user ? (
              <Link to="/dashboard" className="site-btn site-btn-ghost">
                <SlidersHorizontal size={15} /> <span>Open Dashboard</span>
              </Link>
            ) : (
              <button type="button" onClick={login} disabled={loggingIn} className="site-btn site-btn-ghost">
                <SlidersHorizontal size={15} /> <span>{loggingIn ? 'Connecting…' : 'Open Dashboard'}</span>
              </button>
            )}
            <Link to="/docs" className="site-btn site-btn-ghost">
              <BookOpen size={15} /> <span>Documentation</span>
            </Link>
            <Link to="/support" className="site-btn site-btn-ghost">
              <LifeBuoy size={15} /> <span>Support</span>
            </Link>
          </div>

          {/* Live terminal mock */}
          <div className="site-terminal">
            <div className="site-terminal-bar">
              <div className="site-terminal-dots"><span /><span /><span /></div>
              <span className="site-terminal-title">{brand.toUpperCase()} COMMAND TERMINAL</span>
              <span className="site-terminal-status"><span className="d" /> SHARD #0 CONNECTED</span>
            </div>
            <div className="site-terminal-body">
              <div className="site-terminal-msg">
                <div className="site-terminal-avatar">🛡️</div>
                <div>
                  <div className="site-terminal-name">{brand} <span className="site-terminal-tag">BOT</span> <span className="site-terminal-time">Today at 12:00</span></div>
                  <div className="site-terminal-line">
                    🛡️ <strong>Anti-Raid Auto-Defense Triggered:</strong> Blocked 14 malicious accounts
                    attempting a mass-join wave. Channels protected.<span className="site-terminal-cursor" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Live stats */}
          <div className="site-stats">
            <StatCell label="Servers" value={stats ? stats.servers : null} suffix="+" />
            <StatCell label="Members Protected" value={stats ? stats.members : null} suffix="+" />
            <StatCell label="Slash Commands" value={stats ? stats.commands : null} />
            <StatCell label="Latency" value={stats && stats.latency_ms != null ? stats.latency_ms : null} suffix="ms" />
          </div>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────── */}
      <section className="site-section" id="features">
        <div className="container">
          <div className="site-section-head">
            <div className="site-eyebrow">Everything included</div>
            <h2>One bot. Every feature.</h2>
            <p>No paywalls, no separate bots to juggle — every module below ships in {brand}, free.</p>
          </div>
          <div className="site-grid">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="site-card">
                  <div className="site-card-icon"><Icon size={20} /></div>
                  <h3>{f.title}</h3>
                  <p>{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────── */}
      <section className="site-section">
        <div className="container">
          <div className="site-card" style={{ textAlign: 'center', padding: '48px 32px' }}>
            <h2 style={{ fontSize: 28, fontWeight: 800, marginBottom: 10 }}>Ready to upgrade your server?</h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 24 }}>It takes less than a minute to add {brand} and start configuring it from the dashboard.</p>
            <div className="site-hero-ctas">
              <a href={inviteUrl} className="site-btn site-btn-primary" target="_blank" rel="noreferrer">
                <Plus size={16} /> <span>Add to Discord</span> <ArrowRight size={15} />
              </a>
            </div>
          </div>
        </div>
      </section>
    </SitePage>
  );
}

export default Home;
