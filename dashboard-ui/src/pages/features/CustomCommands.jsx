import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import {
  Terminal,
  Plus,
  Trash2,
  Edit2,
  Search,
  CheckCircle2,
  AlertCircle,
  Zap,
  Layers,
  Sparkles,
  Palette,
  Image as ImageIcon,
  MessageSquare
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import { useToast } from '../../components/ToastContext';
import Loader from '../../components/Loader';

export function CustomCommands() {
  const { guildId } = useParams();
  const toast = useToast();

  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [editingName, setEditingName] = useState(null);
  const [search, setSearch] = useState('');

  // Form state
  const [form, setForm] = useState({
    name: '',
    response: '',
    reply_type: 'text', // 'text' | 'embed' | 'both'
    embed: {
      title: '',
      description: '',
      color: '#5865F2',
      thumbnail: '',
      image: '',
      footer: ''
    }
  });

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/custom-commands`);
      setCommands(res.data.commands || []);
    } catch (err) {
      console.error('Failed to load custom commands', err);
      if (toast) toast('Failed to load custom commands', 'error');
    } finally {
      setLoading(false);
    }
  }, [guildId, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const cleanName = form.name.trim().toLowerCase().lstrip ? form.name.trim().toLowerCase().lstrip('!') : form.name.trim().toLowerCase().replace(/^!+/, '');
    if (!cleanName) {
      if (toast) toast('Please provide a command trigger keyword', 'error');
      return;
    }

    const hasText = Boolean(form.response.trim());
    const hasEmbed = form.reply_type !== 'text' && (Boolean(form.embed.title.trim()) || Boolean(form.embed.description.trim()));

    if (!hasText && !hasEmbed) {
      if (toast) toast('Please provide a text response or configure embed fields', 'error');
      return;
    }

    setSubmitting(true);
    const payload = {
      name: cleanName,
      response: form.response.trim(),
      reply_type: form.reply_type,
      embed_json: form.reply_type !== 'text' ? form.embed : null
    };

    try {
      if (editingName) {
        await api.put(`/guilds/${guildId}/custom-commands/${editingName}`, payload);
        if (toast) toast(`Command !${editingName} updated successfully!`, 'success');
      } else {
        await api.post(`/guilds/${guildId}/custom-commands`, payload);
        if (toast) toast(`Command !${cleanName} created successfully!`, 'success');
      }
      setForm({
        name: '',
        response: '',
        reply_type: 'text',
        embed: { title: '', description: '', color: '#5865F2', thumbnail: '', image: '', footer: '' }
      });
      setEditingName(null);
      await fetchData();
    } catch (err) {
      if (toast) toast(err.response?.data?.error || 'Failed to save command', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (cmd) => {
    let embedObj = { title: '', description: '', color: '#5865F2', thumbnail: '', image: '', footer: '' };
    if (cmd.embed_json) {
      try {
        embedObj = typeof cmd.embed_json === 'string' ? JSON.parse(cmd.embed_json) : cmd.embed_json;
      } catch {}
    }
    setEditingName(cmd.name);
    setForm({
      name: cmd.name,
      response: cmd.response || '',
      reply_type: cmd.reply_type || (cmd.embed_json ? 'embed' : 'text'),
      embed: embedObj
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (name) => {
    if (!window.confirm(`Delete command "!${name}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/guilds/${guildId}/custom-commands/${name}`);
      if (toast) toast(`Command !${name} deleted`, 'success');
      await fetchData();
    } catch (err) {
      if (toast) toast('Failed to delete command', 'error');
    }
  };

  const cancelEdit = () => {
    setEditingName(null);
    setForm({
      name: '',
      response: '',
      reply_type: 'text',
      embed: { title: '', description: '', color: '#5865F2', thumbnail: '', image: '', footer: '' }
    });
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return commands;
    const q = search.trim().toLowerCase();
    return commands.filter(c => c.name.toLowerCase().includes(q) || (c.response || '').toLowerCase().includes(q));
  }, [commands, search]);

  if (loading) {
    return <Loader label="Loading Custom Commands Studio..." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Custom Commands & Embeds"
        description="Build custom keyword triggers (!command) that deliver text, variables, or rich multi-embed responses."
        icon={Terminal}
        badge="Command Builder"
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Left: Command Creator Form */}
        <Card>
          <CardHeader>
            <CardTitle icon={Plus}>
              {editingName ? `Edit Command !${editingName}` : 'Create Custom Command'}
            </CardTitle>
            <CardDescription>
              Assign trigger keyword and choose between plain text or visual embeds.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="form-group">
                <label className="form-label">Command Trigger</label>
                <div className="relative">
                  <span className="absolute left-3 top-2.5 text-muted font-bold font-mono">!</span>
                  <input
                    type="text"
                    className="form-input pl-7!"
                    placeholder="help, rules, ip, discord..."
                    value={form.name}
                    disabled={Boolean(editingName)}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                  />
                </div>
              </div>

              {/* Mode Selector */}
              <div className="form-group">
                <label className="form-label">Response Format</label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, reply_type: 'text' })}
                    className={`px-3 py-2 text-xs font-semibold rounded-lg border transition ${
                      form.reply_type === 'text'
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border bg-surface-card text-muted hover:text-main'
                    }`}
                  >
                    Text Only
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, reply_type: 'embed' })}
                    className={`px-3 py-2 text-xs font-semibold rounded-lg border transition ${
                      form.reply_type === 'embed'
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border bg-surface-card text-muted hover:text-main'
                    }`}
                  >
                    Embed Only
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, reply_type: 'both' })}
                    className={`px-3 py-2 text-xs font-semibold rounded-lg border transition ${
                      form.reply_type === 'both'
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border bg-surface-card text-muted hover:text-main'
                    }`}
                  >
                    Text + Embed
                  </button>
                </div>
              </div>

              {/* Text Response Field */}
              {(form.reply_type === 'text' || form.reply_type === 'both') && (
                <div className="form-group">
                  <label className="form-label">Chat Message Text</label>
                  <textarea
                    className="form-input min-h-[90px]"
                    placeholder="Hey {user}, welcome to {server}! Total members: {membercount}"
                    value={form.response}
                    onChange={e => setForm({ ...form, response: e.target.value })}
                  />
                  <span className="text-[11px] text-muted block mt-1">
                    Variables: <code>{'{user}'}</code>, <code>{'{username}'}</code>, <code>{'{server}'}</code>, <code>{'{membercount}'}</code>
                  </span>
                </div>
              )}

              {/* Embed Builder Fields */}
              {(form.reply_type === 'embed' || form.reply_type === 'both') && (
                <div className="space-y-3 pt-3 border-t border-border">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
                    <Palette size={13} /> Visual Embed Settings
                  </h4>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="form-group">
                      <label className="form-label text-xs">Embed Title</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="Server Rules & Info"
                        value={form.embed.title}
                        onChange={e => setForm({ ...form, embed: { ...form.embed, title: e.target.value } })}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label text-xs">Accent Color</label>
                      <div className="flex gap-2">
                        <input
                          type="color"
                          className="w-10 h-10 rounded border border-border p-1 bg-surface-card cursor-pointer"
                          value={form.embed.color || '#5865F2'}
                          onChange={e => setForm({ ...form, embed: { ...form.embed, color: e.target.value } })}
                        />
                        <input
                          type="text"
                          className="form-input flex-1 font-mono text-xs uppercase"
                          value={form.embed.color || '#5865F2'}
                          onChange={e => setForm({ ...form, embed: { ...form.embed, color: e.target.value } })}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label text-xs">Embed Description</label>
                    <textarea
                      className="form-input min-h-[80px]"
                      placeholder="Detailed announcement or guide text..."
                      value={form.embed.description}
                      onChange={e => setForm({ ...form, embed: { ...form.embed, description: e.target.value } })}
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="form-group">
                      <label className="form-label text-xs">Thumbnail URL</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="https://.../icon.png"
                        value={form.embed.thumbnail}
                        onChange={e => setForm({ ...form, embed: { ...form.embed, thumbnail: e.target.value } })}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label text-xs">Banner Image URL</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="https://.../banner.png"
                        value={form.embed.image}
                        onChange={e => setForm({ ...form, embed: { ...form.embed, image: e.target.value } })}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label text-xs">Footer Text</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="Powered by GKR Bot"
                      value={form.embed.footer}
                      onChange={e => setForm({ ...form, embed: { ...form.embed, footer: e.target.value } })}
                    />
                  </div>
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <Button type="submit" variant="primary" loading={submitting} className="flex-1">
                  {editingName ? 'Update Command' : 'Save Command'}
                </Button>
                {editingName && (
                  <Button type="button" variant="secondary" onClick={cancelEdit}>
                    Cancel
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Right: Live Preview Card */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle icon={Sparkles}>Live Discord Message Preview</CardTitle>
              <CardDescription>Simulated view of the bot response inside Discord.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="p-4 rounded-xl bg-[#313338] text-[#dbdee1] font-sans text-sm border border-black/20 shadow-inner space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center font-bold text-xs text-white">
                    GKR
                  </div>
                  <div>
                    <span className="font-semibold text-white mr-1.5">GKR Bot</span>
                    <span className="text-[10px] uppercase font-bold bg-[#5865F2] text-white px-1 py-0.5 rounded">BOT</span>
                  </div>
                </div>

                {/* Text Content */}
                {(form.reply_type === 'text' || form.reply_type === 'both') && form.response && (
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">
                    {form.response.replace('{user}', '@Username').replace('{server}', 'Server Name')}
                  </p>
                )}

                {/* Embed Preview */}
                {(form.reply_type === 'embed' || form.reply_type === 'both') && (form.embed.title || form.embed.description) && (
                  <div
                    className="p-3.5 rounded bg-[#2b2d31] border-l-4 space-y-2"
                    style={{ borderLeftColor: form.embed.color || '#5865F2' }}
                  >
                    <div className="flex justify-between items-start gap-3">
                      <div className="space-y-1 min-w-0">
                        {form.embed.title && (
                          <h4 className="font-bold text-white text-base">{form.embed.title}</h4>
                        )}
                        {form.embed.description && (
                          <p className="text-xs text-[#dbdee1] whitespace-pre-wrap">{form.embed.description}</p>
                        )}
                      </div>
                      {form.embed.thumbnail && (
                        <img
                          src={form.embed.thumbnail}
                          alt=""
                          className="w-14 h-14 rounded object-cover shrink-0"
                          onError={e => { e.target.style.display = 'none'; }}
                        />
                      )}
                    </div>

                    {form.embed.image && (
                      <img
                        src={form.embed.image}
                        alt=""
                        className="w-full max-h-48 rounded object-cover mt-2"
                        onError={e => { e.target.style.display = 'none'; }}
                      />
                    )}

                    {form.embed.footer && (
                      <span className="text-[11px] text-[#949ba4] block pt-1 border-t border-white/5">
                        {form.embed.footer}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* List of Existing Commands */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <CardTitle icon={Terminal}>Server Commands ({commands.length})</CardTitle>
                  <CardDescription>All trigger keywords configured for this guild.</CardDescription>
                </div>
                <div className="w-48">
                  <input
                    type="text"
                    className="form-input text-xs"
                    placeholder="Search commands..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {filtered.length === 0 ? (
                <div className="text-center py-6 text-xs text-muted">
                  No matching custom commands found.
                </div>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto">
                  {filtered.map(cmd => (
                    <div
                      key={cmd.id || cmd.name}
                      className="flex items-center justify-between p-3 rounded-lg border border-border bg-surface-card hover:bg-surface-hover/30 transition"
                    >
                      <div className="truncate mr-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-primary text-sm">!{cmd.name}</span>
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-surface-hover text-muted">
                            {cmd.reply_type || (cmd.embed_json ? 'embed' : 'text')}
                          </span>
                          <span className="text-[10px] text-muted">used {cmd.uses || 0}×</span>
                        </div>
                        <p className="text-xs text-muted truncate mt-0.5">
                          {cmd.response || (cmd.embed_json ? 'Rich Embed Response' : '')}
                        </p>
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleEdit(cmd)}
                          className="btn btn-ghost btn-sm text-primary hover:bg-primary/10"
                          title="Edit command"
                        >
                          <Edit2 size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(cmd.name)}
                          className="btn btn-ghost btn-sm text-danger hover:bg-danger/10"
                          title="Delete command"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default CustomCommands;
