import { Outlet, Link, useParams, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState, useMemo } from 'react';
import api from '../api';
import { autoSyncEnabled, setAutoSyncEnabled } from '../sync';
import { useBotName } from '../BotContext';
import {
  LayoutDashboard,
  UserPlus,
  Ticket,
  Tv,
  FileText,
  ShieldAlert,
  Scale,
  ScrollText,
  Gift,
  BarChart3,
  Users,
  Cake,
  Sparkles,
  Trophy,
  Pin,
  Zap,
  Terminal,
  Mic,
  Music,
  Radio,
  Coins,
  Bot,
  Volume2,
  RefreshCw,
  SlidersHorizontal,
  ChevronLeft,
  ChevronRight,
  Menu,
  X,
  Search,
  LogOut,
  Server,
  ChevronDown
} from 'lucide-react';

const PAGE_DEFINITIONS = [
  {
    label: 'Overview',
    items: [
      { id: 'overview', name: 'Overview', path: 'overview', icon: LayoutDashboard },
    ]
  },
  {
    label: 'Core Features',
    items: [
      { id: 'welcome', name: 'Welcome & Leave', path: 'welcome', icon: UserPlus },
      { id: 'tickets', name: 'Tickets System', path: 'tickets', icon: Ticket },
      { id: 'stream-alerts', name: 'Stream Alerts', path: 'stream-alerts', icon: Tv },
      { id: 'registration', name: 'Registration & Forms', path: 'registration', icon: FileText },
    ]
  },
  {
    label: 'Security & Moderation',
    items: [
      { id: 'security', name: 'Security & Anti-Spam', path: 'security', icon: ShieldAlert },
      { id: 'moderation', name: 'Staff Roles & Mod', path: 'moderation', icon: Scale },
      { id: 'server-logs', name: 'Server Logs', path: 'server-logs', icon: ScrollText },
    ]
  },
  {
    label: 'Community',
    items: [
      { id: 'giveaways', name: 'Giveaways', path: 'giveaways', icon: Gift },
      { id: 'polls', name: 'Polls', path: 'polls', icon: BarChart3 },
      { id: 'community', name: 'Community & Suggestions', path: 'community', icon: Users },
      { id: 'birthdays', name: 'Birthdays', path: 'birthdays', icon: Cake },
      { id: 'self-roles', name: 'Self Roles', path: 'self-roles', icon: Sparkles },
      { id: 'leaderboard', name: 'Leaderboard & XP', path: 'leaderboard', icon: Trophy },
    ]
  },
  {
    label: 'Server Automation',
    items: [
      { id: 'sticky', name: 'Sticky Messages', path: 'sticky', icon: Pin },
      { id: 'auto-reactions', name: 'Auto Reactions', path: 'auto-reactions', icon: Zap },
      { id: 'custom-commands', name: 'Custom Commands', path: 'custom-commands', icon: Terminal },
      { id: 'temp-vc', name: 'Temp Voice Channels', path: 'temp-vc', icon: Mic },
    ]
  },
  {
    label: 'Entertainment',
    items: [
      { id: 'music', name: 'Music Player', path: 'music', icon: Music },
      { id: 'radio', name: 'Radio Station', path: 'radio', icon: Radio },
      { id: 'economy', name: 'Economy & Shop', path: 'economy', icon: Coins },
    ]
  },
  {
    label: 'Advanced',
    items: [
      { id: 'ai', name: 'AI System Studio', path: 'ai', icon: Bot },
      { id: 'voice-announce', name: 'Voice Announcer', path: 'voice-announce', icon: Volume2 },
      { id: 'role-sync', name: 'Role Sync', path: 'role-sync', icon: RefreshCw },
      { id: 'sync', name: 'Sync Servers', path: 'sync', icon: SlidersHorizontal },
    ]
  },
];

export function DashboardLayout({ user }) {
  const { guildId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const botName = useBotName();

  const [guild, setGuild] = useState(null);
  const [allGuilds, setAllGuilds] = useState([]);
  const [autoSync, setAutoSync] = useState(autoSyncEnabled());
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('sidebar_collapsed') === 'true');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [serverPickerOpen, setServerPickerOpen] = useState(false);

  const toggleAutoSync = () => {
    const next = !autoSync;
    setAutoSync(next);
    setAutoSyncEnabled(next);
  };

  const toggleCollapsed = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem('sidebar_collapsed', String(next));
  };

  // Close mobile nav on route change
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  // Fetch current user and guild info
  useEffect(() => {
    api.get('/users/@me').then(res => {
      const gList = res.data.guilds || [];
      setAllGuilds(gList);
      const found = gList.find(g => String(g.id) === String(guildId));
      if (found) setGuild(found);
    }).catch(console.error);
  }, [guildId]);

  // Derive current page segment and title
  const pathParts = location.pathname.split('/').filter(Boolean);
  const activeSegment = pathParts[pathParts.length - 1] || 'overview';

  const currentPageItem = useMemo(() => {
    for (const group of PAGE_DEFINITIONS) {
      for (const item of group.items) {
        if (item.path === activeSegment) return item;
      }
    }
    return null;
  }, [activeSegment]);

  // Filter navigation items if searching
  const filteredNavGroups = useMemo(() => {
    if (!searchQuery.trim()) return PAGE_DEFINITIONS;
    const q = searchQuery.toLowerCase().trim();
    return PAGE_DEFINITIONS.map(group => ({
      ...group,
      items: group.items.filter(item => item.name.toLowerCase().includes(q))
    })).filter(group => group.items.length > 0);
  }, [searchQuery]);

  const handleLogout = () => {
    localStorage.removeItem('bot_dashboard_token');
    window.location.href = '/';
  };

  return (
    <div className="app-shell">
      {/* Mobile Drawer Backdrop */}
      {mobileNavOpen && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 md:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      {/* Sidebar (Desktop & Mobile Drawer) */}
      <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileNavOpen ? 'mobile-open' : ''}`}>
        {/* Brand Header */}
        <div className="sidebar-header">
          <Link to={`/dashboard/${guildId}/overview`} className="sidebar-brand">
            <div className="sidebar-brand-icon">
              <Bot size={18} />
            </div>
            {!collapsed && (
              <span className="sidebar-brand-name">
                {botName ? (botName.toLowerCase().endsWith('bot') ? botName : `${botName} Bot`) : 'GKR Bot'}
              </span>
            )}
          </Link>

          <button
            type="button"
            className="sidebar-collapse-btn hidden md:flex"
            onClick={toggleCollapsed}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>

          <button
            type="button"
            className="sidebar-collapse-btn md:hidden"
            onClick={() => setMobileNavOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        {/* Selected Server Widget */}
        <div className="sidebar-guild-selector">
          {guild?.icon ? (
            <img src={guild.icon} alt={guild.name} className="sidebar-guild-avatar" />
          ) : (
            <div className="sidebar-guild-avatar-fallback">
              {guild?.name ? guild.name.charAt(0).toUpperCase() : <Server size={14} />}
            </div>
          )}

          {!collapsed && (
            <div className="sidebar-guild-meta">
              <div className="sidebar-guild-title" title={guild?.name || 'Loading server...'}>
                {guild?.name || 'Loading server...'}
              </div>
              <Link to="/dashboard" className="sidebar-guild-action">
                Switch server
              </Link>
            </div>
          )}
        </div>

        {/* Search Navigation Bar */}
        {!collapsed && (
          <div className="sidebar-search-box">
            <Search size={13} className="sidebar-search-icon" />
            <input
              type="text"
              placeholder="Search features..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="sidebar-search-input"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-6 top-1/2 -translate-y-1/2 text-muted hover:text-main"
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
              >
                <X size={12} />
              </button>
            )}
          </div>
        )}

        {/* Navigation Items */}
        <nav className="sidebar-nav" aria-label="Main Navigation">
          {filteredNavGroups.map((group, gIdx) => (
            <div key={gIdx} className="mb-2">
              {!collapsed && (
                <div className="sidebar-group-label">{group.label}</div>
              )}
              {group.items.map(item => {
                const ItemIcon = item.icon;
                const isActive = activeSegment === item.path;

                return (
                  <Link
                    key={item.id}
                    to={`/dashboard/${guildId}/${item.path}`}
                    className={`sidebar-link ${isActive ? 'active' : ''}`}
                    title={collapsed ? item.name : undefined}
                  >
                    <ItemIcon size={17} className="sidebar-link-icon" />
                    {!collapsed && (
                      <span className="sidebar-link-text">{item.name}</span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Footer Profile */}
        <div className="sidebar-footer">
          {user?.avatar ? (
            <img src={user.avatar} alt={user.username} className="sidebar-user-avatar" />
          ) : (
            <div className="sidebar-user-avatar flex items-center justify-center bg-primary/20 text-primary text-xs font-bold">
              {user?.username?.charAt(0) || 'U'}
            </div>
          )}

          {!collapsed && (
            <div className="sidebar-user-name" title={user?.username || 'Admin'}>
              {user?.username || 'Admin'}
            </div>
          )}

          <button
            type="button"
            onClick={handleLogout}
            className="sidebar-collapse-btn"
            title="Log out"
            aria-label="Log out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {/* Main Content Viewport */}
      <div className="main-viewport">
        {/* Top Header */}
        <header className="topbar">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              className="mobile-nav-toggle"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open menu"
            >
              <Menu size={18} />
            </button>

            {/* Breadcrumb Navigation */}
            <div className="topbar-breadcrumbs">
              <Link to="/dashboard" className="breadcrumb-link">
                <Server size={14} className="text-muted" />
                <span>Servers</span>
              </Link>

              <span className="breadcrumb-separator">/</span>

              {guild && (
                <Link to={`/dashboard/${guildId}/overview`} className="breadcrumb-link">
                  <span className="max-w-[140px] truncate">{guild.name}</span>
                </Link>
              )}

              {currentPageItem && (
                <>
                  <span className="breadcrumb-separator">/</span>
                  <span className="breadcrumb-current">
                    {currentPageItem.name}
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Right Header Actions */}
          <div className="topbar-actions">
            {/* Auto-Sync Toggle Pill */}
            <div
              className={`autosync-pill ${autoSync ? 'on' : ''}`}
              onClick={toggleAutoSync}
              role="button"
              tabIndex={0}
              onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && toggleAutoSync()}
              title={autoSync ? 'Auto-sync active: edits mirror to all servers' : 'Auto-sync paused: edits stay in this server'}
            >
              <span className="autosync-dot" />
              <SlidersHorizontal size={13} className={autoSync ? 'text-primary' : 'text-muted'} />
              <div>
                <span className="autosync-text">
                  Auto-Sync: {autoSync ? 'ON' : 'OFF'}
                </span>
                <span className="autosync-sub ml-1">
                  ({autoSync ? 'All servers' : 'Local only'})
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Dynamic Page Container */}
        <main className="content-container">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default DashboardLayout;
