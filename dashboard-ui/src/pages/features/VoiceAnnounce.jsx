import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

export default function VoiceAnnounce() {
  const { guildId } = useParams();

  const [voiceChannels, setVoiceChannels] = useState([]);
  const [categories, setCategories] = useState([]);
  const [voices, setVoices] = useState([]);
  const [loading, setLoading] = useState(true);

  // Form
  const [targetType, setTargetType] = useState('channel'); // 'channel' | 'category'
  const [targetId, setTargetId] = useState('');
  const [message, setMessage] = useState('');
  const [language, setLanguage] = useState('en');
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fetchVoiceData = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/voice-announce`);
      setVoiceChannels(res.data.voice_channels || []);
      setCategories(res.data.categories || []);
      setVoices(res.data.voices || []);
      setError('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load voice channel data');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchVoiceData();
  }, [fetchVoiceData]);

  const handleSpeak = async (e) => {
    e.preventDefault();
    if (!targetId || !message.trim()) {
      setError('Please select a target channel/category and enter a message.');
      return;
    }

    setSpeaking(true);
    setError('');
    setSuccess('');

    try {
      const res = await api.post(`/guilds/${guildId}/voice-announce`, {
        target_type: targetType,
        target_id: targetId,
        message: message.trim(),
        language,
      });

      if (targetType === 'category') {
        setSuccess(`✅ Successfully announced in ${res.data.announced_channels} voice channels!`);
      } else {
        setSuccess(`✅ Successfully broadcasted announcement in #${res.data.announced_channel}!`);
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to broadcast voice announcement');
    } finally {
      setSpeaking(false);
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '320px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="page-header" style={{ marginBottom: '24px' }}>
        <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span>📣</span> Neural Voice Announcer
        </h1>
        <p className="page-subtitle">
          Broadcast spoken text-to-speech announcements directly into active voice channels or whole voice categories using Microsoft Edge natural neural voices.
        </p>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: '16px' }}>{error}</div>}
      {success && <div className="alert alert-success" style={{ marginBottom: '16px' }}>{success}</div>}

      <div className="grid-2 stagger" style={{ gap: '24px', alignItems: 'start' }}>
        {/* Announcer Form */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '16px' }}>
            🎙️ Broadcast Announcement
          </h3>

          <form onSubmit={handleSpeak}>
            {/* Target Mode Toggle */}
            <div style={{ marginBottom: '18px' }}>
              <label className="form-label">Broadcast Target</label>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => {
                    setTargetType('channel');
                    setTargetId('');
                  }}
                  className="btn"
                  style={{
                    flex: 1,
                    background: targetType === 'channel' ? 'rgba(99, 102, 241, 0.2)' : 'var(--bg-surface)',
                    border: targetType === 'channel' ? '2px solid var(--primary)' : '1px solid var(--border)',
                    color: targetType === 'channel' ? '#fff' : 'var(--text-muted)',
                    fontWeight: targetType === 'channel' ? '600' : 'normal',
                  }}
                >
                  🔊 Single Voice Channel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTargetType('category');
                    setTargetId('');
                  }}
                  className="btn"
                  style={{
                    flex: 1,
                    background: targetType === 'category' ? 'rgba(99, 102, 241, 0.2)' : 'var(--bg-surface)',
                    border: targetType === 'category' ? '2px solid var(--primary)' : '1px solid var(--border)',
                    color: targetType === 'category' ? '#fff' : 'var(--text-muted)',
                    fontWeight: targetType === 'category' ? '600' : 'normal',
                  }}
                >
                  📁 Entire Category ({categories.length})
                </button>
              </div>
            </div>

            {/* Target Select */}
            {targetType === 'channel' ? (
              <div className="form-group">
                <label className="form-label">Select Voice Channel</label>
                <Select
                  value={targetId}
                  onChange={setTargetId}
                  options={voiceChannels.map(vc => ({
                    value: vc.id,
                    label: `🔊 ${vc.name} (${vc.category})`,
                  }))}
                  placeholder="Select a voice channel..."
                  searchable
                />
              </div>
            ) : (
              <div className="form-group">
                <label className="form-label">Select Category</label>
                <Select
                  value={targetId}
                  onChange={setTargetId}
                  options={categories.map(cat => ({
                    value: cat.id,
                    label: `📁 ${cat.name} (${cat.voice_channels_count} voice channels)`,
                  }))}
                  placeholder="Select a category..."
                  searchable
                />
              </div>
            )}

            {/* Language & Voice Select */}
            <div className="form-group">
              <label className="form-label">Neural Language & Accent</label>
              <Select
                value={language}
                onChange={setLanguage}
                options={voices.map(v => ({
                  value: v.code,
                  label: `🌐 ${v.name}`,
                }))}
                placeholder="Choose voice language..."
                searchable
              />
            </div>

            {/* Announcement Message */}
            <div className="form-group">
              <label className="form-label">Announcement Text</label>
              <textarea
                className="input-field"
                rows={4}
                value={message}
                onChange={e => setMessage(e.target.value)}
                placeholder="Type what the bot should speak in the voice channel..."
                required
                maxLength={400}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {message.length} / 400 characters
              </div>
            </div>

            <button
              type="submit"
              disabled={speaking || !targetId || !message.trim()}
              className="btn btn-primary"
              style={{ width: '100%', display: 'flex', justifyContent: 'center', gap: '8px' }}
            >
              <span>{speaking ? '⏳' : '📢'}</span>
              {speaking ? 'Broadcasting in Voice Channel...' : 'Speak Now in Voice Channel'}
            </button>
          </form>
        </div>

        {/* Info & Tips Panel */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '12px' }}>
            💡 Voice Announcer Highlights
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: '8px', border: '1px solid var(--border)' }}>
              <div style={{ fontWeight: '600', color: '#fff', fontSize: '14px', marginBottom: '4px' }}>
                ✨ Natural Edge-TTS Audio
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                Uses Microsoft Edge neural text-to-speech with crystal-clear human pronunciation, emotional cadence, and native intonation.
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: '8px', border: '1px solid var(--border)' }}>
              <div style={{ fontWeight: '600', color: '#fff', fontSize: '14px', marginBottom: '4px' }}>
                🌐 Regional & International Dialects
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                Full native support for Malayalam, Tamil, Hindi, English (US/UK), Spanish, French, German, Japanese, Korean, Arabic, and more.
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: '8px', border: '1px solid var(--border)' }}>
              <div style={{ fontWeight: '600', color: '#fff', fontSize: '14px', marginBottom: '4px' }}>
                📁 Category Cascading
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                Selecting a category broadcasts your announcement across every single voice channel nested under that category in sequence.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
