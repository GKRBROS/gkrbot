import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Bot,
  Sparkles,
  Brain,
  MessageSquare,
  Globe,
  Palette,
  Smile,
  Volume2,
  GitFork,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Save,
  BookOpen,
  Send
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import Badge from '../../components/Badge';
import Skeleton from '../../components/Skeleton';

const PERSONAS = [
  { id: 'friendly', name: 'Friendly Companion', emoji: '☀️', color: '#f59e0b', desc: 'Warm, helpful, encouraging, and natural conversation.' },
  { id: 'gamer', name: 'Gaming Teammate', emoji: '🎮', color: '#8b5cf6', desc: 'Clutch gaming ally loaded with gaming slang and friendly banter.' },
  { id: 'sarcastic', name: 'Sarcastic & Witty', emoji: '😼', color: '#ef4444', desc: 'Sharp wit, playful snark, dry roasts, and clever humor.' },
  { id: 'expert', name: 'Engineering Expert', emoji: '🔬', color: '#06b6d4', desc: 'Precise technical explanations with zero filler or fluff.' },
  { id: 'cyberpunk', name: 'Cyberpunk AI', emoji: '🌃', color: '#ec4899', desc: 'Sentient neural construct from a neon dystopian metropolis.' },
  { id: 'anime', name: 'Enthusiastic Anime', emoji: '✨', color: '#10b981', desc: 'Expressive, joyful, supportive, and energetic companion.' },
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

  // Memory creation state
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
      setSuccess('AI configuration and personality directives saved successfully!');
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
      await api.post(`/guilds/${guildId}/ai/memories`, { topic: newTopic.trim(), fact: newFact.trim() });
      setNewTopic('');
      setNewFact('');
      fetchAI();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to record memory');
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
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="100px" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px' }}>
          <Skeleton height="360px" />
          <Skeleton height="360px" />
        </div>
      </div>
    );
  }

  const channelSelectOptions = [
    { value: '', label: 'None (Only reply to direct @mentions)' },
    ...channels.map(ch => ({ value: ch.id, label: `#${ch.name}` }))
  ];

  const autonomousModules = [
    { key: 'mention_enabled', label: 'Reply to Direct @Mentions', desc: 'Responds whenever a member tags the bot in any conversation.' },
    { key: 'self_learning', label: 'Self-Learning Lore Retention', desc: 'Passively learns community facts and member nicknames from chat.' },
    { key: 'research_enabled', label: 'Live Web & Fact Research', desc: 'Performs online synthesis to give accurate real-world answers.' },
    { key: 'image_enabled', label: 'FLUX Image Generation', desc: 'Synthesizes images and artwork directly inside Discord chat.' },
    { key: 'comedy_enabled', label: 'Banter & Humorous Roasts', desc: 'Engages in witty retorts and funny banter with familiar members.' },
    { key: 'tts_enabled', label: 'Neural Audio Voice Narration', desc: 'Speaks responses via voice notes when requested by members.' },
    { key: 'thread_mode', label: 'Automated Discussion Threads', desc: 'Spins off detailed questions into dedicated Discord threads.' },
  ];

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Bot}
        title="AI Companion & Studio"
        subtitle="Configure conversational personas, self-learning knowledge retention, regional accents, and autonomous modules."
        actions={
          <Button
            variant="primary"
            size="sm"
            icon={Save}
            loading={saving}
            onClick={handleSave}
          >
            {saved ? 'Saved!' : 'Save Directives'}
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

      {/* Master Toggle Banner */}
      <Card>
        <CardContent style={{ padding: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '46px',
              height: '46px',
              borderRadius: '12px',
              background: config.enabled ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.1)',
              border: `1px solid ${config.enabled ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.2)'}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: config.enabled ? '#10b981' : '#f87171'
            }}>
              <Brain size={24} />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '15.5px', color: 'var(--text-main)' }}>
                AI Companion Status: {config.enabled ? 'Active & Responding' : 'Dormant (Disabled)'}
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {config.enabled
                  ? 'The bot will actively reply to mentions and messages in designated AI channels.'
                  : 'Toggle on to activate neural conversational capabilities across your server.'}
              </div>
            </div>
          </div>

          <Toggle
            checked={Boolean(config.enabled)}
            onChange={val => setConfig(c => ({ ...c, enabled: val ? 1 : 0 }))}
          />
        </CardContent>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))', gap: '24px' }}>
        {/* Left Column: Personality, Channel & Directives */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Persona Picker Card */}
          <Card>
            <CardHeader>
              <CardTitle>Conversational Personality</CardTitle>
              <CardDescription>
                Choose the behavioral style and tone the AI embodies when talking to server members.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '12px', marginBottom: '20px' }}>
                {PERSONAS.map(p => {
                  const isSelected = config.persona === p.id;
                  return (
                    <div
                      key={p.id}
                      onClick={() => setConfig({ ...config, persona: p.id })}
                      style={{
                        background: isSelected ? 'rgba(88, 101, 242, 0.1)' : 'var(--bg-surface)',
                        border: isSelected ? `2px solid ${p.color}` : '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)',
                        padding: '14px 12px',
                        cursor: 'pointer',
                        transition: 'all 150ms ease'
                      }}
                    >
                      <div style={{ fontSize: '22px', marginBottom: '6px' }}>{p.emoji}</div>
                      <div style={{ fontWeight: 600, fontSize: '13.5px', color: 'var(--text-main)' }}>{p.name}</div>
                      <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '4px', lineHeight: 1.3 }}>{p.desc}</div>
                    </div>
                  );
                })}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Dedicated AI Discussion Channel
                  </label>
                  <Select
                    value={config.ai_channel_id || ''}
                    onChange={v => setConfig({ ...config, ai_channel_id: v })}
                    options={channelSelectOptions}
                    placeholder="Select AI channel..."
                    searchable
                  />
                  <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                    In this channel, every message automatically triggers an AI reply without needing an @mention.
                  </p>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Custom Server Directives (System Prompt)
                  </label>
                  <textarea
                    className="form-input"
                    rows={4}
                    value={config.system_prompt || ''}
                    onChange={e => setConfig({ ...config, system_prompt: e.target.value })}
                    placeholder="Give your AI specific server rules, secret lore, inside jokes, or behavior boundaries..."
                    style={{ fontFamily: 'monospace', fontSize: '12.5px' }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Autonomous Feature Modules */}
          <Card>
            <CardHeader>
              <CardTitle>Autonomous Feature Modules</CardTitle>
              <CardDescription>Toggle specific neural capabilities and sub-systems on or off.</CardDescription>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {autonomousModules.map(feat => (
                  <div
                    key={feat.key}
                    style={{
                      padding: '14px 16px',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)'
                    }}
                  >
                    <Toggle
                      checked={Boolean(config[feat.key])}
                      onChange={val => setConfig(c => ({ ...c, [feat.key]: val ? 1 : 0 }))}
                      label={feat.label}
                      description={feat.desc}
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Lore & Knowledge Retention */}
        <div>
          <Card>
            <CardHeader>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <CardTitle>Lore & Memory Retention</CardTitle>
                  <CardDescription>Persistent knowledge the AI references in server conversations.</CardDescription>
                </div>
                <Badge variant="primary" size="sm">{memories.length} Facts</Badge>
              </div>
            </CardHeader>
            <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Add Fact Form */}
              <form onSubmit={handleAddMemory} style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                padding: '14px',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)'
              }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Teach AI New Fact
                </span>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Topic (e.g. Server Founder, Minecraft IP)"
                  value={newTopic}
                  onChange={e => setNewTopic(e.target.value)}
                  required
                />
                <textarea
                  className="form-input"
                  rows={2}
                  placeholder="Fact or Lore (e.g. Server was founded in 2021 by Sarah)"
                  value={newFact}
                  onChange={e => setNewFact(e.target.value)}
                  required
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Button type="submit" variant="primary" size="sm" icon={Plus} loading={addingMemory}>
                    Teach Fact
                  </Button>
                </div>
              </form>

              {/* Memory Cards */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {memories.length === 0 ? (
                  <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                    No custom facts registered yet. Teach your bot facts above or let it learn passively.
                  </div>
                ) : (
                  memories.map(m => (
                    <div
                      key={m.id}
                      style={{
                        padding: '12px 14px',
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: '12px'
                      }}
                    >
                      <div>
                        <Badge variant="primary" size="sm" style={{ marginBottom: '6px' }}>
                          {m.topic}
                        </Badge>
                        <div style={{ fontSize: '13px', color: 'var(--text-main)', lineHeight: 1.4 }}>
                          {m.fact}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDeleteMemory(m.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#f87171',
                          cursor: 'pointer',
                          padding: '4px'
                        }}
                        title="Forget memory"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
