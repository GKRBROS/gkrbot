import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';

function Leaderboard() {
  const { guildId } = useParams();
  const [activeTab, setActiveTab] = useState('voice'); // 'voice' | 'economy'
  const [voiceData, setVoiceData] = useState([]);
  const [economyData, setEconomyData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const fetchData = async () => {
    try {
      setLoading(true);
      const res = await api.get(`/guilds/${guildId}/leaderboard`);
      setVoiceData(res.data.voice || []);
      setEconomyData(res.data.economy || []);
      setError('');
    } catch (err) {
      console.error('Failed to load leaderboard', err);
      setError(err.response?.data?.error || 'Failed to load leaderboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const filteredVoice = voiceData.filter(v =>
    v.username.toLowerCase().includes(search.toLowerCase()) || v.user_id.includes(search)
  );

  const filteredEconomy = economyData.filter(e =>
    e.username.toLowerCase().includes(search.toLowerCase()) || e.user_id.includes(search)
  );

  const getRankBadge = (index) => {
    if (index === 0) return <span style={{ fontSize: '20px' }}>🥇</span>;
    if (index === 1) return <span style={{ fontSize: '20px' }}>🥈</span>;
    if (index === 2) return <span style={{ fontSize: '20px' }}>🥉</span>;
    return <span style={{ fontWeight: '700', color: 'var(--text-muted)' }}>#{index + 1}</span>;
  };

  if (loading) {
    return <div className="feature-page" style={{ padding: '40px', textAlign: 'center' }}>Loading Leaderboards...</div>;
  }

  return (
    <div className="feature-page">
      <div className="feature-header">
        <div>
          <h1 className="feature-title">🏆 Server Leaderboards</h1>
          <p className="feature-desc">Rankings for Voice Channel Activity, Levels, XP, and Server Economy Net Worth.</p>
        </div>
        <button className="btn-secondary" onClick={fetchData}>
          🔄 Refresh
        </button>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '16px' }}>
          {error}
        </div>
      )}

      {/* Tabs & Search Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
        <div className="tabs-container" style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)' }}>
          <button
            className={`tab-btn ${activeTab === 'voice' ? 'active' : ''}`}
            onClick={() => setActiveTab('voice')}
            style={{
              padding: '10px 18px', border: 'none', background: 'transparent',
              cursor: 'pointer', fontWeight: '600',
              color: activeTab === 'voice' ? 'var(--primary)' : 'var(--text-muted)',
              borderBottom: activeTab === 'voice' ? '2px solid var(--primary)' : 'none'
            }}
          >
            🎙️ Voice XP & Hours ({voiceData.length})
          </button>
          <button
            className={`tab-btn ${activeTab === 'economy' ? 'active' : ''}`}
            onClick={() => setActiveTab('economy')}
            style={{
              padding: '10px 18px', border: 'none', background: 'transparent',
              cursor: 'pointer', fontWeight: '600',
              color: activeTab === 'economy' ? 'var(--primary)' : 'var(--text-muted)',
              borderBottom: activeTab === 'economy' ? '2px solid var(--primary)' : 'none'
            }}
          >
            🪙 Economy Net Worth ({economyData.length})
          </button>
        </div>

        <input
          type="text"
          className="form-input"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="🔍 Search members..."
          style={{ width: '240px' }}
        />
      </div>

      {/* VOICE TAB */}
      {activeTab === 'voice' && (
        <div className="dashboard-card" style={{ padding: '20px' }}>
          {filteredVoice.length === 0 ? (
            <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
              No voice activity recorded yet.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '12px 8px', width: '60px' }}>Rank</th>
                    <th style={{ padding: '12px 8px' }}>Member</th>
                    <th style={{ padding: '12px 8px' }}>Level</th>
                    <th style={{ padding: '12px 8px' }}>Voice Time</th>
                    <th style={{ padding: '12px 8px' }}>Total XP</th>
                    <th style={{ padding: '12px 8px' }}>Coins Earned</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredVoice.map((user, idx) => {
                    const hours = (user.total_minutes / 60).toFixed(1);
                    return (
                      <tr key={user.user_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <td style={{ padding: '12px 8px', textAlign: 'center' }}>
                          {getRankBadge(idx)}
                        </td>
                        <td style={{ padding: '12px 8px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            {user.avatar ? (
                              <img src={user.avatar} alt="" style={{ width: '32px', height: '32px', borderRadius: '50%' }} />
                            ) : (
                              <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '12px', fontWeight: 'bold' }}>
                                {user.username.slice(0, 2).toUpperCase()}
                              </div>
                            )}
                            <div>
                              <div style={{ fontWeight: '600', color: 'var(--text-main)' }}>{user.username}</div>
                              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{user.user_id}</div>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: '12px 8px' }}>
                          <span className="badge badge-primary">Lvl {user.level}</span>
                        </td>
                        <td style={{ padding: '12px 8px', fontWeight: '600' }}>
                          {hours} hrs <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>({user.total_minutes}m)</span>
                        </td>
                        <td style={{ padding: '12px 8px', color: '#10b981', fontWeight: '700' }}>
                          {user.xp?.toLocaleString()} XP
                        </td>
                        <td style={{ padding: '12px 8px', color: '#f59e0b', fontWeight: '700' }}>
                          🪙 {user.coins?.toLocaleString()}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ECONOMY TAB */}
      {activeTab === 'economy' && (
        <div className="dashboard-card" style={{ padding: '20px' }}>
          {filteredEconomy.length === 0 ? (
            <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
              No economy accounts recorded yet.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '12px 8px', width: '60px' }}>Rank</th>
                    <th style={{ padding: '12px 8px' }}>Member</th>
                    <th style={{ padding: '12px 8px' }}>Wallet</th>
                    <th style={{ padding: '12px 8px' }}>Bank</th>
                    <th style={{ padding: '12px 8px' }}>Net Worth</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEconomy.map((user, idx) => (
                    <tr key={user.user_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <td style={{ padding: '12px 8px', textAlign: 'center' }}>
                        {getRankBadge(idx)}
                      </td>
                      <td style={{ padding: '12px 8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          {user.avatar ? (
                            <img src={user.avatar} alt="" style={{ width: '32px', height: '32px', borderRadius: '50%' }} />
                          ) : (
                            <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '12px', fontWeight: 'bold' }}>
                              {user.username.slice(0, 2).toUpperCase()}
                            </div>
                          )}
                          <div>
                            <div style={{ fontWeight: '600', color: 'var(--text-main)' }}>{user.username}</div>
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{user.user_id}</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '12px 8px', color: 'var(--text-muted)' }}>
                        🪙 {user.wallet?.toLocaleString()}
                      </td>
                      <td style={{ padding: '12px 8px', color: 'var(--text-muted)' }}>
                        🏦 {user.bank?.toLocaleString()}
                      </td>
                      <td style={{ padding: '12px 8px', color: '#10b981', fontWeight: '700', fontSize: '15px' }}>
                        🪙 {user.total?.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Leaderboard;
