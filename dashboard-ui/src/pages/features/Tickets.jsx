import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { withSync, syncParams } from '../../sync';
import { Select, MultiSelect } from '../../components/Select';

function Tickets() {
  const { guildId } = useParams();
  const [activeTab, setActiveTab] = useState('categories'); // 'categories' | 'hub' | 'tickets' | 'settings'

  const [categories, setCategories] = useState([]);
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [stats, setStats] = useState({ categories_count: 0, total_tickets: 0, open_tickets: 0, closed_tickets: 0, hubs_count: 0 });
  const [activeTickets, setActiveTickets] = useState([]);
  const [logChannelId, setLogChannelId] = useState('');
  const [logChannelSaved, setLogChannelSaved] = useState(false);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Category modal
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({
    name: '', button_label: '', button_emoji: '🎫', embed_title: 'New Ticket', embed_description: '',
  });
  const [pingRoles, setPingRoles] = useState([]);
  const [adminRoles, setAdminRoles] = useState([]);

  // Hub Builder State
  const [hubTitle, setHubTitle] = useState('🎫 Support Ticket Hub');
  const [hubDesc, setHubDesc] = useState('Please click the button below corresponding to your inquiry to open a private support ticket.');
  const [hubColor, setHubColor] = useState('#5865F2');
  const [hubFooter, setHubFooter] = useState('GKR Bot Support System');
  const [hubChannelId, setHubChannelId] = useState('');
  const [selectedHubCats, setSelectedHubCats] = useState([]);
  const [publishingHub, setPublishingHub] = useState(false);

  const EMPTY_FORM = {
    name: '', button_label: '', button_emoji: '🎫', embed_title: 'New Ticket', embed_description: '',
  };

  const fetchData = useCallback(async () => {
    const [ticketsRes, channelsRes, rolesRes, statsRes, listRes] = await Promise.allSettled([
      api.get(`/guilds/${guildId}/tickets`),
      api.get(`/guilds/${guildId}/channels`),
      api.get(`/guilds/${guildId}/roles`),
      api.get(`/guilds/${guildId}/tickets/stats`),
      api.get(`/guilds/${guildId}/tickets/list`),
    ]);

    if (ticketsRes.status === 'fulfilled') {
      const cats = ticketsRes.value.data.categories || [];
      setCategories(cats);
      setLogChannelId(ticketsRes.value.data.log_channel_id || '');
      // By default select all categories in hub builder if none selected yet
      setSelectedHubCats(prev => prev.length ? prev : cats.map(c => c.id));
    }

    if (channelsRes.status === 'fulfilled') {
      setChannels(channelsRes.value.data.channels || []);
    }

    if (rolesRes.status === 'fulfilled') {
      setRoles(rolesRes.value.data.roles || []);
    }

    if (statsRes.status === 'fulfilled') {
      setStats(statsRes.value.data);
    }

    if (listRes.status === 'fulfilled') {
      setActiveTickets(listRes.value.data.tickets || []);
    }

    setLoading(false);
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddCategory = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      const payload = { ...form, ping_roles: pingRoles.join(', '), admin_roles: adminRoles.join(', ') };
      if (editingId) {
        await api.put(`/guilds/${guildId}/tickets/categories/${editingId}`, withSync(payload));
        setSuccess('Category updated successfully!');
      } else {
        await api.post(`/guilds/${guildId}/tickets`, withSync(payload));
        setSuccess('Category created successfully!');
      }
      await fetchData();
      setShowForm(false);
      setEditingId(null);
      setForm(EMPTY_FORM);
      setPingRoles([]);
      setAdminRoles([]);
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
    });
    setPingRoles(cat.ping_roles ? cat.ping_roles.split(',').map(s => s.trim()).filter(Boolean) : []);
    setAdminRoles(cat.admin_roles ? cat.admin_roles.split(',').map(s => s.trim()).filter(Boolean) : []);
    setShowForm(true);
  };

  const handleDeleteCategory = async (catId) => {
    if (!window.confirm('Delete this category? Active tickets under this category may become unmanaged.')) return;
    try {
      await api.delete(`/guilds/${guildId}/tickets/${catId}${syncParams()}`);
      await fetchData();
      setSuccess('Category deleted.');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete category');
    }
  };

  const handleSaveLogChannel = async () => {
    try {
      await api.post(`/guilds/${guildId}/tickets/log-channel`, withSync({ channel_id: logChannelId }));
      setLogChannelSaved(true);
      setTimeout(() => setLogChannelSaved(false), 3000);
      setSuccess('Log channel saved!');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save log channel');
    }
  };

  const handlePublishHub = async (e) => {
    e.preventDefault();
    if (!hubChannelId) {
      setError('Please select a target channel to publish the ticket hub.');
      return;
    }
    if (!selectedHubCats.length) {
      setError('Please select at least one ticket category for the hub.');
      return;
    }
    setPublishingHub(true);
    setError('');
    setSuccess('');
    try {
      const res = await api.post(`/guilds/${guildId}/tickets/hub`, {
        channel_id: hubChannelId,
        category_ids: selectedHubCats,
        title: hubTitle,
        description: hubDesc,
        embed_color: hubColor,
        footer: hubFooter,
      });
      setSuccess('🎉 Ticket Hub published to Discord successfully!');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to publish ticket hub');
    } finally {
      setPublishingHub(false);
    }
  };

  const channelOptions = channels.map(c => ({ value: c.id, label: `#${c.name}` }));
  const roleOptions = roles.map(r => ({ value: r.id, label: `@${r.name}` }));

  if (loading) {
    return <div className="feature-page" style={{ padding: '40px', textAlign: 'center' }}>Loading Ticket System...</div>;
  }

  return (
    <div className="feature-page">
      {/* Header */}
      <div className="feature-header">
        <div>
          <h1 className="feature-title">🎫 Tickets System</h1>
          <p className="feature-desc">Interactive ticket hubs, multiple support categories, private channels & transcript logs.</p>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span>{error}</span>
          <button className="btn-secondary" onClick={() => setError('')} style={{ padding: '2px 8px' }}>✕</button>
        </div>
      )}

      {success && (
        <div className="alert alert-success" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span>{success}</span>
          <button className="btn-secondary" onClick={() => setSuccess('')} style={{ padding: '2px 8px' }}>✕</button>
        </div>
      )}

      {/* Stats Counter Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px', marginBottom: '24px' }}>
        <div className="dashboard-card" style={{ padding: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700' }}>Categories</div>
          <div style={{ fontSize: '26px', fontWeight: '800', color: 'var(--text-main)', marginTop: '4px' }}>{stats.categories_count || categories.length}</div>
        </div>
        <div className="dashboard-card" style={{ padding: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700' }}>Active Open Tickets</div>
          <div style={{ fontSize: '26px', fontWeight: '800', color: '#10b981', marginTop: '4px' }}>{stats.open_tickets || activeTickets.length}</div>
        </div>
        <div className="dashboard-card" style={{ padding: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700' }}>Closed Tickets</div>
          <div style={{ fontSize: '26px', fontWeight: '800', color: 'var(--text-muted)', marginTop: '4px' }}>{stats.closed_tickets || 0}</div>
        </div>
        <div className="dashboard-card" style={{ padding: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700' }}>All-Time Created</div>
          <div style={{ fontSize: '26px', fontWeight: '800', color: 'var(--primary)', marginTop: '4px' }}>{stats.total_tickets || 0}</div>
        </div>
      </div>

      {/* Tab Nav */}
      <div className="tabs-container" style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '24px' }}>
        <button
          className={`tab-btn ${activeTab === 'categories' ? 'active' : ''}`}
          onClick={() => setActiveTab('categories')}
          style={{ padding: '10px 18px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: '600', color: activeTab === 'categories' ? 'var(--primary)' : 'var(--text-muted)', borderBottom: activeTab === 'categories' ? '2px solid var(--primary)' : 'none' }}
        >
          📂 Ticket Categories ({categories.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'hub' ? 'active' : ''}`}
          onClick={() => setActiveTab('hub')}
          style={{ padding: '10px 18px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: '600', color: activeTab === 'hub' ? 'var(--primary)' : 'var(--text-muted)', borderBottom: activeTab === 'hub' ? '2px solid var(--primary)' : 'none' }}
        >
          🚀 Multi-Category Hub Builder
        </button>
        <button
          className={`tab-btn ${activeTab === 'tickets' ? 'active' : ''}`}
          onClick={() => setActiveTab('tickets')}
          style={{ padding: '10px 18px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: '600', color: activeTab === 'tickets' ? 'var(--primary)' : 'var(--text-muted)', borderBottom: activeTab === 'tickets' ? '2px solid var(--primary)' : 'none' }}
        >
          🎫 Open Tickets ({activeTickets.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
          style={{ padding: '10px 18px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: '600', color: activeTab === 'settings' ? 'var(--primary)' : 'var(--text-muted)', borderBottom: activeTab === 'settings' ? '2px solid var(--primary)' : 'none' }}
        >
          ⚙️ Settings & Logs
        </button>
      </div>

      {/* TAB 1: Categories */}
      {activeTab === 'categories' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '18px' }}>Configured Categories</h3>
            <button
              className="btn-primary"
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY_FORM);
                setPingRoles([]);
                setAdminRoles([]);
                setShowForm(true);
              }}
            >
              + Create Category
            </button>
          </div>

          {categories.length === 0 ? (
            <div className="dashboard-card" style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '32px', marginBottom: '8px' }}>🎫</div>
              <div>No ticket categories yet. Create your first category above!</div>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
              {categories.map(cat => (
                <div key={cat.id} className="dashboard-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <h4 style={{ margin: '0 0 4px', fontSize: '17px', color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span>{cat.button_emoji || '🎫'}</span> {cat.name}
                      </h4>
                      <span className="badge badge-primary" style={{ fontSize: '11px' }}>#{cat.ticket_counter || 0} Tickets</span>
                    </div>

                    <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--text-muted)' }}>
                      <div><strong>Button:</strong> {cat.button_label || cat.name}</div>
                      <div style={{ marginTop: '4px' }}><strong>Embed Title:</strong> {cat.embed_title || 'New Ticket'}</div>
                      {cat.ping_roles && (
                        <div style={{ marginTop: '4px' }}>
                          <strong>Ping:</strong> {cat.ping_roles.split(',').length} role(s)
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px', marginTop: '20px', justifyContent: 'flex-end' }}>
                    <button className="btn-secondary" onClick={() => handleEditCategory(cat)} style={{ padding: '6px 14px', fontSize: '12px' }}>Edit</button>
                    <button className="btn-danger" onClick={() => handleDeleteCategory(cat.id)} style={{ padding: '6px 14px', fontSize: '12px' }}>Delete</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: Multi-Category Hub Builder */}
      {activeTab === 'hub' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
          {/* Builder Form */}
          <div className="dashboard-card" style={{ padding: '24px' }}>
            <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>Configure Ticket Hub</h3>
            <form onSubmit={handlePublishHub} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="form-group">
                <label className="form-label">Destination Discord Channel</label>
                <Select
                  value={hubChannelId}
                  onChange={setHubChannelId}
                  options={channelOptions}
                  placeholder="Select channel where hub will be posted..."
                  searchable
                />
              </div>

              <div className="form-group">
                <label className="form-label">Hub Embed Title</label>
                <input
                  type="text"
                  className="form-input"
                  value={hubTitle}
                  onChange={e => setHubTitle(e.target.value)}
                  placeholder="Support Ticket Hub"
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Hub Embed Description</label>
                <textarea
                  className="form-input"
                  rows={3}
                  value={hubDesc}
                  onChange={e => setHubDesc(e.target.value)}
                  placeholder="Explain how members can open a ticket..."
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">Embed Accent Color</label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input
                      type="color"
                      value={hubColor}
                      onChange={e => setHubColor(e.target.value)}
                      style={{ width: '40px', height: '38px', borderRadius: '6px', border: 'none', cursor: 'pointer' }}
                    />
                    <input
                      type="text"
                      className="form-input"
                      value={hubColor}
                      onChange={e => setHubColor(e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Footer Text</label>
                  <input
                    type="text"
                    className="form-input"
                    value={hubFooter}
                    onChange={e => setHubFooter(e.target.value)}
                    placeholder="Footer label..."
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Categories to Include in this Hub</label>
                {categories.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No categories created yet.</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '180px', overflowY: 'auto', padding: '8px', border: '1px solid var(--border-color)', borderRadius: '8px' }}>
                    {categories.map(cat => (
                      <label key={cat.id} style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '14px', cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={selectedHubCats.includes(cat.id)}
                          onChange={e => {
                            if (e.target.checked) {
                              setSelectedHubCats([...selectedHubCats, cat.id]);
                            } else {
                              setSelectedHubCats(selectedHubCats.filter(id => id !== cat.id));
                            }
                          }}
                        />
                        <span>{cat.button_emoji || '🎫'} {cat.name} ({cat.button_label || cat.name})</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={publishingHub || !hubChannelId || !selectedHubCats.length}
                className="btn-primary"
                style={{ padding: '12px', fontSize: '15px', fontWeight: '700', marginTop: '8px' }}
              >
                {publishingHub ? '🚀 Publishing to Discord...' : '🚀 Publish Ticket Hub Panel'}
              </button>
            </form>
          </div>

          {/* Live Discord Embed Preview */}
          <div className="dashboard-card" style={{ padding: '24px' }}>
            <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>Discord Live Preview</h3>
            
            {/* Mock Discord Message */}
            <div style={{ background: '#2b2d31', borderRadius: '8px', padding: '16px', color: '#dbdee1', fontFamily: 'Whitney, "Helvetica Neue", Helvetica, Arial, sans-serif' }}>
              <div style={{ display: 'flex', gap: '12px', marginBottom: '8px' }}>
                <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: '#5865F2', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 'bold' }}>
                  BOT
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontWeight: '600', color: '#f2f3f5', fontSize: '15px' }}>Support Bot</span>
                    <span style={{ background: '#5865F2', color: '#fff', fontSize: '10px', padding: '1px 4px', borderRadius: '3px', fontWeight: '600' }}>BOT</span>
                    <span style={{ fontSize: '12px', color: '#949ba4' }}>Today at 12:00 PM</span>
                  </div>
                </div>
              </div>

              {/* Embed Box */}
              <div style={{
                borderLeft: `4px solid ${hubColor}`,
                background: '#1e1f22',
                borderRadius: '4px',
                padding: '12px 16px',
                marginLeft: '52px',
                marginBottom: '12px',
              }}>
                <div style={{ fontWeight: '700', color: '#f2f3f5', fontSize: '16px', marginBottom: '8px' }}>
                  {hubTitle || 'Support Ticket Hub'}
                </div>
                <div style={{ fontSize: '14px', color: '#dbdee1', whiteHeight: '1.4', marginBottom: '12px', whiteSpace: 'pre-wrap' }}>
                  {hubDesc || 'Please select a category below...'}
                </div>
                {hubFooter && (
                  <div style={{ fontSize: '12px', color: '#949ba4', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '8px' }}>
                    {hubFooter}
                  </div>
                )}
              </div>

              {/* Buttons Row Preview */}
              <div style={{ marginLeft: '52px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {selectedHubCats.map(cid => {
                  const cat = categories.find(c => c.id === cid);
                  if (!cat) return null;
                  return (
                    <div
                      key={cid}
                      style={{
                        background: '#4e5058',
                        color: '#fff',
                        padding: '8px 14px',
                        borderRadius: '4px',
                        fontSize: '14px',
                        fontWeight: '500',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        cursor: 'not-allowed',
                      }}
                    >
                      <span>{cat.button_emoji || '🎫'}</span>
                      <span>{cat.button_label || cat.name}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: Active Tickets */}
      {activeTab === 'tickets' && (
        <div className="dashboard-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '18px' }}>Currently Active Tickets</h3>
            <button className="btn-secondary" onClick={fetchData} style={{ padding: '6px 14px' }}>🔄 Refresh</button>
          </div>

          {activeTickets.length === 0 ? (
            <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '28px', marginBottom: '8px' }}>🎉</div>
              <div>No open support tickets at the moment!</div>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '12px 8px' }}>#</th>
                    <th style={{ padding: '12px 8px' }}>Category</th>
                    <th style={{ padding: '12px 8px' }}>Channel Name</th>
                    <th style={{ padding: '12px 8px' }}>Ticket Owner</th>
                    <th style={{ padding: '12px 8px' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {activeTickets.map(t => (
                    <tr key={t.channel_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <td style={{ padding: '12px 8px', fontWeight: '700' }}>#{t.ticket_number}</td>
                      <td style={{ padding: '12px 8px' }}><span className="badge badge-primary">{t.category_name}</span></td>
                      <td style={{ padding: '12px 8px', color: 'var(--primary)' }}>#{t.channel_name}</td>
                      <td style={{ padding: '12px 8px' }}>{t.owner_name}</td>
                      <td style={{ padding: '12px 8px' }}><span className="badge badge-success">Open</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: Settings & Logs */}
      {activeTab === 'settings' && (
        <div className="dashboard-card" style={{ padding: '24px', maxWidth: '600px' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>Ticket Audit Logging</h3>
          <div className="form-group" style={{ marginBottom: '20px' }}>
            <label className="form-label">Ticket Transcript & Activity Log Channel</label>
            <p style={{ margin: '0 0 8px', fontSize: '13px', color: 'var(--text-muted)' }}>
              Closed tickets and action records will be sent to this channel.
            </p>
            <Select
              value={logChannelId}
              onChange={setLogChannelId}
              options={channelOptions}
              placeholder="Select log channel..."
              searchable
            />
          </div>

          <button className="btn-primary" onClick={handleSaveLogChannel}>
            {logChannelSaved ? '✓ Saved!' : 'Save Log Channel'}
          </button>
        </div>
      )}

      {/* Category Create/Edit Modal */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '540px' }}>
            <h3 style={{ marginTop: 0 }}>{editingId ? 'Edit Category' : 'New Ticket Category'}</h3>
            <form onSubmit={handleAddCategory} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group">
                <label className="form-label">Category Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. General Support"
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">Button Emoji</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.button_emoji}
                    onChange={e => setForm({ ...form, button_emoji: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Button Label</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.button_label}
                    onChange={e => setForm({ ...form, button_label: e.target.value })}
                    placeholder="Create Support Ticket"
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Ticket Embed Title</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.embed_title}
                  onChange={e => setForm({ ...form, embed_title: e.target.value })}
                  placeholder="Ticket title inside channel"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Ticket Embed Description</label>
                <textarea
                  className="form-input"
                  rows={3}
                  value={form.embed_description}
                  onChange={e => setForm({ ...form, embed_description: e.target.value })}
                  placeholder="Instructions for member when ticket opens..."
                />
              </div>

              <div className="form-group">
                <label className="form-label">Staff Ping Roles</label>
                <MultiSelect
                  value={pingRoles}
                  onChange={setPingRoles}
                  options={roleOptions}
                  placeholder="Select roles to ping on ticket creation..."
                />
              </div>

              <div className="form-group">
                <label className="form-label">Ticket Admin Roles (Can Close/Manage)</label>
                <MultiSelect
                  value={adminRoles}
                  onChange={setAdminRoles}
                  options={roleOptions}
                  placeholder="Select roles allowed to manage tickets..."
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '14px' }}>
                <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Saving...' : editingId ? 'Update Category' : 'Create Category'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Tickets;
