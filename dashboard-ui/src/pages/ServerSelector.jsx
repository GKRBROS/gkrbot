import { useEffect, useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../api';
import { Button } from '../components/Button';
import { Badge } from '../components/Badge';
import { EmptyState } from '../components/EmptyState';
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
  ChevronLeft,
  ChevronRight,
  Sparkles,
  X
} from 'lucide-react';

const PAGE_SIZE = 18;

export function ServerSelector() {
  const [guilds, setGuilds] = useState([]);
  const [botClientId, setBotClientId] = useState('');
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState('all'); // 'all' | 'active' | 'uninvited'
  const [page, setPage] = useState(1);
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
    let list = guilds;
    if (activeTab === 'active') {
      list = list.filter(g => g.bot_present !== false);
    } else if (activeTab === 'uninvited') {
      list = list.filter(g => g.bot_present === false);
    }

    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter(g => g.name.toLowerCase().includes(q));
  }, [guilds, search, activeTab]);

  // Reset pagination when search or tab changes
  useEffect(() => {
    setPage(1);
  }, [search, activeTab]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginatedGuilds = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, page]);

  const activeCount = useMemo(() => guilds.filter(g => g.bot_present !== false).length, [guilds]);
  const uninvitedCount = useMemo(() => guilds.filter(g => g.bot_present === false).length, [guilds]);

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
            Choose a Discord server below to configure moderation, automated greetings, embeds, tickets, and community features.
          </p>

          {/* Filter Tabs */}
          {!loading && guilds.length > 0 && (
            <div className="flex items-center justify-center gap-2 mt-4 flex-wrap">
              <button
                type="button"
                onClick={() => setActiveTab('all')}
                className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                  activeTab === 'all'
                    ? 'bg-primary text-white shadow-sm'
                    : 'bg-surface-card text-muted hover:text-main'
                }`}
              >
                All Servers ({guilds.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('active')}
                className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                  activeTab === 'active'
                    ? 'bg-primary text-white shadow-sm'
                    : 'bg-surface-card text-muted hover:text-main'
                }`}
              >
                Ready to Manage ({activeCount})
              </button>
              {uninvitedCount > 0 && (
                <button
                  type="button"
                  onClick={() => setActiveTab('uninvited')}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                    activeTab === 'uninvited'
                      ? 'bg-warning text-black shadow-sm'
                      : 'bg-surface-card text-muted hover:text-main'
                  }`}
                >
                  Invite Required ({uninvitedCount})
                </button>
              )}
            </div>
          )}
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
              <span>Invite to New Server</span>
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
              title="No Manageable Servers Found"
              description="You must have Administrator or Manage Server permissions on Discord to configure a server in this dashboard."
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
          <>
            <div className="server-grid">
              {paginatedGuilds.map(guild => {
                const hasBot = guild.bot_present !== false;
                const inviteUrl = `https://discord.com/api/oauth2/authorize?client_id=${botClientId}&permissions=8&scope=bot%20applications.commands&guild_id=${guild.id}`;

                if (!hasBot) {
                  return (
                    <a
                      key={guild.id}
                      href={inviteUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="server-card server-card--uninvited group"
                      title={`Invite ${displayBrandName} to ${guild.name}`}
                    >
                      <div className="server-card-avatar-wrap">
                        {guild.icon ? (
                          <img
                            src={guild.icon}
                            alt={guild.name}
                            className="server-card-avatar grayscale group-hover:grayscale-0 transition"
                            loading="lazy"
                          />
                        ) : (
                          <div className="server-card-avatar-fallback">
                            {guild.name.charAt(0).toUpperCase()}
                          </div>
                        )}
                      </div>

                      <div className="server-card-info">
                        <h3 className="server-card-name" title={guild.name}>
                          {guild.name}
                        </h3>
                        <div className="server-card-status text-warning">
                          <span className="w-2 h-2 rounded-full bg-warning inline-block mr-1" />
                          <span>Bot not invited</span>
                        </div>
                      </div>

                      <div className="server-card-arrow text-warning">
                        <ExternalLink size={15} />
                      </div>
                    </a>
                  );
                }

                return (
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
                );
              })}
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-3 mt-8">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  <ChevronLeft size={16} />
                  <span>Previous</span>
                </Button>
                <span className="text-xs font-semibold text-muted">
                  Page {page} of {totalPages}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                >
                  <span>Next</span>
                  <ChevronRight size={16} />
                </Button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default ServerSelector;