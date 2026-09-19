import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Mic2,
  Plus,
  Trash2,
  Volume2,
  Folder,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function TempVC() {
  const { guildId } = useParams();
  const [hubs, setHubs] = useState([]);
  const [voiceChannels, setVoiceChannels] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
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
      setError('');
    } catch (err) {
      console.error('Failed to load temp VC data', err);
      setError(err.response?.data?.error || 'Failed to load temp VC configuration');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleAddHub = async (e) => {
    e.preventDefault();
    if (!form.channel_id) return;
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/tempvc`, form);
      setSuccess('Hub channel configured! Members who join it will get their own private temp VC.');
      setTimeout(() => setSuccess(''), 4000);
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to set hub channel');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemoveHub = async (channelId) => {
    if (!window.confirm('Remove this Temp VC hub? Existing temp channels remain active until they are empty.')) return;
    try {
      await api.delete(`/guilds/${guildId}/tempvc/${channelId}`);
      setSuccess('Hub removed.');
      setTimeout(() => setSuccess(''), 2000);
      await fetchData();
    } catch (err) {
      console.error('Failed to remove hub', err);
      setError(err.response?.data?.error || 'Failed to remove hub');
    }
  };

  const getCatName = (id) => categories.find(c => String(c.id) === String(id))?.name || null;

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="260px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Mic2}
        title="Temporary Voice Channels"
        subtitle="Designate hub voice channels — members who join instantly receive a private temporary VC with full owner controls to lock, rename, limit, and ban."
      />

      {error && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderRadius: 'var(--radius-md)', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.25)', color: '#f87171', fontSize: '13.5px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><AlertCircle size={17} /><span>{error}</span></div>
          <button onClick={() => setError('')} style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '16px' }}>✕</button>
        </div>
      )}

      {success && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderRadius: 'var(--radius-md)', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.25)', color: '#34d399', fontSize: '13.5px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><CheckCircle2 size={17} /><span>{success}</span></div>
          <button onClick={() => setSuccess('')} style={{ background: 'transparent', border: 'none', color: '#34d399', cursor: 'pointer', fontSize: '16px' }}>✕</button>
        </div>
      )}

      {/* Hub Configuration Card */}
      <Card>
        <CardHeader>
          <CardTitle>Configure Hub Channel</CardTitle>
          <CardDescription>
            When a member joins the hub voice channel, the bot instantly creates a private temp VC for them. The hub itself is never occupied.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAddHub} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Hub Voice Channel (Join to Create)
                </label>
                <Select
                  value={form.channel_id}
                  onChange={v => setForm(f => ({ ...f, channel_id: v }))}
                  options={voiceChannels.map(ch => ({ value: ch.id, label: `🔊 ${ch.name}` }))}
                  placeholder="Select a voice channel..."
                  searchable
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Spawn Temp Channels Into (optional)
                </label>
                <Select
                  value={form.category_id}
                  onChange={v => setForm(f => ({ ...f, category_id: v }))}
                  options={[
                    { value: '', label: 'Same category as hub channel' },
                    ...categories.map(c => ({ value: c.id, label: `📁 ${c.name}` }))
                  ]}
                  placeholder="Select target category..."
                  searchable
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button
                type="submit"
                variant="primary"
                icon={Plus}
                loading={submitting}
                disabled={!form.channel_id}
              >
                Set Hub Channel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Active hubs */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>Active Hub Channels</h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>Voice channels currently configured to spawn temporary rooms.</p>
          </div>
          <Badge variant="primary" size="sm">{hubs.length} Hubs</Badge>
        </div>

        {hubs.length === 0 ? (
          <EmptyState
            icon={Mic2}
            title="No Hub Channels Configured"
            description="Select a voice channel above. Members who join it will instantly receive their own private temporary voice channel."
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {hubs.map(hub => (
              <Card key={hub.channel_id} style={{ padding: '16px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    <div style={{
                      width: '44px', height: '44px', borderRadius: '12px', flexShrink: 0,
                      background: 'rgba(88, 101, 242, 0.12)', border: '1px solid rgba(88, 101, 242, 0.25)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center'
                    }}>
                      <Volume2 size={20} color="var(--primary)" />
                    </div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '14.5px', color: 'var(--text-main)' }}>
                        {hub.channel_name}
                      </div>
                      <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginTop: '3px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Folder size={12} />
                        Spawns into: {hub.category_id ? (getCatName(hub.category_id) || 'category') : 'same category as hub'}
                      </div>
                    </div>
                  </div>

                  <Button variant="danger" size="sm" icon={Trash2} onClick={() => handleRemoveHub(hub.channel_id)}>
                    Remove Hub
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default TempVC;
