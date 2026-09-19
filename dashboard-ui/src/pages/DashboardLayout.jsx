import { Outlet, Link, useParams, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import api from '../api';
import { autoSyncEnabled, setAutoSyncEnabled } from '../sync';
import { useBotName } from '../BotContext';
import { useTheme } from '../hooks/useTheme';

// Page name map for breadcrumbs
const PAGE_NAMES = {
  overview: '📊 Overview',
  welcome: '👋 Welcome & Leave',
  registration: '📝 Registration & Forms',
  'stream-alerts': '📺 Stream Alerts',
  tickets: '🎫 Tickets',
  security: '🛡️ Security',
  moderation: '⚖️ Moderation',
  sticky: '📌 Sticky Messages',
  'auto-reactions': '⚡ Auto Reactions',
  'custom-commands': '💬 Custom Commands',
  'temp-vc': '🎙️ Temp Voice',
  music: '🎵 Music',
  radio: '📻 Radio',
  economy: '🪙 Economy',
  giveaways: '🎉 Giveaways',
  polls: '📊 Polls',
  'self-roles': '🎭 Self Roles',
  'server-logs': '📋 Server Logs',
  birthdays: '🎂 Birthdays',
  leaderboard: '🏆 Leaderboard',
  community: '🤝 Community',
  ai: '🤖 AI System',
  'voice-announce': '🔊 Voice Announce',
  'role-sync': '🔗 Role Sync',
  sync: '🔄 Multi-Server Sync',
};

function DashboardLayout({ user }) {
  const { guildId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const botName = useBotName();
  const { theme, toggle: toggleTheme, isDark } = useTheme();
  const [guild, setGuild] = useState(null);
  const [autoSync, setAutoSync] = useState(autoSyncEnabled());
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const toggleAutoSync = () => {
    const next = !autoSync;
    setAutoSync(next);
    setAutoSyncEnabled(next);
  };

  // Close mobile nav whenever the route changes
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    api.get('/users/@me').then(res => {
      const found = res.data.guilds.find(g => g.id === guildId);
      if (found) setGuild(found);
    }).catch(console.error);
  }, [guildId]);

  // Derive current page name for breadcrumb
  const pathSegments = location.pathname.split('/').filter(Boolean);
  const currentPage = pathSegments[pathSegments.length - 1];
  const currentPageName = PAGE_NAMES[currentPage] || '';

  const navGroups = [
    {
      label: 'Overview',
      items: [
        { name: '📊 Overview', path: `/dashboard/${guildId}/overview`, icon: '📊' },
      ]
    },
    {
      label: 'Core Features',
      items: [
        { name: 'Welcome & Leave', path: `/dashboard/${guildId}/welcome`, icon: '👋' },
        { name: 'Tickets System', path: `/dashboard/${guildId}/tickets`, icon: '🎫' },
        { name: 'Stream Alerts', path: `/dashboard/${guildId}/stream-alerts`, icon: '📺' },
        { name: 'Registration & Forms', path: `/dashboard/${guildId}/registration`, icon: '📝' },
      ]
    },
    {
      label: 'Security & Moderation',
      items: [
        { name: 'Security & Anti-Spam', path: `/dashboard/${guildId}/security`, icon: '🛡️' },
        { name: 'Staff Roles & Mod', path: `/dashboard/${guildId}/moderation`, icon: '⚖️' },
        { name: 'Server Logs', path: `/dashboard/${guildId}/server-logs`, icon: '📋' },
      ]
    },
    {
      label: 'Community',
      items: [
        { name: 'Giveaways', path: `/dashboard/${guildId}/giveaways`, icon: '🎉' },
        { name: 'Polls', path: `/dashboard/${guildId}/polls`, icon: '📊' },
        { name: 'Community & Suggestions', path: `/dashboard/${guildId}/community`, icon: '🤝' },
        { name: 'Birthdays', path: `/dashboard/${guildId}/birthdays`, icon: '🎂' },
        { name: 'Self Roles', path: `/dashboard/${guildId}/self-roles`, icon: '🎭' },
        { name: 'Leaderboard & XP', path: `/dashboard/${guildId}/leaderboard`, icon: '🏆' },
      ]
    },
    {
      label: 'Server Automation',
      items: [
        { name: 'Sticky Messages', path: `/dashboard/${guildId}/sticky`, icon: '📌' },
        { name: 'Auto Reactions', path: `/dashboard/${guildId}/auto-reactions`, icon: '⚡' },
        { name: 'Custom Commands', path: `/dashboard/${guildId}/custom-commands`, icon: '💬' },
        { name: 'Temp Voice Channels', path: `/dashboard/${guildId}/temp-vc`, icon: '🎙️' },
      ]
    },
    {
      label: 'Entertainment',
      items: [
        { name: 'Music Player', path: `/dashboard/${guildId}/music`, icon: '🎵' },
        { name: 'Radio Station', path: `/dashboard/${guildId}/radio`, icon: '📻' },
        { name: 'Economy & Shop', path: `/dashboard/${guildId}/economy`, icon: '🪙' },
      ]
    },
    {
      label: 'Advanced Features',
      items: [
        { name: 'AI System Studio', path: `/dashboard/${guildId}/ai`, icon: '🤖' },
        { name: 'Voice Announcer', path: `/dashboard/${guildId}/voice-announce`, icon: '🔊' },
        { name: 'Cross-Server Role Sync', path: `/dashboard/${guildId}/role-sync`, icon: '🔗' },
        { name: 'Sync To Other Servers', path: `/dashboard/${guildId}/sync`, icon: '🔄' },
      ]
    },
  ];

  const isActive = (path) => location.pathname === path;

  return (
    <div className="flex animate-fade-in" style={{ height: '100vh', overflow: 'hidden' }}>

      {/* Mobile nav backdrop */}
      {mobileNavOpen && (
        <div
          onClick={() => setMobileNavOpen(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(3,4,10,0.7)',
            backdropFilter: 'blur(4px)', zIndex: 150,
          }}
        />
      )}

      {/* Sidebar */}
      <div className={`sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}>
        {/* App Logo */}
        <Link to="/dashboard" className="sidebar-logo" style={{ textDecoration: 'none' }}>
          <div style={{
            width: '30px', height: '30px', borderRadius: '9px',
            background: 'linear-gradient(135deg, #818cf8, #6366f1 45%, #22d3ee)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '16px', boxShadow: '0 4px 14px -4px rgba(99,102,241,0.7)'
          }}>🤖</div>
          <span className="sidebar-logo-text">{botName} Dashboard</span>
        </Link>

        {/* Selected Guild */}
        <div className="sidebar-guild">
          {guild?.icon ? (
            <img src={guild.icon} alt="Guild" className="sidebar-guild-icon" />
          ) : (
            <div className="sidebar-guild-icon" style={{
              background: 'rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontSize: '14px', fontWeight: 'bold', boxShadow: 'none'
            }}>
              {guild?.name ? guild.name.charAt(0) : '?'}
            </div>
          )}
          <div className="sidebar-guild-name" title={guild?.name || 'Loading...'}>
            {guild?.name || 'Loading...'}
          </div>
        </div>

        {/* Navigation */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {navGroups.map((group, idx) => (
            <div key={idx} style={{ marginBottom: '12px' }}>
              <div className="sidebar-section-label">{group.label}</div>
              {group.items.map(item => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`sidebar-nav-item ${isActive(item.path) ? 'active' : ''}`}
                >
                  <span className="nav-icon">{item.icon}</span>
                  {item.name}
                </Link>
              ))}
            </div>
          ))}
        </div>

        {/* User Profile Footer */}
        <div className="sidebar-user">
          {user?.avatar ? (
            <img src={user.avatar} alt="User" className="sidebar-user-avatar" />
          ) : (
            <div className="sidebar-user-avatar" style={{
              background: 'var(--brand-gradient)', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontWeight: 'bold'
            }}>
              {user?.username?.charAt(0) || 'U'}
            </div>
          )}
          <div className="sidebar-user-name">
            {user?.username || 'User'}
          </div>
          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="theme-toggle"
            title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          >
            {isDark ? '☀️' : '🌙'}
          </button>
          <button
            onClick={() => {
              localStorage.removeItem('bot_dashboard_token');
              window.location.href = '/';
            }}
            style={{
              background: 'transparent', border: 'none', color: 'var(--text-muted)',
              cursor: 'pointer', padding: '4px'
            }}
            title="Logout"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
              <polyline points="16 17 21 12 16 7"></polyline>
              <line x1="21" y1="12" x2="9" y2="12"></line>
            </svg>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ flex: 1, overflowY: 'auto', position: 'relative' }}>
        {/* Topbar */}
        <div className="topbar">
          <button
            type="button"
            className="topbar-toggle"
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open navigation"
          >
            ☰
          </button>

          {/* Breadcrumb in topbar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 0 }}>
            <Link to="/dashboard" style={{ textDecoration: 'none', color: 'var(--text-muted)', fontSize: '13px', whiteSpace: 'nowrap' }}>
              🏰 Servers
            </Link>
            {guild && (
              <>
                <span style={{ color: 'var(--text-muted)', opacity: 0.5 }}>/</span>
                <Link
                  to={`/dashboard/${guildId}/overview`}
                  style={{ textDecoration: 'none', color: 'var(--text-muted)', fontSize: '13px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '140px' }}
                >
                  {guild.name}
                </Link>
              </>
            )}
            {currentPageName && currentPage !== guildId && (
              <>
                <span style={{ color: 'var(--text-muted)', opacity: 0.5, flexShrink: 0 }}>/</span>
                <span style={{ fontSize: '13px', color: 'var(--text-sub)', fontWeight: 600, whiteSpace: 'nowrap' }}>
                  {currentPageName}
                </span>
              </>
            )}
          </div>

          {/* Global Auto-Sync Toggle */}
          <div
            className={`autosync-pill ${autoSync ? 'on' : ''}`}
            onClick={toggleAutoSync}
            role="button"
            tabIndex={0}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') toggleAutoSync(); }}
            title={autoSync
              ? 'Auto-sync is ON — every edit is applied to all your other servers.'
              : 'Auto-sync is OFF — edits only affect this server.'}
            style={{ cursor: 'pointer', userSelect: 'none' }}
          >
            <span className="autosync-dot" />
            <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-main)' }}>🔄</span>
            <span className="autosync-label-text">
              <span style={{ fontSize: '12.5px', fontWeight: 700, color: autoSync ? '#a5b4fc' : 'var(--text-sub)', display: 'block', lineHeight: 1.2 }}>
                Auto-sync: {autoSync ? 'ON' : 'OFF'}
              </span>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', lineHeight: 1.3 }}>
                {autoSync ? 'All servers' : 'This server only'}
              </span>
            </span>
          </div>
        </div>

        <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '32px 36px 56px' }}>
          <Outlet />
        </div>
      </div>

    </div>
  );
}

export default DashboardLayout;
