import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Pin,
  Plus,
  Trash2,
  Hash,
  Share2,
  AlertCircle,
  CheckCircle2,
  MessageSquare
} from 'lucide-react';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync, syncParams } from '../../sync';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function StickyMessages() {
  const { guildId } = useParams();
  const [channels, setChannels] = useState([]);
  const [stickies, setStickies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [syncOpen, setSyncOpen] = useState(false);

  const [selectedChannel, setSelectedChannel] = useState('');
  const [content, setContent] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const [stickiesRes, chanRes] = await Promise.all([
        api.get(`/guilds/${guildId}/sticky`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      setStickies(stickiesRes.data.stickies || []);
      const chList = chanRes.data.channels || [];
      setChannels(chList);
      if (chList.length > 0 && !selectedChannel) {
        setSelectedChannel(chList[0].id);
      }
      setError('');
    } catch (err) {
      console.error('Failed to load sticky messages', err);
      setError(err.response?.data?.error || 'Failed to load sticky messages');
    } finally {
      setLoading(false);
    }
  }, [guildId, selectedChannel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddSticky = async (e) => {
    e.preventDefault();
    if (!selectedChannel || !content.trim()) return;
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/sticky`, withSync({
        channel_id: selectedChannel,
        content: content.trim()
      }));
      setContent('');
      setSuccess('Sticky message pinned to channel successfully!');
      setTimeout(() => setSuccess(''), 3000);
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save sticky message');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (channelId) => {
    if (!window.confirm('Remove sticky message from this channel?')) return;
    try {
      await api.delete(`/guilds/${guildId}/sticky/${channelId}`, { params: syncParams() });
      setStickies(prev => prev.filter(s => s.channel_id !== channelId));
      setSuccess('Sticky message deleted.');
      setTimeout(() => setSuccess(''), 2500);
    } catch (err) {
      console.error('Failed to delete sticky', err);
      setError(err.response?.data?.error || 'Failed to delete sticky');
    }
  };

  const channelOptions = channels.map(c => ({
    value: c.id,
    label: `#${c.name}`
  }));

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="240px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  const getChannelName = (id) => {
    const ch = channels.find(c => String(c.id) === String(id));
    return ch ? `#${ch.name}` : `Channel ${id}`;
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Pin}
        title="Sticky Channel Messages"
        subtitle="Pins dynamic reminders and notices to the bottom of channels. When members chat, the bot automatically repositions the message."
        actions={
          <Button
            variant="outline"
            size="sm"
            icon={Share2}
            onClick={() => setSyncOpen(true)}
          >
            Sync to Servers
          </Button>
        }
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

      {/* Create / Pin Sticky Message Card */}
      <Card>
        <CardHeader>
          <CardTitle>Pin New Sticky Notice</CardTitle>
          <CardDescription>
            Select a target channel and specify the message content to keep anchored at the bottom of the chat stream.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAddSticky} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Discord Channel
              </label>
              <Select
                value={selectedChannel}
                onChange={setSelectedChannel}
                options={channelOptions}
                placeholder="Select channel..."
                searchable
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Sticky Message Body (Markdown supported)
              </label>
              <textarea
                className="form-input"
                rows={3}
                value={content}
                onChange={e => setContent(e.target.value)}
                placeholder="e.g. ⚠️ Remember: Keep discussion on-topic in this channel. See #rules for guidelines!"
                required
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button
                type="submit"
                variant="primary"
                icon={Pin}
                loading={submitting}
                disabled={!selectedChannel || !content.trim()}
              >
                Pin Sticky Message
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Active Sticky Notices */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Active Sticky Messages
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Channels where auto-repositioning sticky messages are currently enabled.
            </p>
          </div>
          <Badge variant="primary" size="sm">{stickies.length} Active</Badge>
        </div>

        {stickies.length === 0 ? (
          <EmptyState
            icon={Pin}
            title="No Sticky Messages Pinned"
            description="Use the form above to pin an enduring notice or guideline message to any channel."
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {stickies.map(s => (
              <Card key={s.channel_id} style={{ padding: '18px 20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px' }}>
                  <div style={{ flex: 1, minWidth: '280px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                      <Badge variant="primary" size="sm">
                        {getChannelName(s.channel_id)}
                      </Badge>
                    </div>
                    <div style={{ fontSize: '13.5px', color: 'var(--text-main)', lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>
                      {s.content}
                    </div>
                  </div>

                  <Button
                    variant="danger"
                    size="sm"
                    icon={Trash2}
                    onClick={() => handleDelete(s.channel_id)}
                  >
                    Unpin
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <SyncModal
        isOpen={syncOpen}
        onClose={() => setSyncOpen(false)}
        currentGuildId={guildId}
        moduleName="sticky"
        moduleLabel="Sticky Messages"
      />
    </div>
  );
}

export default StickyMessages;
