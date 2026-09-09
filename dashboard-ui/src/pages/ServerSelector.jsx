import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';

function ServerSelector() {
  const [guilds, setGuilds] = useState([]);
  const [botClientId, setBotClientId] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchGuilds = async () => {
      try {
        const res = await api.get('/users/@me');
        setGuilds(res.data.guilds || []);
        if (res.data.bot_client_id) {
          setBotClientId(res.data.bot_client_id);
        }
      } catch (err) {
        console.error('Failed to fetch guilds', err);
      }
      setLoading(false);
    };
    fetchGuilds();
  }, []);

  const filtered = guilds.filter(g =>
    g.name.toLowerCase().includes(search.trim().toLowerCase())
  );

  return (
    <div className="animate-fade-in" style={{ padding: '56px 40px', maxWidth: '1200px', margin: '0 auto' }}>
      <div className="page-header" style={{ textAlign: 'center', marginBottom: '40px' }}>
        <div className="landing-badge" style={{ marginBottom: '16px' }}>
          🏰 {guilds.length > 0 ? `${guilds.length} server${guilds.length === 1 ? '' : 's'} under your command` : 'Your servers'}
        </div>
        <h2 className="page-title" style={{ justifyContent: 'center', fontSize: '36px' }}>
          Select a Server
        </h2>
        <p className="page-subtitle" style={{ fontSize: '15.5px' }}>
          Choose a server to manage its settings and features.
        </p>
      </div>

      {/* Search */}
      {!loading && guilds.length > 3 && (
        <div style={{ maxWidth: '420px', margin: '0 auto 36px', position: 'relative' }}>
          <span style={{
            position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-muted)', fontSize: '15px', pointerEvents: 'none'
          }}>
            🔍
          </span>
          <input
            type="text"
            className="input-field"
            placeholder="Search servers..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ paddingLeft: '42px' }}
          />
        </div>
      )}

      {loading ? (
        <div className="grid-auto stagger">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="card skeleton" style={{ height: '96px', border: 'none' }} />
          ))}
        </div>
      ) : guilds.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">🕵️</div>
          <h3 className="empty-state-title">No servers found</h3>
          <p className="empty-state-desc">
            Make sure the bot is invited to a server where you have<br />
            <strong>Administrator</strong> permissions.
          </p>
          {botClientId && (
            <a
              href={`https://discord.com/api/oauth2/authorize?client_id=${botClientId}&permissions=8&scope=bot%20applications.commands`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-primary"
              style={{ marginTop: '22px' }}
            >
              ➕ Invite Bot
            </a>
          )}
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">🔍</div>
          <h3 className="empty-state-title">No matches</h3>
          <p className="empty-state-desc">No server name matches "{search}".</p>
        </div>
      ) : (
        <div className="grid-auto stagger">
          {filtered.map(guild => (
            <Link to={`/dashboard/${guild.id}`} key={guild.id} className="server-card">
              <div className="server-icon-ring">
                {guild.icon ? (
                  <img src={guild.icon} alt={guild.name} />
                ) : (
                  <div className="server-icon-fallback">
                    {guild.name.charAt(0).toUpperCase()}
                  </div>
                )}
              </div>
              <div style={{ overflow: 'hidden', minWidth: 0 }}>
                <div style={{
                  fontWeight: 700, fontSize: '15px', color: 'var(--text-main)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  fontFamily: 'var(--font-display)'
                }}>
                  {guild.name}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '5px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                  <span style={{
                    width: '7px', height: '7px', borderRadius: '50%',
                    background: 'var(--success)', boxShadow: '0 0 8px rgba(52,211,153,0.8)', display: 'inline-block'
                  }} />
                  Manage settings
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default ServerSelector;
