import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync, syncParams } from '../../sync';

const QUICK_EMOJIS = ['👍', '❤️', '🔥', '🎉', '⭐', '📢', '✅', '🚀'];

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
        emoji: emoji.trim()
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
      setReactions(prev => prev.filter(r => r.id !== id));
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
    const ch = channels.find(c => c.id === id);
    return ch ? `#${ch.name}` : `Channel ${id}`;
  };

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="page-header flex justify-between items-center" style={{ flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 className="page-title">
            <span>⚡</span> Auto Reactions
          </h2>
          <p className="page-subtitle">
            Automatically react with emojis to every message sent in configured channels.
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
            gap: '6px'
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
          background: 'rgba(239, 68, 68, 0.15)',
          border: '1px solid var(--danger)',
          color: 'var(--danger)',
          fontSize: '14px'
        }}>
          {error}
        </div>
      )}

      {/* Add Reaction Form */}
      <div className="card glass-panel" style={{ marginBottom: '28px' }}>
        <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
          Add Channel Auto-Reaction
        </h3>
        <form onSubmit={handleAdd}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px', marginBottom: '16px' }}>
            <div className="form-group">
              <label className="form-label">Channel</label>
              <select
                className="form-control"
                value={selectedChannel}
                onChange={e => setSelectedChannel(e.target.value)}
                required
              >
                {channels.map(ch => (
                  <option key={ch.id} value={ch.id}>#{ch.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Emoji</label>
              <input
                type="text"
                className="form-control"
                placeholder="Paste emoji or type :name:"
                value={emoji}
                onChange={e => setEmoji(e.target.value)}
                required
              />
            </div>
          </div>

          {/* Quick Emoji Bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Quick Select:</span>
            {QUICK_EMOJIS.map(em => (
              <button
                key={em}
                type="button"
                onClick={() => setEmoji(em)}
                style={{
                  background: 'rgba(255,255,255,0.06)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  padding: '4px 10px',
                  fontSize: '16px',
                  cursor: 'pointer'
                }}
              >
                {em}
              </button>
            ))}
          </div>

          <button
            type="submit"
            disabled={submitting || !emoji.trim()}
            className="btn btn-primary"
          >
            {submitting ? 'Adding...' : '⚡ Add Auto Reaction'}
          </button>
        </form>
      </div>

      {/* Active Reactions */}
      <div>
        <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
          Configured Reactions ({reactions.length})
        </h3>

        {reactions.length === 0 ? (
          <div className="card glass-panel" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
            No auto-reactions configured yet.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
            {reactions.map(r => (
              <div
                key={r.id}
                className="card glass-panel"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '14px 18px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span style={{ fontSize: '24px' }}>{r.emoji}</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-main)' }}>
                      {getChannelName(r.channel_id)}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      Auto-reacts on every message
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedChannel(r.channel_id);
                      setEmoji(r.emoji);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--primary)',
                      cursor: 'pointer',
                      fontSize: '15px',
                      padding: '4px 8px'
                    }}
                    title="Edit reaction (loads it into the form above)"
                  >
                    ✏️
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(r.id)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--danger)',
                      cursor: 'pointer',
                      fontSize: '16px',
                      padding: '4px 8px'
                    }}
                    title="Remove reaction"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sync Modal */}
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
