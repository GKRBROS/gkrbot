import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync, syncParams } from '../../sync';
import { Select } from '../../components/Select';

const QUICK_EMOJIS = ['👍', '❤️', '🔥', '🎉', '⭐', '📢', '✅', '🚀'];

/**
 * Parse a Discord emoji string into a renderable object.
 *
 * Handles:
 *  - Standard Unicode emoji:  "👍"           → { type:'unicode', display:'👍', label:'👍' }
 *  - Custom animated emoji:   "<a:name:id>"  → { type:'custom', animated:true,  name:'name', id:'id' }
 *  - Custom static emoji:     "<:name:id>"   → { type:'custom', animated:false, name:'name', id:'id' }
 *  - Colon-name shorthand:    ":thumbsup:"   → { type:'shorthand', label:'thumbsup' }
 */
function parseEmoji(raw = '') {
  const str = raw.trim();

  // Animated custom emoji  <a:name:id>
  const animated = str.match(/^<a:([^:]+):(\d+)>$/);
  if (animated) return { type: 'custom', animated: true, name: animated[1], id: animated[2] };

  // Static custom emoji  <:name:id>
  const custom = str.match(/^<:([^:]+):(\d+)>$/);
  if (custom) return { type: 'custom', animated: false, name: custom[1], id: custom[2] };

  // Colon shorthand  :name:
  const shorthand = str.match(/^:([^:]+):$/);
  if (shorthand) return { type: 'shorthand', label: shorthand[1] };

  // Plain unicode
  return { type: 'unicode', display: str, label: str };
}

/** Render a compact emoji chip that always fits in a small space */
function EmojiChip({ raw, size = 32 }) {
  const parsed = parseEmoji(raw);

  if (parsed.type === 'custom') {
    const ext = parsed.animated ? 'gif' : 'webp';
    const url = `https://cdn.discordapp.com/emojis/${parsed.id}.${ext}?size=64&quality=lossless`;
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'rgba(255,255,255,0.07)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '8px',
          padding: '4px 10px',
          maxWidth: '160px',
          flexShrink: 0,
        }}
      >
        <img
          src={url}
          alt={parsed.name}
          style={{ width: size, height: size, borderRadius: '4px', objectFit: 'contain', flexShrink: 0 }}
          onError={(e) => { e.target.style.display = 'none'; }}
        />
        <span
          style={{
            fontSize: '12px',
            color: 'var(--text-sub)',
            fontFamily: 'monospace',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            maxWidth: '100px',
          }}
        >
          :{parsed.name}:
        </span>
      </div>
    );
  }

  if (parsed.type === 'shorthand') {
    return (
      <div
        style={{
          background: 'rgba(255,255,255,0.07)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '8px',
          padding: '4px 10px',
          fontSize: '13px',
          fontFamily: 'monospace',
          color: 'var(--text-sub)',
          maxWidth: '160px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        :{parsed.label}:
      </div>
    );
  }

  // Unicode emoji — just render the character at a readable size
  return (
    <span style={{ fontSize: size, lineHeight: 1, flexShrink: 0 }}>
      {parsed.display}
    </span>
  );
}

function AutoReactions() {
  const { guildId } = useParams();
  const [channels, setChannels] = useState([]);
  const [reactions, setReactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
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
    } catch (err) {
      console.error('Failed to load auto reactions', err);
    }
    setLoading(false);
  }, [guildId, selectedChannel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!selectedChannel || !emoji.trim()) return;
    setError('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/auto-reactions`, withSync({
        channel_id: selectedChannel,
        emoji: emoji.trim(),
      }));
      setEmoji('');
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add auto reaction');
    }
    setSubmitting(false);
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/guilds/${guildId}/auto-reactions/${id}`, { params: syncParams() });
      setReactions((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      console.error('Failed to remove reaction', err);
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '240px' }}></div>
      </div>
    );
  }

  const getChannelName = (id) => {
    const ch = channels.find((c) => c.id === id);
    return ch ? ch.name : id;
  };

  const emojiPreview = emoji.trim() ? parseEmoji(emoji.trim()) : null;

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="page-header flex justify-between items-center" style={{ flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 className="page-title">⚡ Auto Reactions</h1>
          <p className="page-subtitle">
            Automatically react with emojis to every message in configured channels.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSyncOpen(true)}
          className="btn"
          style={{
            background: 'rgba(88,101,242,0.15)',
            border: '1px solid var(--primary)',
            color: 'var(--text-main)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span>🔄</span> Sync to Other Servers
        </button>
      </div>

      {error && (
        <div style={{
          padding: '12px 16px',
          borderRadius: '8px',
          marginBottom: '20px',
          background: 'rgba(239,68,68,0.15)',
          border: '1px solid var(--danger)',
          color: 'var(--danger)',
          fontSize: '14px',
        }}>
          {error}
        </div>
      )}

      {/* Add Reaction Form */}
      <div className="glass-panel" style={{ padding: '24px', marginBottom: '28px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '20px', color: 'var(--text-main)' }}>
          Add Channel Auto-Reaction
        </h3>
        <form onSubmit={handleAdd}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '16px' }}>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">Channel</label>
              <Select
                value={selectedChannel}
                onChange={setSelectedChannel}
                options={channels.map((ch) => ({ value: ch.id, label: '# ' + ch.name }))}
                placeholder="Select a channel..."
                searchable
              />
            </div>

            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">Emoji</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <input
                  type="text"
                  className="form-control"
                  placeholder="Paste emoji or type :name:"
                  value={emoji}
                  onChange={(e) => setEmoji(e.target.value)}
                  required
                  style={{ flex: 1 }}
                />
                {emojiPreview && (
                  <div style={{ flexShrink: 0 }}>
                    <EmojiChip raw={emoji.trim()} size={28} />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Quick Emoji Bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600 }}>Quick Select:</span>
            {QUICK_EMOJIS.map((em) => (
              <button
                key={em}
                type="button"
                onClick={() => setEmoji(em)}
                style={{
                  background: emoji === em ? 'rgba(99,102,241,0.2)' : 'rgba(255,255,255,0.06)',
                  border: `1px solid ${emoji === em ? 'rgba(99,102,241,0.5)' : 'var(--border)'}`,
                  borderRadius: '8px',
                  padding: '6px 12px',
                  fontSize: '18px',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  lineHeight: 1,
                }}
              >
                {em}
              </button>
            ))}
          </div>

          <button type="submit" disabled={submitting || !emoji.trim()} className="btn btn-primary">
            {submitting ? 'Adding...' : '⚡ Add Auto Reaction'}
          </button>
        </form>
      </div>

      {/* Active Reactions List */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-main)', margin: 0 }}>
            Configured Reactions
          </h3>
          {reactions.length > 0 && (
            <span
              style={{
                fontSize: '12px',
                fontWeight: 700,
                background: 'rgba(99,102,241,0.15)',
                color: '#a5b4fc',
                padding: '3px 12px',
                borderRadius: '999px',
              }}
            >
              {reactions.length} total
            </span>
          )}
        </div>

        {reactions.length === 0 ? (
          <div className="glass-panel" style={{ textAlign: 'center', padding: '48px 36px' }}>
            <div style={{ fontSize: '40px', marginBottom: '12px' }}>⚡</div>
            <div style={{ fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>No auto-reactions yet</div>
            <div style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
              Add one above to get started.
            </div>
          </div>
        ) : (
          <div className="glass-panel" style={{ padding: '0', overflow: 'hidden' }}>
            {reactions.map((r, idx) => (
              <div
                key={r.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '16px',
                  padding: '14px 20px',
                  borderBottom: idx < reactions.length - 1 ? '1px solid var(--border)' : 'none',
                  transition: 'background 0.15s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.03)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                {/* Emoji display */}
                <div style={{ flexShrink: 0 }}>
                  <EmojiChip raw={r.emoji} size={28} />
                </div>

                {/* Channel info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontWeight: 600,
                      fontSize: '14px',
                      color: 'var(--text-main)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      overflow: 'hidden',
                    }}
                  >
                    <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>#</span>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {getChannelName(r.channel_id)}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    Auto-reacts on every message
                  </div>
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedChannel(r.channel_id);
                      setEmoji(r.emoji);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    style={{
                      background: 'transparent',
                      border: '1px solid transparent',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '14px',
                      padding: '6px 8px',
                      borderRadius: '6px',
                      transition: 'all 0.15s ease',
                      lineHeight: 1,
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'rgba(99,102,241,0.15)';
                      e.currentTarget.style.color = '#a5b4fc';
                      e.currentTarget.style.borderColor = 'rgba(99,102,241,0.3)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent';
                      e.currentTarget.style.color = 'var(--text-muted)';
                      e.currentTarget.style.borderColor = 'transparent';
                    }}
                    title="Edit — loads into form above"
                  >
                    ✏️
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(r.id)}
                    style={{
                      background: 'transparent',
                      border: '1px solid transparent',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '14px',
                      padding: '6px 8px',
                      borderRadius: '6px',
                      transition: 'all 0.15s ease',
                      lineHeight: 1,
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'rgba(239,68,68,0.15)';
                      e.currentTarget.style.color = 'var(--danger)';
                      e.currentTarget.style.borderColor = 'rgba(239,68,68,0.3)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent';
                      e.currentTarget.style.color = 'var(--text-muted)';
                      e.currentTarget.style.borderColor = 'transparent';
                    }}
                    title="Remove reaction"
                  >
                    🗑️
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <SyncModal
        isOpen={syncOpen}
        onClose={() => setSyncOpen(false)}
        currentGuildId={guildId}
        moduleName="autoreact"
        moduleLabel="Auto Reactions"
      />
    </div>
  );
}

export default AutoReactions;
