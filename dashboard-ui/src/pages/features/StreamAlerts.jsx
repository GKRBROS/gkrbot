import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Tv,
  Plus,
  Trash2,
  Edit2,
  Radio,
  Video,
  Hash,
  CheckCircle2,
  AlertCircle,
  ExternalLink
} from 'lucide-react';
import api from '../../api';
import { withSync, syncParams } from '../../sync';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import Toggle from '../../components/Toggle';
import Modal from '../../components/Modal';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function StreamAlerts() {
  const { guildId } = useParams();
  const [alerts, setAlerts] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [editingAlert, setEditingAlert] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const [addPlatform, setAddPlatform] = useState('youtube');
  const [addUsername, setAddUsername] = useState('');
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
      setError(err.response?.data?.error || 'Failed to load stream alerts');
    } finally {
      setLoading(false);
    }
  };

  const handleAddAlert = async (e) => {
    e.preventDefault();
    setError('');

    const data = {
      platform: addPlatform,
      creator_username: addUsername.trim(),
      notification_channel_id: addChannel,
    };

    if (!data.creator_username || !data.notification_channel_id) {
      setError('Creator handle and destination channel are required.');
      return;
    }

    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/stream-alerts`, withSync(data));
      await fetchData();
      setSuccess(`Stream alert registered for ${data.creator_username}!`);
      setTimeout(() => setSuccess(''), 3000);
      setAddUsername('');
      setAddChannel('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add alert');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteAlert = async (platform, username) => {
    if (!window.confirm(`Delete automatic alert for ${username}?`)) return;
    try {
      await api.delete(`/guilds/${guildId}/stream-alerts/${platform}/${username}`, { params: syncParams() });
      await fetchData();
      setSuccess(`Alert for ${username} removed.`);
      setTimeout(() => setSuccess(''), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete alert');
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
      setSuccess('Alert parameters updated successfully!');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update alert');
    } finally {
      setEditSaving(false);
    }
  };

  const channelOptions = channels.map(ch => ({ value: ch.id, label: `#${ch.name}` }));

  const getPlatformBadge = (platform) => {
    switch (platform) {
      case 'youtube':
        return <Badge variant="danger" size="sm">YouTube</Badge>;
      case 'twitch':
        return <Badge variant="primary" size="sm">Twitch</Badge>;
      case 'kick':
        return <Badge variant="success" size="sm">Kick</Badge>;
      default:
        return <Badge variant="neutral" size="sm">{platform}</Badge>;
    }
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="160px" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
          <Skeleton height="180px" />
          <Skeleton height="180px" />
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Tv}
        title="Live Stream & Video Alerts"
        subtitle="Broadcast automatic announcements when favorite creators go live on YouTube, Twitch, or Kick."
      />

      {error && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.25)',
          color: '#f87171',
          fontSize: '13.5px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertCircle size={17} />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError('')}
            style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '16px' }}
          >
            ✕
          </button>
        </div>
      )}

      {success && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(16, 185, 129, 0.1)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          color: '#34d399',
          fontSize: '13.5px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <CheckCircle2 size={17} />
            <span>{success}</span>
          </div>
          <button
            onClick={() => setSuccess('')}
            style={{ background: 'transparent', border: 'none', color: '#34d399', cursor: 'pointer', fontSize: '16px' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Add Alert Card */}
      <Card>
        <CardHeader>
          <CardTitle>Track New Creator</CardTitle>
          <CardDescription>
            Register a channel handle to automatically ping Discord when content is published or live streams commence.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAddAlert} style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ minWidth: '150px', flex: '0.8' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Streaming Platform
              </label>
              <Select
                value={addPlatform}
                onChange={setAddPlatform}
                options={[
                  { value: 'youtube', label: 'YouTube' },
                  { value: 'twitch', label: 'Twitch' },
                  { value: 'kick', label: 'Kick' },
                ]}
              />
            </div>

            <div style={{ minWidth: '220px', flex: '1.2' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Channel Handle or Username
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. @MrBeast or shroud"
                value={addUsername}
                onChange={e => setAddUsername(e.target.value)}
                required
              />
            </div>

            <div style={{ minWidth: '220px', flex: '1.2' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Notification Channel
              </label>
              <Select
                value={addChannel}
                onChange={setAddChannel}
                options={channelOptions}
                placeholder="Select Discord channel..."
                searchable
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              icon={Plus}
              loading={submitting}
              disabled={!addUsername.trim() || !addChannel}
            >
              Add Alert
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Active Alerts Grid */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Active Stream Monitors
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Creators currently tracked by background polling routines.
            </p>
          </div>
          <Badge variant="primary" size="sm">{alerts.length} Tracked</Badge>
        </div>

        {alerts.length === 0 ? (
          <EmptyState
            icon={Tv}
            title="No Stream Alerts Configured"
            description="Add a creator handle above to notify your community the second they begin broadcasting."
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
            {alerts.map(alert => {
              const ch = channels.find(c => String(c.id) === String(alert.notification_channel_id));
              return (
                <Card key={`${alert.platform}-${alert.creator_username}`} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <CardContent style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                      {getPlatformBadge(alert.platform)}
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Edit2}
                          onClick={() => openEditAlert(alert)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Trash2}
                          onClick={() => handleDeleteAlert(alert.platform, alert.creator_username)}
                          style={{ color: '#f87171' }}
                        />
                      </div>
                    </div>

                    <h4 style={{ margin: '0 0 6px', fontSize: '16.5px', fontWeight: 700, color: 'var(--text-main)', wordBreak: 'break-all' }}>
                      {alert.creator_username}
                    </h4>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '12.5px' }}>
                      <Hash size={13} />
                      <span>{ch ? ch.name : alert.notification_channel_id}</span>
                    </div>

                    <div style={{ marginTop: '16px', borderTop: '1px solid var(--border)', paddingTop: '10px', display: 'flex', gap: '12px' }}>
                      <span style={{
                        fontSize: '12px',
                        color: alert.notify_live ? 'var(--text-main)' : 'var(--text-muted)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: alert.notify_live ? '#10b981' : 'var(--text-muted)' }} />
                        Live Streams
                      </span>
                      <span style={{
                        fontSize: '12px',
                        color: alert.notify_videos ? 'var(--text-main)' : 'var(--text-muted)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: alert.notify_videos ? '#10b981' : 'var(--text-muted)' }} />
                        VODs & Uploads
                      </span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Edit Alert Modal */}
      <Modal
        isOpen={Boolean(editingAlert && editForm)}
        onClose={() => { setEditingAlert(null); setEditForm(null); }}
        title={editingAlert ? `Configure Alert — ${editingAlert.creator_username}` : 'Edit Alert'}
        maxWidth="520px"
      >
        {editingAlert && editForm && (
          <form onSubmit={handleSaveEdit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Notification Channel
              </label>
              <Select
                value={editForm.notification_channel_id}
                onChange={val => setEditForm({ ...editForm, notification_channel_id: val })}
                options={channelOptions}
                searchable
              />
            </div>

            <div style={{
              padding: '14px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px'
            }}>
              <Toggle
                checked={editForm.notify_live}
                onChange={val => setEditForm({ ...editForm, notify_live: val })}
                label="Notify on Live Streams"
                description="Trigger alert when creator starts a live broadcast."
              />
              <Toggle
                checked={editForm.notify_videos}
                onChange={val => setEditForm({ ...editForm, notify_videos: val })}
                label="Notify on New Uploads"
                description="Trigger alert when creator posts a new video or VOD."
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Custom Live Stream Announcement Message
              </label>
              <textarea
                className="form-input"
                rows={2}
                value={editForm.custom_live_message}
                onChange={e => setEditForm({ ...editForm, custom_live_message: e.target.value })}
                placeholder="{creator} is now LIVE on {platform}! Watch at {url}"
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Custom New Video Announcement Message
              </label>
              <textarea
                className="form-input"
                rows={2}
                value={editForm.custom_video_message}
                onChange={e => setEditForm({ ...editForm, custom_video_message: e.target.value })}
                placeholder="{creator} uploaded a new video! Check it out: {url}"
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
              <Button
                type="button"
                variant="outline"
                onClick={() => { setEditingAlert(null); setEditForm(null); }}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                loading={editSaving}
              >
                Save Changes
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}

export default StreamAlerts;
