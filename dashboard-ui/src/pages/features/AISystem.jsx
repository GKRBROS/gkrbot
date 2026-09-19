import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

const PERSONAS = [
  { id: 'friendly', name: 'Friendly', emoji: '☀️', color: '#f59e0b', desc: 'Warm, helpful, and natural conversation.' },
  { id: 'gamer', name: 'Gamer', emoji: '🎮', color: '#8b5cf6', desc: 'Clutch gaming teammate with hype & banter.' },
  { id: 'sarcastic', name: 'Sarcastic', emoji: '😼', color: '#ef4444', desc: 'Sharp wit, playful sass, and clever humor.' },
  { id: 'expert', name: 'Expert', emoji: '🔬', color: '#06b6d4', desc: 'Senior engineer clarity with zero fluff.' },
  { id: 'cyberpunk', name: 'Cyberpunk', emoji: '🌃', color: '#ec4899', desc: 'Futuristic AI construct from neon metropolis.' },
  { id: 'anime', name: 'Anime', emoji: '✨', color: '#10b981', desc: 'Kawaii, enthusiastic, and expressive companion.' },
];

export default function AISystem() {
  const { guildId } = useParams();

  const [config, setConfig] = useState(null);
  const [memories, setMemories] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Memory creation modal state
  const [newTopic, setNewTopic] = useState('');
  const [newFact, setNewFact] = useState('');
  const [addingMemory, setAddingMemory] = useState(false);

  const fetchAI = useCallback(async () => {
    try {
      const [aiRes, channelsRes] = await Promise.all([
        api.get(`/guilds/${guildId}/ai`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      setConfig(aiRes.data.config || {});
      setMemories(aiRes.data.memories || []);
      setChannels(channelsRes.data.channels || []);
      setError('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load AI system configuration');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchAI();
  }, [fetchAI]);

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    try {
      await api.post(`/guilds/${guildId}/ai`, config);
      setSaved(true);
      setSuccess('AI configuration saved successfully!');
      setTimeout(() => {
        setSaved(false);
        setSuccess('');
      }, 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save AI configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleAddMemory = async (e) => {
    e.preventDefault();
    if (!newTopic.trim() || !newFact.trim()) return;

    setAddingMemory(true);
    try {
      await api.post(`/guilds/${guildId}/ai/memories`, { topic: newTopic, fact: newFact });
      setNewTopic('');
      setNewFact('');
      fetchAI();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add memory');
    } finally {
      setAddingMemory(false);
    }
  };

  const handleDeleteMemory = async (id) => {
    try {
      await api.delete(`/guilds/${guildId}/ai/memories/${id}`);
      fetchAI();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to remove memory');
    }
  };

  if (loading || !config) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '350px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span>🤖</span> AI Companion & Lore Studio
        </h1>
        <p className="page-subtitle">
          Configure personality personas, self-learning knowledge retention, multi-lingual responses (including Manglish & regional dialects), and autonomous features.
        </p>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: '16px' }}>{error}</div>}
      {success && <div className="alert alert-success" style={{ marginBottom: '16px' }}>{success}</div>}

      {/* Global AI Master Toggle */}
      <div className="glass-panel" style={{ padding: '16px 20px', marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            width: '44px',
            height: '44px',
            borderRadius: '12px',
            background: config.enabled ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.12)',
            border: `1px solid ${config.enabled ? 'rgba(34, 197, 94, 0.4)' : 'rgba(239, 68, 68, 0.3)'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '22px',
          }}>
            {config.enabled ? '🧠' : '💤'}
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '16px', color: 'var(--text-main)' }}>
              AI Companion is {config.enabled ? 'Active & Listening' : 'Sleeping (Disabled)'}
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              {config.enabled
                ? 'The AI is responsive to mentions, messages in dedicated channels, and self-learning.'
                : 'Turn this on to enable intelligent conversation throughout the server.'}
            </div>
          </div>
        </div>
        <button
          type="button"
          className={`toggle ${config.enabled ? 'active' : ''}`}
          onClick={() => setConfig(c => ({ ...c, enabled: c.enabled ? 0 : 1 }))}
          aria-label="Toggle AI Active State"
        ></button>
      </div>

      <div className="grid-2 stagger" style={{ gap: '24px', alignItems: 'start' }}>
        {/* Left Column: Personality & Prompts */}
        <div className="flex flex-col gap-4">
          {/* Persona Picker */}
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '8px' }}>
              🎭 Personality Persona
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>
              Select the conversational style and tone the AI adapts when interacting with members.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '10px', marginBottom: '20px' }}>
              {PERSONAS.map(p => {
                const isSelected = config.persona === p.id;
                return (
                  <div
                    key={p.id}
                    onClick={() => setConfig({ ...config, persona: p.id })}
                    style={{
                      background: isSelected ? 'rgba(88, 101, 242, 0.15)' : 'var(--bg-surface)',
                      border: isSelected ? `2px solid ${p.color}` : '1px solid var(--border)',
                      borderRadius: '10px',
                      padding: '12px',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      boxShadow: isSelected ? `0 0 16px ${p.color}33` : 'none',
                    }}
                  >
                    <div style={{ fontSize: '24px', marginBottom: '4px' }}>{p.emoji}</div>
                    <div style={{ fontWeight: '600', fontSize: '14px', color: '#fff' }}>{p.name}</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px', lineHeight: '1.2' }}>{p.desc}</div>
                  </div>
                );
              })}
            </div>

            {/* Dedicated Channel */}
            <div className="form-group">
              <label className="form-label">Dedicated AI Chat Channel</label>
              <Select
                value={config.ai_channel_id}
                onChange={v => setConfig({ ...config, ai_channel_id: v })}
                options={[
                  { value: '', label: 'None (Only reply to direct @mentions)' },
                  ...channels.map(ch => ({ value: ch.id, label: '# ' + ch.name })),
                ]}
                placeholder="Select an AI channel..."
                searchable
              />
              <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
                Messages in this channel will trigger AI replies without needing an explicit @mention.
              </span>
            </div>

            {/* Custom System Prompt */}
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Custom Directive / System Prompt (Optional)</label>
              <textarea
                className="input-field"
                rows={3}
                value={config.system_prompt}
                onChange={e => setConfig({ ...config, system_prompt: e.target.value })}
                placeholder="Give your AI specific server rules, inside jokes, or behavior boundaries..."
                style={{ fontFamily: 'monospace' }}
              />
            </div>
          </div>

          {/* Autonomous Features Switches */}
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '14px' }}>
              ⚡ Autonomous Feature Modules
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[
                { key: 'mention_enabled', label: '💬 Reply to @Mentions', desc: 'Responds when tagged in any server channel' },
                { key: 'self_learning', label: '🧠 Self-Learning Retention', desc: 'Passively learns facts, lore, and member preferences from conversation' },
                { key: 'research_enabled', label: '🌐 Web & Encyclopedia Research', desc: 'Performs live multi-paragraph synthesis for queries and concepts' },
                { key: 'image_enabled', label: '🎨 FLUX Image Generation', desc: 'Generates banners and artwork on demand' },
                { key: 'comedy_enabled', label: '🎭 Banter & Comedy Mode', desc: 'Cracks jokes and engages in humorous member banter' },
                { key: 'tts_enabled', label: '🗣️ Voice TTS Narration', desc: 'Generates neural audio clips when requested' },
                { key: 'thread_mode', label: '🧵 Auto-Thread Replies', desc: 'Creates organized conversation threads for long questions' },
              ].map(feat => (
                <div
                  key={feat.key}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    background: 'rgba(255,255,255,0.02)',
                    padding: '10px 14px',
                    borderRadius: '8px',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: '500', fontSize: '14px' }}>{feat.label}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{feat.desc}</div>
                  </div>
                  <button
                    type="button"
                    className={`toggle ${config[feat.key] ? 'active' : ''}`}
                    onClick={() => setConfig(c => ({ ...c, [feat.key]: c[feat.key] ? 0 : 1 }))}
                  ></button>
                </div>
              ))}
            </div>

            <div className="flex justify-end mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
              <button
                type="button"
                onClick={handleSave}
                className={`btn ${saved ? 'btn-success' : 'btn-primary'}`}
                disabled={saving}
              >
                {saving ? 'Saving...' : saved ? '✅ Saved!' : 'Save AI Settings'}
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Learned Knowledge & Memories */}
        <div className="flex flex-col gap-4">
          <div className="glass-panel" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none' }}>
                🧠 Learned Lore & Knowledge Base ({memories.length})
              </h3>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>
              Facts the AI has passively remembered from chat or that staff have explicitly taught it.
            </p>

            {/* Add Memory Form */}
            <form onSubmit={handleAddMemory} style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border)', marginBottom: '20px' }}>
              <div style={{ fontWeight: '600', fontSize: '13px', color: '#fff', marginBottom: '8px' }}>
                ➕ Teach New Server Lore / Fact
              </div>
              <div className="form-group" style={{ marginBottom: '8px' }}>
                <input
                  type="text"
                  className="input-field"
                  placeholder="Topic / Keyword (e.g., server_founder, favorite_game)"
                  value={newTopic}
                  onChange={e => setNewTopic(e.target.value)}
                  required
                />
              </div>
              <div className="form-group" style={{ marginBottom: '10px' }}>
                <textarea
                  className="input-field"
                  rows={2}
                  placeholder="Fact / Lore detail (e.g., The server was founded in July 2024 by John)"
                  value={newFact}
                  onChange={e => setNewFact(e.target.value)}
                  required
                />
              </div>
              <button
                type="submit"
                disabled={addingMemory || !newTopic.trim() || !newFact.trim()}
                className="btn btn-secondary"
                style={{ fontSize: '12px', width: '100%' }}
              >
                {addingMemory ? 'Memorizing...' : '💡 Teach AI Fact'}
              </button>
            </form>

            {/* Memories List */}
            {memories.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
                No learned memories yet. The AI will build this automatically through conversation, or you can add custom lore above!
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '480px', overflowY: 'auto' }}>
                {memories.map(m => (
                  <div
                    key={m.id}
                    style={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      borderRadius: '8px',
                      padding: '12px 14px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'start',
                      gap: '10px',
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <span className="badge badge-primary" style={{ fontSize: '11px' }}>
                          #{m.topic}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          via {m.learned_from || 'chat'}
                        </span>
                      </div>
                      <div style={{ fontSize: '13px', color: '#e2e8f0', lineHeight: '1.4' }}>
                        {m.fact}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteMemory(m.id)}
                      className="btn"
                      style={{ padding: '4px 8px', fontSize: '11px', background: 'transparent', color: 'var(--danger)', border: 'none' }}
                      title="Forget this memory"
                    >
                      ❌
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
