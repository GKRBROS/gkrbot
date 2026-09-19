import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Zap,
  Plus,
  Trash2,
  Edit2,
  Share2,
  Hash,
  CheckCircle2,
  AlertCircle,
  SmilePlus
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

const QUICK_EMOJIS = ['👍', '❤️', '🔥', '🎉', '⭐', '📢', '✅', '🚀'];

function parseEmoji(raw = '') {
  const str = raw.trim();
  const animated = str.match(/^<a:([^:]+):(\d+)>$/);
  if (animated) return { type: 'custom', animated: true, name: animated[1], id: animated[2] };
  const custom = str.match(/^<:([^:]+):(\d+)>$/);
  if (custom) return { type: 'custom', animated: false, name: custom[1], id: custom[2] };
  const shorthand = str.match(/^:([^:]+):$/);
  if (shorthand) return { type: 'shorthand', label: shorthand[1] };
  return { type: 'unicode', display: str, label: str };
}

function EmojiChip({ raw, size = 28 }) {
  const parsed = parseEmoji(raw);
  if (parsed.type === 'custom') {
    const ext = parsed.animated ? 'gif' : 'webp';
    const url = `https://cdn.discordapp.com/emojis/${parsed.id}.${ext}?size=64&quality=lossless`;
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '4px 10px', maxWidth: '160px' }}>
        <img src={url} alt={parsed.name} style={{ width: size, height: size, borderRadius: '4px', objectFit: 'contain' }} onError={e => { e.target.style.display = 'none'; }} />
        <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100px' }}>
          :{parsed.name}:
        </span>
      </div>
    );
  }
  if (parsed.type === 'shorthand') {
    return (
      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '4px 10px', fontSize: '13px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
        :{parsed.label}:
      </div>
    );
  }
  return <span style={{ fontSize: size, lineHeight: 1 }}>{parsed.display}</span>;
}

function AutoReactions() {
  const { guildId } = useParams();
  const [channels, setChannels] = useState([]);
  const [reactions, setReactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [syncOpen, setSyncOpen] = useState(false);

  const [selectedChannel, setSelectedChannel] = useState('');
  const [emoji, setEmoji] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const [reactRes, chanRes] = await Promise.all([
        api.get(`/guilds/${guildId}/auto-reactions`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      setReactions(reactRes.data.reactions || []);
      const chList = chanRes.data.channels || [];
      setChannels(chList);
      if (chList.length > 0 && !selectedChannel) {
        setSelectedChannel(chList[0].id);
      }
      setError('');
    } catch (err) {
      console.error('Failed to load auto reactions', err);
    } finally {
      setLoading(false);
    }
  }, [guildId, selectedChannel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!selectedChannel || !emoji.trim()) return;
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/auto-reactions`, withSync({
        channel_id: selectedChannel,
        emoji: emoji.trim(),
      }));
      setEmoji('');
      setSuccess('Auto-reaction rule added successfully!');
      setTimeout(() => setSuccess(''), 3000);
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add auto reaction');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/guilds/${guildId}/auto-reactions/${id}`, { params: syncParams() });
      setReactions(prev => prev.filter(r => r.id !== id));
      setSuccess('Reaction rule removed.');
      setTimeout(() => setSuccess(''), 2000);
    } catch (err) {
      console.error('Failed to remove reaction', err);
      setError(err.response?.data?.error || 'Failed to remove reaction');
    }
  };

  const channelOptions = channels.map(ch => ({ value: ch.id, label: `#${ch.name}` }));

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="260px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  const getChannelName = (id) => {
    const ch = channels.find(c => String(c.id) === String(id));
    return ch ? ch.name : id;
  };

  const emojiPreview = emoji.trim() ? parseEmoji(emoji.trim()) : null;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Zap}
        title="Auto Reactions"
        subtitle="Automatically apply emoji reactions to every message posted in designated channels."
        actions={
          <Button variant="outline" size="sm" icon={Share2} onClick={() => setSyncOpen(true)}>
            Sync to Servers
          </Button>
        }
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

      {/* Add Reaction Card */}
      <Card>
        <CardHeader>
          <CardTitle>Configure New Auto-Reaction</CardTitle>
          <CardDescription>
            Select a channel and an emoji. The bot will react with that emoji to every new message in the channel.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAdd} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Target Channel
                </label>
                <Select
                  value={selectedChannel}
                  onChange={setSelectedChannel}
                  options={channelOptions}
                  placeholder="Select a channel..."
                  searchable
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Reaction Emoji
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Paste emoji or <:name:id>"
                    value={emoji}
                    onChange={e => setEmoji(e.target.value)}
                    style={{ flex: 1 }}
                    required
                  />
                  {emojiPreview && <div style={{ flexShrink: 0 }}><EmojiChip raw={emoji.trim()} size={26} /></div>}
                </div>
              </div>
            </div>

            {/* Quick emoji picker */}
            <div>
              <span style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
                Quick Select
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {QUICK_EMOJIS.map(em => (
                  <button
                    key={em}
                    type="button"
                    onClick={() => setEmoji(em)}
                    style={{
                      background: emoji === em ? 'rgba(88, 101, 242, 0.15)' : 'var(--bg-surface)',
                      border: `1px solid ${emoji === em ? 'rgba(88, 101, 242, 0.4)' : 'var(--border)'}`,
                      borderRadius: '8px',
                      padding: '6px 14px',
                      fontSize: '20px',
                      cursor: 'pointer',
                      transition: 'all 150ms ease',
                      lineHeight: 1,
                    }}
                  >
                    {em}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button type="submit" variant="primary" icon={Plus} loading={submitting} disabled={!emoji.trim() || !selectedChannel}>
                Add Auto-Reaction
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Active Reactions */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>Active Auto-Reaction Rules</h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>Channels where the bot automatically reacts to every message.</p>
          </div>
          <Badge variant="primary" size="sm">{reactions.length} Rules</Badge>
        </div>

        {reactions.length === 0 ? (
          <EmptyState icon={SmilePlus} title="No Auto-Reactions Configured" description="Add a channel and emoji above to have the bot automatically react to every message." />
        ) : (
          <Card>
            <CardContent style={{ padding: 0 }}>
              {reactions.map((r, idx) => (
                <div
                  key={r.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '16px',
                    padding: '14px 20px',
                    borderBottom: idx < reactions.length - 1 ? '1px solid var(--border)' : 'none',
                  }}
                >
                  <div style={{ flexShrink: 0 }}>
                    <EmojiChip raw={r.emoji} size={26} />
                  </div>

                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Hash size={14} color="var(--text-muted)" />
                      {getChannelName(r.channel_id)}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>Reacts to every new message in this channel</div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <Button variant="ghost" size="sm" icon={Edit2} onClick={() => { setSelectedChannel(r.channel_id); setEmoji(r.emoji); window.scrollTo({ top: 0, behavior: 'smooth' }); }} />
                    <Button variant="ghost" size="sm" icon={Trash2} onClick={() => handleDelete(r.id)} style={{ color: '#f87171' }} />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      <SyncModal isOpen={syncOpen} onClose={() => setSyncOpen(false)} currentGuildId={guildId} moduleName="autoreact" moduleLabel="Auto Reactions" />
    </div>
  );
}

export default AutoReactions;
