import { Outlet, Link, useParams, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import api from '../api';

function DashboardLayout({ user }) {
  const { guildId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [guild, setGuild] = useState(null);

  useEffect(() => {
    // Fetch guild details from user's guilds
    api.get('/users/@me').then(res => {
      const found = res.data.guilds.find(g => g.id === guildId);
      if (found) setGuild(found);
    }).catch(console.error);
  }, [guildId]);

  const navGroups = [
    {
      label: 'Core Features',
      items: [
        { name: 'Stream Alerts', path: `/dashboard/${guildId}/stream-alerts`, icon: '📺' },
        { name: 'Tickets', path: `/dashboard/${guildId}/tickets`, icon: '🎫' },
        { name: 'Welcome Message', path: `/dashboard/${guildId}/welcome`, icon: '👋' },
      ]
    },
    {
      label: 'Entertainment',
      items: [
        { name: 'Music Player', path: `/dashboard/${guildId}/music`, icon: '🎵' },
      ]
    }
  ];

  const isActive = (path) => location.pathname === path;

  return (
    <div className="flex animate-fade-in" style={{ height: '100vh', overflow: 'hidden' }}>
      
      {/* Sidebar */}
      <div className="sidebar">
        {/* App Logo */}
        <Link to="/dashboard" className="sidebar-logo" style={{ textDecoration: 'none' }}>
          <div style={{
            width: '28px', height: '28px', borderRadius: '6px',
            background: 'linear-gradient(135deg, var(--primary), var(--accent))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '16px'
          }}>🤖</div>
          <span className="sidebar-logo-text">GKR Dashboard</span>
        </Link>

        {/* Selected Guild */}
        <div className="sidebar-guild">
          {guild?.icon ? (
            <img src={guild.icon} alt="Guild" className="sidebar-guild-icon" />
          ) : (
            <div className="sidebar-guild-icon" style={{
              background: 'rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', 
              justifyContent: 'center', fontSize: '14px', fontWeight: 'bold'
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
            <div key={idx} style={{ marginBottom: '16px' }}>
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
              background: 'var(--primary)', display: 'flex', alignItems: 'center', 
              justifyContent: 'center', fontWeight: 'bold'
            }}>
              {user?.username?.charAt(0) || 'U'}
            </div>
          )}
          <div className="sidebar-user-name">
            {user?.username || 'User'}
          </div>
          <button 
            onClick={() => {
              localStorage.removeItem('session_token');
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
      <div style={{ flex: 1, backgroundColor: 'var(--bg)', overflowY: 'auto', position: 'relative' }}>
        <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '40px' }}>
          <Outlet />
        </div>
      </div>

    </div>
  );
}

export default DashboardLayout;
