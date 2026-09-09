import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

function TempVC() {
  const { guildId } = useParams();
  const [hubs, setHubs] = useState([]);
  const [voiceChannels, setVoiceChannels] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState({ channel_id: '', category_id: '' });

  const fetchData = useCallback(async () => {
    try {
      const [hubsRes, vcRes] = await Promise.all([
        api.get(`/guilds/${guildId}/tempvc`),
        api.get(`/guilds/${guildId}/voice-channels`),
      ]);
      setHubs(hubsRes.data.hubs || []);
      setVoiceChannels(vcRes.data.channels || []);
      setCategories(vcRes.data.categories || []);
      if (vcRes.data.channels?.length > 0) {
        setForm(f => ({ ...f, channel_id: f.channel_id || vcRes.data.channels[0].id }));
      }
    } catch (err) {
      console.error('Failed to load temp VC data', err);
    }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleAddHub = async (e) => {
    e.preventDefault();
    if (!form.channel_id) return;
    setError('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/tempvc`, form);
      setForm(f => ({ ...f, category_id: '' }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to set hub channel');
    }
    setSubmitting(false);
  };

  const handleRemoveHub = async (channelId) => {
    if (!window.confirm('Remove this Temp VC hub? Existing temp channels stay active until they are empty.')) return;
    try {
      await api.delete(`/guilds/${guildId}/tempvc/${channelId}`);
      await fetchData();
    } catch (err) {
      console.error('Failed to remove hub', err);
    }
  };

  const getCatName = (id) => categories.find(c => c.id === id)?.name || null;

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '300px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h2 className="page-title"><span>🎙️</span> Temp Voice Channels</h2>
        <p className="page-subtitle">
          Set hub voice channels — when a member joins a hub, the bot creates them a private temp VC with full owner controls (lock, rename, limit, ban &amp; more).
        </p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {/* Set hub */}
      <div className="glass-panel" style={{ padding: '24px', marginBottom: '32px', border: '1px solid var(--primary)' }}>
        <h3 className="section-title" style={{ marginBottom: '6px', border: 'none', padding: 0 }}>📡 Set Hub Channel</h3>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '18px' }}>
          Joining this voice channel spawns a new temporary voice channel. Existing hubs can be re-pointed by selecting them again.
        </p>
        <form onSubmit={handleAddHub}>
          <div className="grid-2" style={{ alignItems: 'end' }}>
            <div className="form-group">
              <label className="form-label">Hub Voice Channel (Join to create)</label>
              <Select
                value={form.channel_id}
                onChange={v => setForm(f => ({ ...f, channel_id: v }))}
                options={voiceChannels.map(ch => ({ value: ch.id, label: '🔊 ' + ch.name }))}
                placeholder="Select a voice channel..."
                searchable
              />
            </div>
            <div className="form-group">
              <label className="form-label">Spawn Temp Channels Into (optional)</label>
              <Select
                value={form.category_id}
                onChange={v => setForm(f => ({ ...f, category_id: v }))}
                options={[{ value: '', label: 'Same category as hub' }, ...categories.map(c => ({ value: c.id, label: '📁 ' + c.name }))]}
                placeholder="Select a category..."
                searchable
              />
            </div>
          </div>
          <div className="flex justify-end">
            <button type="submit" className={`btn ${saved ? 'btn-success' : 'btn-primary'}`} disabled={submitting || !form.channel_id}>
              {saved ? '✅ Hub Set!' : (submitting ? 'Setting...' : '📡 Set Hub Channel')}
            </button>
          </div>
        </form>
      </div>

      {/* Active hubs */}
      <div className="section-header">
        <h3 className="section-title">Active Hubs <span className="section-count">{hubs.length}</span></h3>
      </div>

      {hubs.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">🎙️</div>
          <h3 className="empty-state-title">No hub channels set</h3>
          <p className="empty-state-desc">Pick a voice channel above — members who join it will get their own private temp voice channel.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {hubs.map(hub => (
            <div key={hub.channel_id} className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', minWidth: 0 }}>
                <div style={{
                  width: '44px', height: '44px', borderRadius: '12px', flexShrink: 0,
                  background: 'var(--primary-dim)', border: '1px solid rgba(99,102,241,0.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '19px'
                }}>
                  🔊
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: '14.5px', color: 'var(--text-main)' }}>
                    {hub.channel_name}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '3px' }}>
                    Temp channels spawn {hub.category_id ? `into 📁 ${getCatName(hub.category_id) || 'category'}` : 'next to the hub'}
                  </div>
                </div>
              </div>
              <button
                onClick={() => handleRemoveHub(hub.channel_id)}
                className="btn btn-danger"
                style={{ padding: '8px 16px', fontSize: '13px' }}
              >
                Remove Hub
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default TempVC;
