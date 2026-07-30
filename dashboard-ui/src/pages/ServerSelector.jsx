import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';

function ServerSelector() {
  const [guilds, setGuilds] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchGuilds = async () => {
      try {
        const res = await api.get('/users/@me');
        setGuilds(res.data.guilds);
      } catch (err) {
        console.error('Failed to fetch guilds', err);
      }
      setLoading(false);
    };
    fetchGuilds();
  }, []);

  return (
    <div className="animate-fade-in" style={{ padding: '60px 40px', maxWidth: '1200px', margin: '0 auto' }}>
      <div className="page-header" style={{ textAlign: 'center', marginBottom: '48px' }}>
        <h2 className="page-title" style={{ justifyContent: 'center', fontSize: '32px' }}>
          Select a Server
        </h2>
        <p className="page-subtitle" style={{ fontSize: '16px' }}>
          Choose a server to manage its settings and features.
        </p>
      </div>
      
      {loading ? (
        <div className="grid-auto stagger">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="card skeleton" style={{ height: '90px' }} />
          ))}
        </div>
      ) : guilds.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">🕵️</div>
          <h3 className="empty-state-title">No servers found</h3>
          <p className="empty-state-desc">
            Make sure the bot is invited to a server where you have<br/>
            <strong>Administrator</strong> permissions.
          </p>
          <a href="https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot%20applications.commands" 
             target="_blank" rel="noreferrer" 
             className="btn btn-primary" style={{ marginTop: '20px' }}>
            Invite Bot
          </a>
        </div>
      ) : (
        <div className="grid-auto stagger">
          {guilds.map(guild => (
            <Link to={`/dashboard/${guild.id}`} key={guild.id} className="card card-clickable flex items-center gap-4">
              {guild.icon ? (
                <img src={guild.icon} alt={guild.name} style={{ width: '56px', height: '56px', borderRadius: '16px', objectFit: 'cover' }} />
              ) : (
                <div style={{ 
                  width: '56px', height: '56px', borderRadius: '16px', 
                  background: 'linear-gradient(135deg, var(--primary), var(--accent))', 
                  display: 'flex', alignItems: 'center', justifyContent: 'center', 
                  fontSize: '24px', fontWeight: 'bold', color: 'white',
                  textShadow: '0 2px 4px rgba(0,0,0,0.3)'
                }}>
                  {guild.name.charAt(0)}
                </div>
              )}
              <div style={{ overflow: 'hidden' }}>
                <div style={{ fontWeight: '600', fontSize: '15px', color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {guild.name}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Click to manage
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
