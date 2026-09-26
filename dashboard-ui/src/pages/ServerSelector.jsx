import { useEffect, useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../api';
import { Button } from '../components/Button';
import { Badge } from '../components/Badge';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/Skeleton';
import { Loader } from '../components/Loader';
import { useBotName } from '../BotContext';
import {
  Search,
  Server,
  Plus,
  ArrowRight,
  ShieldCheck,
  LogOut,
  ExternalLink,
  Sparkles,
  X
} from 'lucide-react';

export function ServerSelector() {
  const [guilds, setGuilds] = useState([]);
  const [botClientId, setBotClientId] = useState('');
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const botName = useBotName();
  const navigate = useNavigate();

  useEffect(() => {
    const fetchUserData = async () => {
      try {
        const res = await api.get('/users/@me');
        setUser(res.data.user || null);
        setGuilds(res.data.guilds || []);
        if (res.data.bot_client_id) {
          setBotClientId(res.data.bot_client_id);
        }
      } catch (err) {
        console.error('Failed to fetch guilds or user profile', err);
      } finally {
        setLoading(false);
      }
    };
    fetchUserData();
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('bot_dashboard_token');
    window.location.href = '/';
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return guilds;
    const q = search.trim().toLowerCase();
    return guilds.filter(g => g.name.toLowerCase().includes(q));
  }, [guilds, search]);

  const cleanName = (botName || '').trim();
  const displayBrandName = !cleanName || cleanName.toLowerCase() === 'bot'
    ? 'GKR Bot'
    : cleanName.toLowerCase().endsWith('bot')
      ? cleanName
      : `${cleanName} Bot`;

  return (
    <div className="server-selector-shell">
      {/* Top Application Bar */}
      <header className="server-selector-nav">
        <div className="server-selector-nav-inner">
          <div className="flex items-center gap-3">
            <div className="server-selector-brand-icon server-selector-brand-icon--logo">
              <img src="/logo-mark.png" alt="" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base text-main tracking-tight">{displayBrandName}</span>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-primary/15 text-primary border border-primary/25">
                  Dashboard
                </span>
              </div>
              <span className="text-[11px] text-muted hidden sm:inline-block">Command & Control Center</span>
            </div>
          </div>

          {user && (
            <div className="flex items-center gap-3">
              <div className="server-selector-user-chip">
                {user.avatar ? (
                  <img src={user.avatar} alt={user.username} className="w-7 h-7 rounded-full object-cover" />
                ) : (
                  <div className="w-7 h-7 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-xs">
                    {user.username?.charAt(0) || 'U'}
                  </div>
                )}
                <span className="text-xs font-medium text-main max-w-[120px] truncate">
                  {user.username}
                </span>
              </div>

              <button
                type="button"
                onClick={handleLogout}
                className="btn btn-ghost btn-sm text-muted hover:text-danger"
                title="Log out"
                aria-label="Log out"
              >
                <LogOut size={15} />
                <span className="hidden sm:inline text-xs">Logout</span>
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="server-selector-content">
        {/* Page Hero Header */}
        <div className="server-selector-hero">
          <div className="server-selector-badge">
            <ShieldCheck size={13} />
            <span>
              {loading
                ? 'Verifying Servers...'
                : `${guilds.length} Authorized Server${guilds.length === 1 ? '' : 's'}`}
            </span>
          </div>
          <h1 className="server-selector-title">Select a Server</h1>
          <p className="server-selector-subtitle">
            Choose a Discord server below to configure automated greetings, ticket hubs, stream alerts, moderation, and community features.
          </p>
        </div>

        {/* Responsive Search & Actions Toolbar */}
        <div className="server-selector-toolbar">
          <div className="server-search-wrapper">
            <Search size={16} className="server-search-icon" />
            <input
              type="text"
              className="server-search-input"
              placeholder="Search your servers by name..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              aria-label="Search servers"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="server-search-clear"
                title="Clear search"
                aria-label="Clear search"
              >
                <X size={14} />
              </button>
            )}
          </div>

          {botClientId && (
            <a
              href={`https://discord.com/api/oauth2/authorize?client_id=${botClientId}&permissions=8&scope=bot%20applications.commands`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-primary server-invite-btn"
            >
              <Plus size={16} />
              <span>Invite to Server</span>
            </a>
          )}
        </div>

        {/* Search Results Meta */}
        {!loading && search && (
          <div className="server-results-meta">
            <span>
              Showing {filtered.length} of {guilds.length} servers
            </span>
            <button
              type="button"
              onClick={() => setSearch('')}
              className="text-xs text-primary hover:underline"
            >
              Clear filter
            </button>
          </div>
        )}

        {/* Grid or States */}
        {loading ? (
          <Loader label="Loading your servers…" />
        ) : guilds.length === 0 ? (
          <div className="server-empty-panel">
            <EmptyState
              icon={Server}
              title="No Authorized Servers Found"
              description="You do not appear to have Administrator or Manage Server permissions on any server where this bot is present."
              action={
                botClientId && (
                  <a
                    href={`https://discord.com/api/oauth2/authorize?client_id=${botClientId}&permissions=8&scope=bot%20applications.commands`}
                    target="_blank"
                    rel="noreferrer"
                    className="btn btn-primary"
                  >
                    <Plus size={16} />
                    <span>Invite Bot to a Server</span>
                  </a>
                )
              }
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="server-empty-panel">
            <EmptyState
              icon={Search}
              title="No Matching Servers"
              description={`We couldn't find any server matching "${search}".`}
              action={
                <Button variant="secondary" onClick={() => setSearch('')}>
                  Clear Search
                </Button>
              }
            />
          </div>
        ) : (
          <div className="server-grid">
            {filtered.map(guild => (
              <Link
                key={guild.id}
                to={`/dashboard/${guild.id}`}
                className="server-card group"
                title={`Manage ${guild.name}`}
              >
                {guild.icon && (
                  <span
                    className="server-card-glow"
                    style={{ backgroundImage: `url(${guild.icon})` }}
                    aria-hidden="true"
                  />
                )}
                <div className="server-card-avatar-wrap">
                  {guild.icon ? (
                    <img
                      src={guild.icon}
                      alt={guild.name}
                      className="server-card-avatar"
                      loading="lazy"
                    />
                  ) : (
                    <div className="server-card-avatar-fallback">
                      {guild.name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <span className="server-card-pulse" />
                </div>

                <div className="server-card-info">
                  <h3 className="server-card-name" title={guild.name}>
                    {guild.name}
                  </h3>
                  <div className="server-card-status">
                    <span className="server-card-dot" />
                    <span>Ready to manage</span>
                  </div>
                </div>

                <div className="server-card-arrow">
                  <ArrowRight size={15} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default ServerSelector;