import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { withSync, syncParams } from '../../sync';

function Tickets() {
  const { guildId } = useParams();
  const [categories, setCategories] = useState([]);
  const [channels, setChannels] = useState([]);
  const [logChannelId, setLogChannelId] = useState('');
  const [logChannelSaved, setLogChannelSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({
    name: '', button_label: '', button_emoji: '🎫', embed_title: 'New Ticket', embed_description: '',
    ping_roles: '', admin_roles: '',
  });

  const EMPTY_FORM = {
    name: '', button_label: '', button_emoji: '🎫', embed_title: 'New Ticket', embed_description: '',
    ping_roles: '', admin_roles: '',
  };

  const fetchData = useCallback(async () => {
    try {
      const [ticketsRes, channelsRes] = await Promise.all([
        api.get(`/guilds/${guildId}/tickets`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      setCategories(ticketsRes.data.categories || []);
      setLogChannelId(ticketsRes.data.log_channel_id || '');
      setChannels(channelsRes.data.channels || []);
    } catch (err) {
      console.error('Failed to fetch tickets data', err);
    }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleAddCategory = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      if (editingId) {
        await api.put(`/guilds/${guildId}/tickets/categories/${editingId}`, withSync(form));
      } else {
        await api.post(`/guilds/${guildId}/tickets`, withSync(form));
      }
      await fetchData();
      setShowForm(false);
      setEditingId(null);
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(err.response?.data?.error || (editingId ? 'Failed to update category' : 'Failed to create category'));
    }
    setSubmitting(false);
  };

  const handleEditCategory = (cat) => {
    setEditingId(cat.id);
    setForm({
      name: cat.name || '',
      button_label: cat.button_label || '',
      button_emoji: cat.button_emoji || '🎫',
      embed_title: cat.embed_title || '',
      embed_description: cat.embed_description || '',
      ping_roles: cat.ping_roles || '',
      admin_roles: cat.admin_roles || '',
    });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (catId, catName) => {
    if (!window.confirm(`Delete ticket category "${catName}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/guilds/${guildId}/tickets/${catId}`, { params: syncParams() });
      await fetchData();
    } catch (err) {
      console.error('Failed to delete category', err);
    }
  };

  const handleSaveLogChannel = async () => {
    try {
      await api.post(`/guilds/${guildId}/tickets/log-channel`, withSync({ channel_id: logChannelId || null }));
      setLogChannelSaved(true);
      setTimeout(() => setLogChannelSaved(false), 2500);
    } catch (err) {
      console.error('Failed to save log channel', err);
    }
  };

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
        <h1 className="page-title">🎫 Tickets</h1>
        <p className="page-subtitle">Manage ticket categories and configure the transcript log channel.</p>
      </div>

      <div className="grid-2" style={{ marginBottom: '24px' }}>
        {/* Log Channel Panel */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h3 className="section-title" style={{ marginBottom: '16px', border: 'none', padding: 0 }}>
            📋 Transcript Log Channel
          </h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '16px', lineHeight: 1.5 }}>
            When a ticket is closed, a full transcript HTML file will be sent to this channel.
          </p>
          <div className="flex gap-2">
            <select
              value={logChannelId}
              onChange={e => setLogChannelId(e.target.value)}
              className="input-field flex-1"
            >
              <option value="">None (Disabled)</option>
              {channels.map(ch => (
                <option key={ch.id} value={ch.id}>#{ch.name}</option>
              ))}
            </select>
            <button onClick={handleSaveLogChannel} className={`btn ${logChannelSaved ? 'btn-success' : 'btn-primary'}`}>
              {logChannelSaved ? '✅ Saved' : 'Save'}
            </button>
          </div>
        </div>

        {/* Stats Panel */}
        <div className="glass-panel flex flex-col justify-center" style={{ padding: '24px', alignItems: 'center' }}>
          <div className="stat-icon" style={{ background: 'rgba(245, 158, 11, 0.15)', color: 'var(--warning)', marginBottom: '12px' }}>
            🏷️
          </div>
          <div className="stat-value">{categories.length}</div>
          <div className="stat-label">Active Categories</div>
        </div>
      </div>

      <div className="section-header" style={{ marginTop: '40px' }}>
        <h2 className="section-title">Ticket Categories <span className="section-count">{categories.length}</span></h2>
        <button
          className="btn btn-primary"
          onClick={() => {
            if (showForm) {
              setEditingId(null);
              setForm(EMPTY_FORM);
            }
            setShowForm(!showForm);
          }}
        >
          {showForm ? 'Cancel' : '+ New Category'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleAddCategory} className="glass-panel animate-fade-in" style={{ padding: '24px', marginBottom: '24px', border: '1px solid var(--primary)' }}>
          <h3 style={{ marginBottom: '20px', fontSize: '16px' }}>
            {editingId ? `✏️ Edit Category (ID: ${editingId})` : 'Create New Ticket Category'}
          </h3>
          {error && <div className="alert alert-error">{error}</div>}
          
          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Category Name</label>
              <input type="text" className="input-field" value={form.name} onChange={e => setForm({...form, name: e.target.value})} placeholder="e.g. Support" required />
            </div>
            <div className="form-group">
              <label className="form-label">Button Label</label>
              <input type="text" className="input-field" value={form.button_label} onChange={e => setForm({...form, button_label: e.target.value})} placeholder="e.g. Open Support Ticket" required />
            </div>
          </div>

          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Button Emoji</label>
              <input type="text" className="input-field" value={form.button_emoji} onChange={e => setForm({...form, button_emoji: e.target.value})} placeholder="e.g. 🎫" required />
            </div>
            <div className="form-group">
              <label className="form-label">Embed Title</label>
              <input type="text" className="input-field" value={form.embed_title} onChange={e => setForm({...form, embed_title: e.target.value})} placeholder="e.g. Support Ticket" required />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Embed Description</label>
            <textarea className="input-field" value={form.embed_description} onChange={e => setForm({...form, embed_description: e.target.value})} placeholder="Welcome to support! Please describe your issue..." required rows={3}></textarea>
          </div>

          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Ping Roles (Role IDs, comma separated — optional)</label>
              <input type="text" className="input-field" value={form.ping_roles} onChange={e => setForm({...form, ping_roles: e.target.value})} placeholder="e.g. 123456789012345678, 987654321098765432" />
            </div>
            <div className="form-group">
              <label className="form-label">Admin Roles (Role IDs, comma separated — optional)</label>
              <input type="text" className="input-field" value={form.admin_roles} onChange={e => setForm({...form, admin_roles: e.target.value})} placeholder="e.g. 123456789012345678" />
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-4">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => { setShowForm(false); setEditingId(null); setForm(EMPTY_FORM); }}
            >
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Saving...' : (editingId ? 'Save Changes' : 'Create Category')}
            </button>
          </div>
        </form>
      )}

      {categories.length === 0 && !showForm ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">📝</div>
          <h3 className="empty-state-title">No Categories Found</h3>
          <p className="empty-state-desc">Create a ticket category so users can open tickets in your server.</p>
          <button className="btn btn-primary" onClick={() => setShowForm(true)} style={{ marginTop: '16px' }}>Create Category</button>
        </div>
      ) : (
        <div className="grid-3 stagger">
          {categories.map(cat => (
            <div key={cat.id} className="card flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between" style={{ marginBottom: '12px' }}>
                  <span className="badge badge-primary">{cat.button_emoji} {cat.name}</span>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button
                      onClick={() => handleEditCategory(cat)}
                      className="btn btn-icon btn-ghost"
                      style={{ color: 'var(--primary)', padding: '4px' }}
                      title="Edit category"
                    >
                      ✏️
                    </button>
                    <button onClick={() => handleDelete(cat.id, cat.name)} className="btn btn-icon btn-ghost" style={{ color: 'var(--danger)', padding: '4px' }} title="Delete">
                      🗑️
                    </button>
                  </div>
                </div>
                <h4 style={{ fontSize: '15px', marginBottom: '8px', color: 'var(--text-main)' }}>{cat.embed_title}</h4>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: '1.5', marginBottom: '16px', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {cat.embed_description}
                </p>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.04)', padding: '10px 14px', borderRadius: '6px', fontSize: '12px', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-sub)' }}>Button Text:</span>
                <span style={{ color: 'var(--text-main)', fontWeight: '500' }}>{cat.button_label}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Tickets;
