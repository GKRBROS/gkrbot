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
  Send,
  Zap,
  Cpu
} from 'lucide-react';
import api from '../../api';
import ChannelSelect from '../../components/ChannelSelect';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import Badge from '../../components/Badge';
import Skeleton from '../../components/Skeleton';
import { useToast } from '../../components/ToastContext';

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
  const toast = useToast();

  const [config, setConfig] = useState(null);
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Memory creation state
  const [newTopic, setNewTopic] = useState('');
  const [newFact, setNewFact] = useState('');
  const [addingMemory, setAddingMemory] = useState(false);

  const fetchAI = useCallback(async () => {
    try {
      const aiRes = await api.get(`/guilds/${guildId}/ai`);
      setConfig(aiRes.data.config || {});
      setMemories(aiRes.data.memories || []);
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

    try {
      await api.post(`/guilds/${guildId}/ai`, config);
      toast('AI configuration and personality directives saved successfully!', 'success');
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to save AI configuration';
      setError(msg);
      toast(msg, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleAddMemory = async (e) => {
    e.preventDefault();
    if (!newTopic.trim() || !newFact.trim()) return;

    setAddingMemory(true);
    setError('');

    try {
      await api.post(`/guilds/${guildId}/ai/memories`, {
        topic: newTopic.trim(),
        fact: newFact.trim()
      });
      setNewTopic('');
      setNewFact('');
      toast('Memory added to neural retention bank.', 'success');
      fetchAI();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to record memory';
      setError(msg);
      toast(msg, 'error');
    } finally {
      setAddingMemory(false);
    }
  };

  const handleDeleteMemory = async (id) => {
    try {
      await api.delete(`/guilds/${guildId}/ai/memories/${id}`);
      toast('Memory forgotten.', 'info');
      fetchAI();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to remove memory';
      setError(msg);
      toast(msg, 'error');
    }
  };

  if (loading || !config) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <Skeleton height="80px" />
        <Skeleton height="90px" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton height="360px" />
          <Skeleton height="360px" />
        </div>
        <Skeleton height="260px" />
      </div>
    );
  }

  const autonomousModules = [
    { key: 'mention_enabled', label: 'Direct @Mentions', icon: MessageSquare, color: '#38bdf8', desc: 'Responds whenever a member tags the bot in any conversation.' },
    { key: 'self_learning', label: 'Self-Learning Lore', icon: Brain, color: '#a855f7', desc: 'Passively learns community facts and member nicknames from chat.' },
    { key: 'research_enabled', label: 'Live Web Research', icon: Globe, color: '#10b981', desc: 'Performs online synthesis to give accurate real-world answers.' },
    { key: 'image_enabled', label: 'FLUX Image Generation', icon: Palette, color: '#ec4899', desc: 'Synthesizes images and artwork directly inside Discord chat.' },
    { key: 'comedy_enabled', label: 'Banter & Roasts', icon: Smile, color: '#f59e0b', desc: 'Engages in witty retorts and funny banter with familiar members.' },
    { key: 'tts_enabled', label: 'Neural Audio TTS', icon: Volume2, color: '#06b6d4', desc: 'Speaks responses via voice notes when requested by members.' },
    { key: 'thread_mode', label: 'Auto Discussion Threads', icon: GitFork, color: '#6366f1', desc: 'Spins off detailed questions into dedicated Discord threads.' },
  ];

  const isMasterEnabled = Boolean(config.enabled);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
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
            Save Directives
          </Button>
        }
      />

      {error && (
        <div className="flex items-center justify-between p-4 rounded-xl bg-red-500/10 border border-red-500/25 text-red-400 text-sm">
          <div className="flex items-center gap-3">
            <AlertCircle size={18} className="shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError('')} className="text-red-400 hover:text-red-300">✕</button>
        </div>
      )}

      {/* Master Toggle Banner */}
      <Card>
        <CardContent className="p-5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 border ${
              isMasterEnabled
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                : 'bg-red-500/10 border-red-500/20 text-red-400'
            }`}>
              <Brain size={24} />
            </div>
            <div>
              <div className="font-bold text-base text-[var(--text-main)]">
                AI Companion Status: {isMasterEnabled ? 'Active & Responding' : 'Dormant (Disabled)'}
              </div>
              <div className="text-xs text-[var(--text-muted)] mt-0.5">
                {isMasterEnabled
                  ? 'The bot actively replies to mentions and messages in designated AI channels.'
                  : 'Toggle on to activate neural conversational capabilities across your server.'}
              </div>
            </div>
          </div>

          <Toggle
            checked={isMasterEnabled}
            onChange={val => setConfig(c => ({ ...c, enabled: val ? 1 : 0 }))}
          />
        </CardContent>
      </Card>

      {/* Row 1: Split 2-Column Desktop Grid for Persona & Lore */}
      <div className={`grid grid-cols-1 lg:grid-cols-2 gap-6 transition-opacity duration-200 ${!isMasterEnabled ? 'opacity-60 pointer-events-none' : ''}`}>
        {/* Left Column: Personality & Channel */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 border border-indigo-500/20">
                <Sparkles size={20} />
              </div>
              <div>
                <CardTitle>Conversational Personality</CardTitle>
                <CardDescription>
                  Choose the behavioral style and tone the AI embodies when talking to members.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] mb-2.5">
                Persona Model
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                {PERSONAS.map(p => {
                  const isSelected = config.persona === p.id;
                  return (
                    <div
                      key={p.id}
                      onClick={() => setConfig({ ...config, persona: p.id })}
                      className={`p-3 rounded-xl cursor-pointer transition-all border ${
                        isSelected
                          ? 'bg-[var(--primary)]/10 border-[var(--primary)] shadow-sm'
                          : 'bg-[var(--bg-surface)] border-[var(--border)] hover:border-[var(--border-hover)]'
                      }`}
                    >
                      <div className="text-2xl mb-1">{p.emoji}</div>
                      <div className="font-semibold text-xs text-[var(--text-main)] truncate">{p.name}</div>
                      <div className="text-[11px] text-[var(--text-muted)] mt-1 line-clamp-2 leading-tight">{p.desc}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="space-y-1.5 pt-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Dedicated AI Discussion Channel
              </label>
              <ChannelSelect
                guildId={guildId}
                value={config.ai_channel_id || ''}
                onChange={v => setConfig(prev => ({ ...prev, ai_channel_id: v }))}
                placeholder="Select AI channel (optional)..."
                allowedTypes={['text', 'news']}
              />
              <p className="text-xs text-[var(--text-muted)]">
                In this channel, every message automatically triggers an AI reply without needing an @mention.
              </p>
            </div>

            <div className="space-y-1.5 pt-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Custom Directives (System Prompt)
              </label>
              <textarea
                className="w-full bg-[var(--bg-surface)] border border-[var(--border)] rounded-xl px-4 py-2.5 text-xs font-mono text-[var(--text-main)] focus:outline-none focus:border-[var(--primary)] transition-colors resize-y"
                rows={3}
                value={config.system_prompt || ''}
                onChange={e => setConfig({ ...config, system_prompt: e.target.value })}
                placeholder="Give your AI specific server rules, secret lore, inside jokes, or behavior boundaries..."
              />
            </div>
          </CardContent>
        </Card>

        {/* Right Column: Lore & Knowledge Retention */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between w-full">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center text-purple-400 border border-purple-500/20">
                  <BookOpen size={20} />
                </div>
                <div>
                  <CardTitle>Lore & Memory Retention</CardTitle>
                  <CardDescription>Persistent facts the AI recalls during server conversations.</CardDescription>
                </div>
              </div>
              <Badge variant="primary" size="sm">{memories.length} Facts</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Add Fact Form */}
            <form onSubmit={handleAddMemory} className="p-3.5 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] space-y-2.5">
              <span className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Teach AI New Fact
              </span>
              <input
                type="text"
                className="w-full bg-[var(--bg-surface-hover)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs text-[var(--text-main)] focus:outline-none focus:border-[var(--primary)]"
                placeholder="Topic (e.g. Server Founder, Minecraft IP)"
                value={newTopic}
                onChange={e => setNewTopic(e.target.value)}
                required
              />
              <textarea
                className="w-full bg-[var(--bg-surface-hover)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs text-[var(--text-main)] focus:outline-none focus:border-[var(--primary)] resize-none"
                rows={2}
                placeholder="Fact or Lore (e.g. Server was founded in 2021 by Sarah)"
                value={newFact}
                onChange={e => setNewFact(e.target.value)}
                required
              />
              <div className="flex justify-end pt-1">
                <Button type="submit" variant="primary" size="sm" icon={Plus} loading={addingMemory}>
                  Record Fact
                </Button>
              </div>
            </form>

            {/* Memory List */}
            <div className="space-y-2 max-h-[260px] overflow-y-auto pr-1">
              {memories.length === 0 ? (
                <div className="p-6 text-center text-xs text-[var(--text-muted)]">
                  No custom facts registered yet. Teach your bot facts above or let it learn passively.
                </div>
              ) : (
                memories.map(m => (
                  <div
                    key={m.id}
                    className="p-3 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] flex items-start justify-between gap-3 hover:border-[var(--border-hover)] transition-colors"
                  >
                    <div>
                      <Badge variant="primary" size="sm" className="mb-1.5">
                        {m.topic}
                      </Badge>
                      <div className="text-xs text-[var(--text-main)] leading-relaxed">
                        {m.fact}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteMemory(m.id)}
                      className="text-red-400 hover:text-red-300 p-1 shrink-0"
                      title="Forget memory"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Row 2: Full Width Split Row/Column Grid for Autonomous Feature Modules */}
      <Card className={`transition-opacity duration-200 ${!isMasterEnabled ? 'opacity-60 pointer-events-none' : ''}`}>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center text-cyan-400 border border-cyan-500/20">
              <Cpu size={20} />
            </div>
            <div>
              <CardTitle>Autonomous Feature Modules</CardTitle>
              <CardDescription>
                Enable or disable specialized neural capabilities across chat and voice channels.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {autonomousModules.map(feat => {
              const IconComponent = feat.icon;
              const isChecked = Boolean(config[feat.key]);
              return (
                <div
                  key={feat.key}
                  className={`p-4 rounded-xl border transition-all flex flex-col justify-between ${
                    isChecked
                      ? 'bg-[var(--bg-surface)] border-[var(--border)] shadow-sm'
                      : 'bg-[var(--bg-surface)]/60 border-[var(--border)] opacity-80'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2.5">
                      <div
                        className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                        style={{ background: `${feat.color}15`, color: feat.color, border: `1px solid ${feat.color}30` }}
                      >
                        <IconComponent size={16} />
                      </div>
                      <span className="font-semibold text-xs text-[var(--text-main)]">{feat.label}</span>
                    </div>
                    <Toggle
                      checked={isChecked}
                      onChange={val => setConfig(c => ({ ...c, [feat.key]: val ? 1 : 0 }))}
                    />
                  </div>
                  <p className="text-[11.5px] text-[var(--text-muted)] leading-relaxed">
                    {feat.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
