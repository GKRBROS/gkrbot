import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';

function CustomCommands() {
  const { guildId } = useParams();
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [editingName, setEditingName] = useState(null);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState({ name: '', response: '' });

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/custom-commands`);
      setCommands(res.data.commands || []);
    } catch (err) {
      console.error('Failed to load custom commands', err);
    }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      if (editingName) {
        await api.put(`/guilds/${guildId}/custom-commands/${editingName}`, { response: form.response });
      } else {
        await api.post(`/guilds/${guildId}/custom-commands`, form);
      }
      setForm({ name: '', response: '' });
      setEditingName(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save command');
    }
    setSubmitting(false);
  };

  const handleEdit = (cmd) => {
    setEditingName(cmd.name);
    setForm({ name: cmd.name, response: cmd.response });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (name) => {
    if (!window.confirm(`Delete command "!${name}"?`)) return;
    try {
      await api.delete(`/guilds/${guildId}/custom-commands/${name}`);
      await fetchData();
    } catch (err) {
      console.error('Failed to delete command', err);
    }
  };

  const filtered = commands.filter(c =>
    c.name.toLowerCase().includes(search.trim().toLowerCase()) ||
    c.response.toLowerCase().includes(search.trim().toLowerCase())
  );

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '300px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h2 className="page-title"><span>💬</span> Custom Commands</h2>
        <p className="page-subtitle">
          Create your own commands. Members trigger them with <span className="badge badge-primary">!name</span> in chat.
          Variables: {'{user}'} {'{username}'} {'{server}'} {'{membercount}'}
        </p>
      </div>

      {/* Create / Edit form */}
      <div className="glass-panel" style={{ padding: '24px', marginBottom: '32px', border: '1px solid var(--primary)' }}>
        <h3 className="section-title" style={{ marginBottom: '18px', border: 'none', padding: 0 }}>
          {editingName ? `✏️ Edit Command: !${editingName}` : '➕ Create New Command'}
        </h3>
        {error && <div className="alert alert-error">{error}</div>}
        {saved && <div className="alert alert-success">✅ Command saved!</div>}

        <form onSubmit={handleSubmit}>
          <div className="grid-2" style={{ alignItems: 'end' }}>
            <div className="form-group">
              <label className="form-label">Command Name</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '18px', fontWeight: 800, color: 'var(--accent)', fontFamily: 'monospace' }}>!</span>
                <input
                  type="text"
                  className="input-field"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. rules"
                  disabled={!!editingName}
                  required
                  maxLength={30}
                  style={{ fontFamily: 'monospace' }}
                />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Response</label>
              <textarea
                className="input-field"
                rows={2}
                value={form.response}
                onChange={e => setForm({ ...form, response: e.target.value })}
                placeholder="Welcome to {server}! Please read the rules..."
                required
                maxLength={2000}
              />
            </div>
          </div>

          <div className="flex justify-end gap-3">
            {editingName && (
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => { setEditingName(null); setForm({ name: '', response: '' }); }}
              >
                Cancel
              </button>
            )}
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Saving...' : (editingName ? 'Save Changes' : '➕ Create Command')}
            </button>
          </div>
        </form>
      </div>

      {/* List */}
      <div className="section-header">
        <h3 className="section-title">
          Commands <span className="section-count">{commands.length}</span>
        </h3>
        {commands.length > 3 && (
          <input
            type="text"
            className="input-field"
            placeholder="🔍 Search commands..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ maxWidth: '260px' }}
          />
        )}
      </div>

      {commands.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">💬</div>
          <h3 className="empty-state-title">No custom commands yet</h3>
          <p className="empty-state-desc">Create your first command above — members can trigger it with <strong>!name</strong>.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">🔍</div>
          <h3 className="empty-state-title">No matches</h3>
        </div>
      ) : (
        <div className="grid-auto stagger">
          {filtered.map(cmd => (
            <div key={cmd.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div className="flex items-center justify-between">
                <span className="badge badge-primary" style={{ fontFamily: 'monospace', fontSize: '13px' }}>!{cmd.name}</span>
                <div style={{ display: 'flex', gap: '2px' }}>
                  <button onClick={() => handleEdit(cmd)} className="btn btn-icon btn-ghost" style={{ color: 'var(--primary)', padding: '6px' }} title="Edit">✏️</button>
                  <button onClick={() => handleDelete(cmd.name)} className="btn btn-icon btn-ghost" style={{ color: 'var(--danger)', padding: '6px' }} title="Delete">🗑️</button>
                </div>
              </div>
              <p style={{
                fontSize: '13px', color: 'var(--text-sub)', lineHeight: '1.6', flex: 1,
                display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                whiteSpace: 'pre-wrap'
              }}>
                {cmd.response}
              </p>
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: '10px', fontSize: '12px', color: 'var(--text-muted)' }}>
                🔥 Used {cmd.uses || 0} time{cmd.uses === 1 ? '' : 's'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default CustomCommands;
