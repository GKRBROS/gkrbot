import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';

function StreamAlerts() {
  const { guildId } = useParams();
  const [alerts, setAlerts] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const fetchData = async () => {
    try {
      const [alertsRes, channelsRes] = await Promise.all([
        api.get(`/guilds/${guildId}/stream-alerts`),
        api.get(`/guilds/${guildId}/channels`)
      ]);
      setAlerts(alertsRes.data.alerts || []);
      setChannels(channelsRes.data.channels || []);
    } catch (err) {
      console.error('Failed to fetch stream alerts data', err);
    }
    setLoading(false);
  };

  const handleAddAlert = async (e) => {
    e.preventDefault();
    setError('');
    
    const data = {
      platform: e.target.platform.value,
      creator_username: e.target.username.value,
      notification_channel_id: e.target.channel.value,
    };
    
    if (!data.creator_username || !data.notification_channel_id) return;
    
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/stream-alerts`, data);
      await fetchData();
      e.target.reset();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add alert');
    }
    setSubmitting(false);
  };

  const handleDeleteAlert = async (platform, username) => {
    if (!window.confirm(`Are you sure you want to delete the alert for ${username}?`)) return;
    try {
      await api.delete(`/guilds/${guildId}/stream-alerts/${platform}/${username}`);
      await fetchData();
    } catch (err) {
      console.error('Failed to delete alert', err);
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '200px', marginBottom: '24px' }}></div>
        <div className="grid-auto">
          {[1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: '140px' }}></div>)}
        </div>
      </div>
    );
  }

  const getPlatformBadge = (platform) => {
    switch (platform) {
      case 'youtube': return <span className="badge badge-youtube"><span className="platform-dot youtube"></span> YouTube</span>;
      case 'twitch': return <span className="badge badge-twitch"><span className="platform-dot twitch"></span> Twitch</span>;
      case 'kick': return <span className="badge badge-kick"><span className="platform-dot kick"></span> Kick</span>;
      default: return <span className="badge">{platform}</span>;
    }
  };

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">📺 Stream Alerts</h1>
        <p className="page-subtitle">Configure automatic notifications for YouTube, Twitch, and Kick.</p>
      </div>

      <div className="glass-panel" style={{ padding: '24px', marginBottom: '32px', border: '1px solid var(--primary)' }}>
        <h3 className="section-title" style={{ marginBottom: '20px', border: 'none', padding: 0 }}>
          Add New Alert
        </h3>
        {error && <div className="alert alert-error">{error}</div>}
        
        <form onSubmit={handleAddAlert} className="flex gap-4 items-end" style={{ flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: 1, minWidth: '150px', marginBottom: 0 }}>
            <label className="form-label">Platform</label>
            <select name="platform" className="input-field" required>
              <option value="youtube">YouTube</option>
              <option value="twitch">Twitch</option>
              <option value="kick">Kick</option>
            </select>
          </div>
          <div className="form-group" style={{ flex: 2, minWidth: '200px', marginBottom: 0 }}>
            <label className="form-label">Channel Name/Handle</label>
            <input type="text" name="username" placeholder="e.g. @PewDiePie" className="input-field" required />
          </div>
          <div className="form-group" style={{ flex: 2, minWidth: '200px', marginBottom: 0 }}>
            <label className="form-label">Notification Channel</label>
            <select name="channel" className="input-field" required>
              <option value="">Select a channel...</option>
              {channels.map(ch => (
                <option key={ch.id} value={ch.id}>#{ch.name}</option>
              ))}
            </select>
          </div>
          <div>
            <button type="submit" className="btn btn-primary" style={{ padding: '10px 24px' }} disabled={submitting}>
              {submitting ? 'Adding...' : '+ Add Alert'}
            </button>
          </div>
        </form>
      </div>

      <div className="section-header">
        <h2 className="section-title">Active Alerts <span className="section-count">{alerts.length}</span></h2>
      </div>

      {alerts.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">📡</div>
          <h3 className="empty-state-title">No Alerts Found</h3>
          <p className="empty-state-desc">Add a YouTube, Twitch, or Kick channel above to start receiving notifications.</p>
        </div>
      ) : (
        <div className="grid-auto stagger">
          {alerts.map(alert => (
            <div key={`${alert.platform}-${alert.creator_username}`} className="card flex flex-col justify-between" style={{ position: 'relative' }}>
              <div>
                <div className="flex items-center justify-between" style={{ marginBottom: '16px' }}>
                  {getPlatformBadge(alert.platform)}
                  <button 
                    onClick={() => handleDeleteAlert(alert.platform, alert.creator_username)} 
                    className="btn btn-icon btn-ghost" 
                    style={{ color: 'var(--danger)', padding: '4px', margin: '-8px' }} 
                    title="Remove Alert"
                  >
                    🗑️
                  </button>
                </div>
                
                <h4 style={{ fontSize: '18px', fontWeight: 'bold', marginBottom: '8px', color: 'var(--text-main)', wordBreak: 'break-all' }}>
                  {alert.creator_username}
                </h4>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--text-muted)' }}>
                  <span style={{ color: 'var(--primary)' }}>#</span>
                  {channels.find(c => c.id === alert.notification_channel_id)?.name || 'Unknown Channel'}
                </div>
              </div>
              
              <div style={{ marginTop: '20px', borderTop: '1px solid var(--border)', paddingTop: '12px', display: 'flex', gap: '12px' }}>
                <label className="flex items-center gap-2" style={{ fontSize: '12px', color: alert.notify_live ? 'var(--text-main)' : 'var(--text-muted)' }}>
                  <input type="checkbox" checked={alert.notify_live} readOnly style={{ accentColor: 'var(--primary)' }} /> 
                  Live Streams
                </label>
                <label className="flex items-center gap-2" style={{ fontSize: '12px', color: alert.notify_videos ? 'var(--text-main)' : 'var(--text-muted)' }}>
                  <input type="checkbox" checked={alert.notify_videos} readOnly style={{ accentColor: 'var(--primary)' }} /> 
                  Videos
                </label>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default StreamAlerts;
