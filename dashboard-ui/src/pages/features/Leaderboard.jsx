import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Trophy,
  Mic,
  Coins,
  Search,
  RefreshCw,
  Clock,
  Wallet,
  Building2,
  Award
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function Leaderboard() {
  const { guildId } = useParams();
  const [activeTab, setActiveTab] = useState('voice'); // 'voice' | 'economy'
  const [voiceData, setVoiceData] = useState([]);
  const [economyData, setEconomyData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      if (!isRefresh) setLoading(true);
      const res = await api.get(`/guilds/${guildId}/leaderboard`);
      setVoiceData(res.data.voice || []);
      setEconomyData(res.data.economy || []);
      setError('');
    } catch (err) {
      console.error('Failed to load leaderboard', err);
      setError(err.response?.data?.error || 'Failed to load leaderboard data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const filteredVoice = voiceData.filter(v =>
    (v.username || '').toLowerCase().includes(search.toLowerCase()) || (v.user_id || '').includes(search)
  );

  const filteredEconomy = economyData.filter(e =>
    (e.username || '').toLowerCase().includes(search.toLowerCase()) || (e.user_id || '').includes(search)
  );

  const formatHours = (seconds) => {
    if (!seconds) return '0h 0m';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="50px" />
        <Skeleton height="360px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Trophy}
        title="Server Leaderboards"
        subtitle="Rankings for Voice Channel Activity, Levels, XP, and Server Economy Net Worth."
        actions={
          <Button
            variant="outline"
            size="sm"
            icon={RefreshCw}
            loading={refreshing}
            onClick={() => fetchData(true)}
          >
            Refresh Standings
          </Button>
        }
      />

      {error && (
        <div style={{
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.25)',
          color: '#f87171',
          fontSize: '13.5px'
        }}>
          {error}
        </div>
      )}

      {/* Tabs & Search Filter Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div style={{
          display: 'flex',
          gap: '6px',
          padding: '4px',
          borderRadius: 'var(--radius-lg)',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)'
        }}>
          <button
            onClick={() => setActiveTab('voice')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              borderRadius: 'var(--radius-md)',
              border: 'none',
              background: activeTab === 'voice' ? 'var(--bg-card)' : 'transparent',
              color: activeTab === 'voice' ? 'var(--text-main)' : 'var(--text-muted)',
              fontWeight: activeTab === 'voice' ? 600 : 500,
              fontSize: '13.5px',
              cursor: 'pointer',
              transition: 'all 150ms ease',
              boxShadow: activeTab === 'voice' ? '0 1px 3px rgba(0, 0, 0, 0.2)' : 'none'
            }}
          >
            <Mic size={16} color={activeTab === 'voice' ? 'var(--primary)' : 'currentColor'} />
            <span>Voice Activity & XP</span>
            <Badge variant={activeTab === 'voice' ? 'primary' : 'neutral'} size="sm">
              {voiceData.length}
            </Badge>
          </button>

          <button
            onClick={() => setActiveTab('economy')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              borderRadius: 'var(--radius-md)',
              border: 'none',
              background: activeTab === 'economy' ? 'var(--bg-card)' : 'transparent',
              color: activeTab === 'economy' ? 'var(--text-main)' : 'var(--text-muted)',
              fontWeight: activeTab === 'economy' ? 600 : 500,
              fontSize: '13.5px',
              cursor: 'pointer',
              transition: 'all 150ms ease',
              boxShadow: activeTab === 'economy' ? '0 1px 3px rgba(0, 0, 0, 0.2)' : 'none'
            }}
          >
            <Coins size={16} color={activeTab === 'economy' ? '#f59e0b' : 'currentColor'} />
            <span>Economy Net Worth</span>
            <Badge variant={activeTab === 'economy' ? 'warning' : 'neutral'} size="sm">
              {economyData.length}
            </Badge>
          </button>
        </div>

        <div style={{ position: 'relative', width: '260px' }}>
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            className="form-input"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search members..."
            style={{ paddingLeft: '36px' }}
          />
        </div>
      </div>

      {/* Leaderboard Table Card */}
      <Card>
        <CardContent style={{ padding: 0 }}>
          {activeTab === 'voice' ? (
            filteredVoice.length === 0 ? (
              <EmptyState
                icon={Mic}
                title="No Voice Data Recorded"
                description={search ? 'No members match your search query.' : 'Members will appear here once they spend time in voice channels.'}
              />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13.5px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', textAlign: 'left', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '14px 18px', width: '70px', fontWeight: 600 }}>Rank</th>
                      <th style={{ padding: '14px 18px', fontWeight: 600 }}>Member</th>
                      <th style={{ padding: '14px 18px', fontWeight: 600 }}>Level</th>
                      <th style={{ padding: '14px 18px', fontWeight: 600 }}>Voice XP</th>
                      <th style={{ padding: '14px 18px', fontWeight: 600, textAlign: 'right' }}>Time in Voice</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredVoice.map((v, i) => {
                      const isTop3 = i < 3;
                      return (
                        <tr key={v.user_id} style={{ borderBottom: '1px solid var(--border)' }}>
                          <td style={{ padding: '14px 18px' }}>
                            <div style={{
                              width: '28px',
                              height: '28px',
                              borderRadius: '6px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '12px',
                              fontWeight: 700,
                              background: i === 0 ? 'rgba(251, 191, 36, 0.15)' : i === 1 ? 'rgba(148, 163, 184, 0.15)' : i === 2 ? 'rgba(180, 83, 9, 0.15)' : 'transparent',
                              color: i === 0 ? '#fbbf24' : i === 1 ? '#94a3b8' : i === 2 ? '#d97706' : 'var(--text-muted)'
                            }}>
                              #{i + 1}
                            </div>
                          </td>
                          <td style={{ padding: '14px 18px' }}>
                            <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                              {v.username || `User ${v.user_id.slice(0, 6)}...`}
                            </div>
                            <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                              {v.user_id}
                            </div>
                          </td>
                          <td style={{ padding: '14px 18px' }}>
                            <Badge variant="primary" size="sm">Level {v.level || 1}</Badge>
                          </td>
                          <td style={{ padding: '14px 18px', color: 'var(--text-main)', fontWeight: 500 }}>
                            {v.xp?.toLocaleString() || 0} XP
                          </td>
                          <td style={{ padding: '14px 18px', textAlign: 'right', fontWeight: 600, color: '#10b981' }}>
                            {formatHours(v.time_spent_seconds || v.voice_seconds || 0)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            filteredEconomy.length === 0 ? (
              <EmptyState
                icon={Coins}
                title="No Economy Balances"
                description={search ? 'No members match your search query.' : 'Member balances will appear here as they earn and trade coins.'}
              />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13.5px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', textAlign: 'left', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '14px 18px', width: '70px', fontWeight: 600 }}>Rank</th>
                      <th style={{ padding: '14px 18px', fontWeight: 600 }}>Member</th>
                      <th style={{ padding: '14px 18px', fontWeight: 600 }}>Wallet</th>
                      <th style={{ padding: '14px 18px', fontWeight: 600 }}>Bank Vault</th>
                      <th style={{ padding: '14px 18px', fontWeight: 600, textAlign: 'right' }}>Total Net Worth</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEconomy.map((e, i) => {
                      return (
                        <tr key={e.user_id} style={{ borderBottom: '1px solid var(--border)' }}>
                          <td style={{ padding: '14px 18px' }}>
                            <div style={{
                              width: '28px',
                              height: '28px',
                              borderRadius: '6px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '12px',
                              fontWeight: 700,
                              background: i === 0 ? 'rgba(251, 191, 36, 0.15)' : i === 1 ? 'rgba(148, 163, 184, 0.15)' : i === 2 ? 'rgba(180, 83, 9, 0.15)' : 'transparent',
                              color: i === 0 ? '#fbbf24' : i === 1 ? '#94a3b8' : i === 2 ? '#d97706' : 'var(--text-muted)'
                            }}>
                              #{i + 1}
                            </div>
                          </td>
                          <td style={{ padding: '14px 18px' }}>
                            <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                              {e.username || `User ${e.user_id.slice(0, 6)}...`}
                            </div>
                            <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                              {e.user_id}
                            </div>
                          </td>
                          <td style={{ padding: '14px 18px', color: 'var(--text-muted)' }}>
                            🪙 {e.wallet?.toLocaleString() || 0}
                          </td>
                          <td style={{ padding: '14px 18px', color: 'var(--text-muted)' }}>
                            🏛️ {e.bank?.toLocaleString() || 0}
                          </td>
                          <td style={{ padding: '14px 18px', textAlign: 'right', fontWeight: 700, color: '#f59e0b' }}>
                            🪙 {e.total?.toLocaleString() || 0}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default Leaderboard;
