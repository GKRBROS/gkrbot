import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../../api';

function Overview() {
  const { guildId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchOverview = async () => {
    try {
      setLoading(true);
      const res = await api.get(`/guilds/${guildId}/overview`);
      setData(res.data);
      setError('');
    } catch (err) {
      console.error('Failed to load overview', err);
      setError(err.response?.data?.error || 'Failed to load server overview.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, [guildId]);

  if (loading) {
    return (
      <div className="feature-page" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '400px' }}>
        <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: '32px', marginBottom: '12px' }}>📊</div>
          <div>Loading server overview...</div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="feature-page">
        <div className="alert alert-danger" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{error || 'Unable to fetch server data.'}</span>
          <button className="btn-secondary" onClick={fetchOverview} style={{ padding: '6px 14px' }}>Retry</button>
        </div>
      </div>
    );
  }

  const { guild, bot, features } = data;

  const featureCards = [
    { title: 'Welcome & Leave', icon: '👋', path: 'welcome', active: features.welcome, desc: 'Aesthetic welcome cards, roles & leave logs' },
    { title: 'Tickets System', icon: '🎫', path: 'tickets', active: features.tickets, count: features.tickets_count, desc: 'Multi-category ticket hubs, modals & logs' },
    { title: 'Stream Alerts', icon: '📺', path: 'stream-alerts', active: features.stream_alerts, count: features.stream_alerts_count, desc: 'Twitch, YouTube, Kick live alerts' },
    { title: 'Registration & Forms', icon: '📝', path: 'registration', active: features.registration, count: features.registration_count, desc: 'Interactive forms, automations & reviewer panel' },
    { title: 'Giveaways', icon: '🎉', path: 'giveaways', active: features.giveaways, count: features.active_giveaways_count, desc: 'Timed button-based giveaways with auto-draw' },
    { title: 'Polls', icon: '📊', path: 'polls', active: features.polls, count: features.active_polls_count, desc: 'Live progress bar voting & timed auto-close' },
    { title: 'Self Roles', icon: '🎭', path: 'self-roles', active: features.self_roles, count: features.self_roles_count, desc: 'Button & dropdown role assignment menus' },
    { title: 'Server Logs', icon: '📋', path: 'server-logs', active: true, desc: 'Detailed audit categories & event routing' },
    { title: 'Birthdays', icon: '🎂', path: 'birthdays', active: features.birthdays, count: features.birthdays_count, desc: 'Automatic birthday wishes & calendar' },
    { title: 'Leaderboards', icon: '🏆', path: 'leaderboard', active: true, desc: 'Voice XP rankings, coins & top members' },
    { title: 'Security & Anti-Nuke', icon: '🛡️', path: 'security', active: features.security, desc: 'Anti-spam, raid defense & rate limits' },
    { title: 'Radio 24/7', icon: '📻', path: 'radio', active: features.radio, desc: 'Ultra-low CPU 24/7 lofi & radio streams' },
    { title: 'AI System', icon: '🤖', path: 'ai', active: features.ai, desc: 'Autonomous chat, deep research & memories' },
    { title: 'Economy System', icon: '🪙', path: 'economy', active: true, desc: 'Server currency, custom shop items & balances' },
    { title: 'Temporary Voice', icon: '🎙️', path: 'temp-vc', active: true, desc: 'Auto-create join-to-create voice channels' },
    { title: 'Cross-Server Role Sync', icon: '🔗', path: 'role-sync', active: true, desc: 'Real-time role mirror across linked guilds' },
  ];

  const configuredCount = featureCards.filter(f => f.active).length;

  return (
    <div className="feature-page">
      {/* Hero Server Header */}
      <div className="dashboard-card" style={{
        background: 'linear-gradient(135deg, rgba(88, 101, 242, 0.15) 0%, rgba(30, 41, 59, 0.7) 100%)',
        borderColor: 'rgba(88, 101, 242, 0.3)',
        marginBottom: '24px',
        padding: '28px',
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
            {guild.icon ? (
              <img src={guild.icon} alt={guild.name} style={{ width: '76px', height: '76px', borderRadius: '20px', border: '2px solid rgba(255,255,255,0.1)' }} />
            ) : (
              <div style={{
                width: '76px', height: '76px', borderRadius: '20px',
                background: 'var(--primary)', color: '#fff',
                fontSize: '28px', fontWeight: 'bold',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}>
                {guild.name.slice(0, 2).toUpperCase()}
              </div>
            )}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <h1 style={{ fontSize: '26px', fontWeight: '800', margin: 0, color: 'var(--text-main)' }}>{guild.name}</h1>
                <span className="badge badge-success" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981' }}></span>
                  Active
                </span>
              </div>
              <p style={{ margin: '6px 0 0', color: 'var(--text-muted)', fontSize: '14px' }}>
                Managed by <strong style={{ color: 'var(--text-main)' }}>{bot.name}</strong> • Connected via Discord API
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button className="btn-secondary" onClick={fetchOverview} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              🔄 Refresh
            </button>
            <Link to={`/dashboard/${guildId}/server-logs`} className="btn-primary" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '6px' }}>
              📋 Audit Logs
            </Link>
          </div>
        </div>
      </div>

      {/* Stats Counter Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '28px' }}>
        <div className="dashboard-card" style={{ padding: '20px' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Members</div>
          <div style={{ fontSize: '28px', fontWeight: '800', color: 'var(--text-main)', marginTop: '8px' }}>
            {guild.member_count?.toLocaleString() || 0}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>Server population</div>
        </div>

        <div className="dashboard-card" style={{ padding: '20px' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Channels</div>
          <div style={{ fontSize: '28px', fontWeight: '800', color: 'var(--text-main)', marginTop: '8px' }}>
            {guild.channel_count || 0}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>Text & Voice channels</div>
        </div>

        <div className="dashboard-card" style={{ padding: '20px' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Roles</div>
          <div style={{ fontSize: '28px', fontWeight: '800', color: 'var(--text-main)', marginTop: '8px' }}>
            {guild.role_count || 0}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>Configured permissions</div>
        </div>

        <div className="dashboard-card" style={{ padding: '20px' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Bot Latency</div>
          <div style={{ fontSize: '28px', fontWeight: '800', color: '#10b981', marginTop: '8px' }}>
            {bot.latency_ms} <span style={{ fontSize: '14px', fontWeight: 'normal', color: 'var(--text-muted)' }}>ms</span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>WebSocket heartbeat</div>
        </div>

        <div className="dashboard-card" style={{ padding: '20px' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Features Active</div>
          <div style={{ fontSize: '28px', fontWeight: '800', color: 'var(--primary)', marginTop: '8px' }}>
            {configuredCount} <span style={{ fontSize: '14px', fontWeight: 'normal', color: 'var(--text-muted)' }}>/ {featureCards.length}</span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>System coverage</div>
        </div>
      </div>

      {/* Feature Navigation Grid */}
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', margin: 0, color: 'var(--text-main)' }}>Management Modules</h2>
        <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Click any card to open configuration</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px', marginBottom: '32px' }}>
        {featureCards.map(fc => (
          <Link
            key={fc.path}
            to={`/dashboard/${guildId}/${fc.path}`}
            style={{ textDecoration: 'none', color: 'inherit' }}
          >
            <div
              className="dashboard-card"
              style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                cursor: 'pointer',
                transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                border: '1px solid var(--border-color)',
                padding: '20px',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.transform = 'translateY(-3px)';
                e.currentTarget.style.borderColor = 'var(--primary)';
                e.currentTarget.style.boxShadow = '0 10px 24px -10px rgba(0,0,0,0.5)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.transform = 'none';
                e.currentTarget.style.borderColor = 'var(--border-color)';
                e.currentTarget.style.boxShadow = 'none';
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                  <div style={{
                    width: '44px', height: '44px', borderRadius: '12px',
                    background: 'rgba(88, 101, 242, 0.1)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '22px'
                  }}>
                    {fc.icon}
                  </div>
                  {fc.active ? (
                    <span className="badge badge-success" style={{ fontSize: '11px' }}>
                      {fc.count !== undefined ? `${fc.count} Active` : 'Active'}
                    </span>
                  ) : (
                    <span className="badge badge-muted" style={{ fontSize: '11px', opacity: 0.6 }}>Inactive</span>
                  )}
                </div>
                <h3 style={{ fontSize: '16px', fontWeight: '700', margin: '0 0 6px', color: 'var(--text-main)' }}>
                  {fc.title}
                </h3>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>
                  {fc.desc}
                </p>
              </div>

              <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', fontSize: '13px', color: 'var(--primary)', fontWeight: '600' }}>
                Configure &rarr;
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default Overview;
