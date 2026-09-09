import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync, syncParams } from '../../sync';

function StickyMessages() {
  const { guildId } = useParams();
  const [channels, setChannels] = useState([]);
  const [stickies, setStickies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
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
    } catch (err) {
      console.error('Failed to load sticky messages', err);
    }
    setLoading(false);
  }, [guildId, selectedChannel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddSticky = async (e) => {
    e.preventDefault();
    if (!selectedChannel || !content.trim()) return;
    setError('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/sticky`, withSync({
        channel_id: selectedChannel,
        content: content.trim()
      }));
      setContent('');
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save sticky message');
    }
    setSubmitting(false);
  };

  const handleDelete = async (channelId) => {
    try {
      await api.delete(`/guilds/${guildId}/sticky/${channelId}`, { params: syncParams() });
      setStickies(prev => prev.filter(s => s.channel_id !== channelId));
    } catch (err) {
      console.error('Failed to delete sticky', err);
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
            <span>📌</span> Sticky Messages
          </h2>
          <p className="page-subtitle">
            Pins a dynamic message to the bottom of any channel. When new messages are sent, the bot repositions it.
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

      {/* Set Sticky Form */}
      <div className="card glass-panel" style={{ marginBottom: '28px' }}>
        <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
          Add or Update Sticky Message
        </h3>
        <form onSubmit={handleAddSticky}>
          <div className="form-group" style={{ maxWidth: '400px', marginBottom: '16px' }}>
            <label className="form-label">Target Channel</label>
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

          <div className="form-group" style={{ marginBottom: '16px' }}>
            <label className="form-label">Sticky Content</label>
            <textarea
              className="form-control"
              rows="4"
              placeholder="e.g. 📢 Remember to read server rules before chatting! Discord formatting and links supported."
              value={content}
              onChange={e => setContent(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            disabled={submitting || !content.trim()}
            className="btn btn-primary"
          >
            {submitting ? 'Setting Sticky...' : '📌 Set Sticky Message'}
          </button>
        </form>
      </div>

      {/* Active Stickies List */}
      <div>
        <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
          Active Sticky Messages ({stickies.length})
        </h3>

        {stickies.length === 0 ? (
          <div className="card glass-panel" style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
            No sticky messages configured for this server yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {stickies.map(s => (
              <div
                key={s.channel_id}
                className="card glass-panel"
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  gap: '16px',
                  padding: '16px 20px'
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{
                    display: 'inline-block',
                    background: 'rgba(88,101,242,0.15)',
                    border: '1px solid var(--primary)',
                    borderRadius: '6px',
                    padding: '3px 10px',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--accent)',
                    marginBottom: '8px'
                  }}>
                    {getChannelName(s.channel_id)}
                  </div>
                  <div style={{
                    fontSize: '14px',
                    color: 'var(--text-main)',
                    whiteSpace: 'pre-wrap',
                    background: 'rgba(0,0,0,0.2)',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: '1px solid var(--border)'
                  }}>
                    {s.content}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedChannel(s.channel_id);
                      setContent(s.content);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className="btn"
                    style={{
                      background: 'rgba(88,101,242,0.12)',
                      border: '1px solid var(--primary)',
                      color: 'var(--text-main)',
                      padding: '8px 14px',
                      fontSize: '13px'
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(s.channel_id)}
                    className="btn"
                    style={{
                      background: 'rgba(239,68,68,0.12)',
                      border: '1px solid var(--danger)',
                      color: 'var(--danger)',
                      padding: '8px 14px',
                      fontSize: '13px'
                    }}
                  >
                    Delete
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
        moduleName="sticky"
        moduleLabel="Sticky Messages"
      />
    </div>
  );
}

export default StickyMessages;
