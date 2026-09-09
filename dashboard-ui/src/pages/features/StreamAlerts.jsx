import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { withSync, syncParams } from '../../sync';
import { Select } from '../../components/Select';

function StreamAlerts() {
  const { guildId } = useParams();
  const [alerts, setAlerts] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [editingAlert, setEditingAlert] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const [addPlatform, setAddPlatform] = useState('youtube');
  const [addChannel, setAddChannel] = useState('');

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
      platform: addPlatform,
      creator_username: e.target.username.value,
      notification_channel_id: addChannel,
    };

    if (!data.creator_username || !data.notification_channel_id) return;

    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/stream-alerts`, withSync(data));
      await fetchData();
      e.target.reset();
      setAddChannel('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add alert');
    }
    setSubmitting(false);
  };

  const handleDeleteAlert = async (platform, username) => {
    if (!window.confirm(`Are you sure you want to delete the alert for ${username}?`)) return;
    try {
      await api.delete(`/guilds/${guildId}/stream-alerts/${platform}/${username}`, { params: syncParams() });
      await fetchData();
    } catch (err) {
      console.error('Failed to delete alert', err);
    }
  };

  const openEditAlert = (alert) => {
    setEditingAlert(alert);
    setEditForm({
      notification_channel_id: alert.notification_channel_id || '',
      notify_live: !!alert.notify_live,
      notify_videos: !!alert.notify_videos,
      custom_live_message: alert.custom_live_message || '',
      custom_video_message: alert.custom_video_message || '',
    });
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingAlert || !editForm.notification_channel_id) return;
    setEditSaving(true);
    try {
      await api.put(
        `/guilds/${guildId}/stream-alerts/${editingAlert.platform}/${editingAlert.creator_username}`,
        withSync(editForm)
      );
      setEditingAlert(null);
      setEditForm(null);
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update alert');
    }
    setEditSaving(false);
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
            <Select
              value={addPlatform}
              onChange={setAddPlatform}
              options={[
                { value: 'youtube', label: '▶️ YouTube' },
                { value: 'twitch', label: '🟣 Twitch' },
                { value: 'kick', label: '🟢 Kick' },
              ]}
            />
          </div>
          <div className="form-group" style={{ flex: 2, minWidth: '200px', marginBottom: 0 }}>
            <label className="form-label">Channel Name/Handle</label>
            <input type="text" name="username" placeholder="e.g. @PewDiePie" className="input-field" required />
          </div>
          <div className="form-group" style={{ flex: 2, minWidth: '200px', marginBottom: 0 }}>
            <label className="form-label">Notification Channel</label>
            <Select
              value={addChannel}
              onChange={setAddChannel}
              options={channels.map(ch => ({ value: ch.id, label: '# ' + ch.name }))}
              placeholder="Select a channel..."
              searchable
            />
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
                  <div style={{ display: 'flex', gap: '2px' }}>
                    <button
                      onClick={() => openEditAlert(alert)}
                      className="btn btn-icon btn-ghost"
                      style={{ color: 'var(--primary)', padding: '4px', margin: '-8px' }}
                      title="Edit Alert"
                    >
                      ✏️
                    </button>
                    <button
                      onClick={() => handleDeleteAlert(alert.platform, alert.creator_username)}
                      className="btn btn-icon btn-ghost"
                      style={{ color: 'var(--danger)', padding: '4px', margin: '-8px' }}
                      title="Remove Alert"
                    >
                      🗑️
                    </button>
                  </div>
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

      {/* Edit Alert Modal */}
      {editingAlert && editForm && (
        <div className="modal-overlay">
          <form
            onSubmit={handleSaveEdit}
            className="card glass-panel animate-fade-in"
            style={{ width: '100%', maxWidth: '520px', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(88,101,242,0.3)' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                ✏️ Edit Alert — {editingAlert.creator_username}
              </h3>
              <button
                type="button"
                onClick={() => { setEditingAlert(null); setEditForm(null); }}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', fontSize: '20px', cursor: 'pointer', padding: '4px 8px' }}
              >
                ✕
              </button>
            </div>

            {error && <div className="alert alert-error">{error}</div>}

            <div className="form-group">
              <label className="form-label">Notification Channel</label>
              <Select
                value={editForm.notification_channel_id}
                onChange={v => setEditForm({ ...editForm, notification_channel_id: v })}
                options={channels.map(ch => ({ value: ch.id, label: '# ' + ch.name }))}
                placeholder="Select a channel..."
                searchable
              />
            </div>

            <div className="toggle-wrapper" style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '14px', fontWeight: 600 }}>Notify on Live Streams</div>
              <button
                type="button"
                className={`toggle ${editForm.notify_live ? 'active' : ''}`}
                onClick={() => setEditForm({ ...editForm, notify_live: !editForm.notify_live })}
                aria-label="Toggle live notifications"
              ></button>
            </div>

            <div className="toggle-wrapper" style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '14px', fontWeight: 600 }}>Notify on New Videos</div>
              <button
                type="button"
                className={`toggle ${editForm.notify_videos ? 'active' : ''}`}
                onClick={() => setEditForm({ ...editForm, notify_videos: !editForm.notify_videos })}
                aria-label="Toggle video notifications"
              ></button>
            </div>

            <div className="form-group">
              <label className="form-label">Custom Live Message (optional)</label>
              <textarea
                className="input-field"
                rows={2}
                value={editForm.custom_live_message}
                onChange={e => setEditForm({ ...editForm, custom_live_message: e.target.value })}
                placeholder="Leave empty to use the default live message"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Custom Video Message (optional)</label>
              <textarea
                className="input-field"
                rows={2}
                value={editForm.custom_video_message}
                onChange={e => setEditForm({ ...editForm, custom_video_message: e.target.value })}
                placeholder="Leave empty to use the default video message"
              />
            </div>

            <div className="flex justify-end gap-3 mt-4">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => { setEditingAlert(null); setEditForm(null); }}
              >
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={editSaving}>
                {editSaving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default StreamAlerts;
