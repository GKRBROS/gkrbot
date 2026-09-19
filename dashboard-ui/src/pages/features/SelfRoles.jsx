import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

function SelfRoles() {
  const { guildId } = useParams();
  const [menus, setMenus] = useState([]);
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Modal State
  const [showModal, setShowModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    title: 'Select Your Roles',
    description: 'Click any button below to receive or remove roles.',
    channel_id: '',
    embed_color: '#5865F2',
    image_url: '',
  });

  const [roleOptions, setRoleOptions] = useState([
    { role_id: '', label: '', emoji: '🎭', color: 'primary' },
  ]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [menusRes, chRes, roRes] = await Promise.all([
        api.get(`/guilds/${guildId}/self-roles`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/roles`),
      ]);
      setMenus(menusRes.data.menus || []);
      setChannels(chRes.data.channels || []);
      setRoles(roRes.data.roles || []);
      setError('');
    } catch (err) {
      console.error('Failed to fetch self roles', err);
      setError(err.response?.data?.error || 'Failed to fetch self roles');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const handleAddRoleOption = () => {
    if (roleOptions.length < 25) {
      setRoleOptions([...roleOptions, { role_id: '', label: '', emoji: '🎭', color: 'primary' }]);
    }
  };

  const handleRemoveRoleOption = (index) => {
    if (roleOptions.length > 1) {
      setRoleOptions(roleOptions.filter((_, i) => i !== index));
    }
  };

  const handleRoleOptionChange = (field, value, index) => {
    const next = [...roleOptions];
    next[index][field] = value;
    // Auto-fill label if empty and role changed
    if (field === 'role_id' && !next[index].label) {
      const found = roles.find(r => r.id === value);
      if (found) next[index].label = found.name;
    }
    setRoleOptions(next);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    const validOptions = roleOptions.filter(o => o.role_id);
    if (!formData.channel_id || validOptions.length === 0) {
      setError('Target channel and at least one role are required.');
      return;
    }
    setSubmitting(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/self-roles`, {
        ...formData,
        options: validOptions,
      });
      setSuccess('🎭 Self-Role panel created and posted to Discord!');
      setShowModal(false);
      setFormData({
        title: 'Select Your Roles',
        description: 'Click any button below to receive or remove roles.',
        channel_id: '',
        embed_color: '#5865F2',
        image_url: '',
      });
      setRoleOptions([{ role_id: '', label: '', emoji: '🎭', color: 'primary' }]);
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create self role menu');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (messageId) => {
    if (!window.confirm('Delete this self-role menu? The message will remain in Discord but interactive buttons will be unlinked.')) return;
    try {
      await api.delete(`/guilds/${guildId}/self-roles/${messageId}`);
      setSuccess('Self-role panel removed.');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete self role menu');
    }
  };

  const channelSelectOptions = channels.map(c => ({ value: c.id, label: `#${c.name}` }));
  const roleSelectOptions = roles.map(r => ({ value: r.id, label: `@${r.name}` }));

  return (
    <div className="feature-page">
      <div className="feature-header">
        <div>
          <h1 className="feature-title">🎭 Self-Assignable Roles</h1>
          <p className="feature-desc">Interactive Discord panels with buttons or select menus allowing members to claim roles.</p>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + Create Role Menu
        </button>
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

      {menus.length === 0 ? (
        <div className="dashboard-card" style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>🎭</div>
          <div>No self-role panels configured. Click &ldquo;+ Create Role Menu&rdquo; to build your first menu!</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '20px' }}>
          {menus.map(menu => {
            const ch = channels.find(c => c.id === menu.channel_id);
            return (
              <div key={menu.message_id} className="dashboard-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <h4 style={{ margin: 0, fontSize: '18px', color: 'var(--text-main)' }}>{menu.title}</h4>
                    <span className="badge badge-primary">#{ch ? ch.name : menu.channel_id}</span>
                  </div>

                  <p style={{ fontSize: '13px', color: 'var(--text-muted)', margin: '0 0 16px', lineHeight: 1.4 }}>
                    {menu.description}
                  </p>

                  <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '12px' }}>
                    <div style={{ fontSize: '12px', fontWeight: '700', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
                      Roles Included ({menu.options?.length || 0})
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {menu.options?.map(opt => {
                        const r = roles.find(ro => ro.id === opt.role_id);
                        return (
                          <span
                            key={opt.id}
                            style={{
                              background: 'rgba(255,255,255,0.06)',
                              padding: '4px 10px',
                              borderRadius: '6px',
                              fontSize: '12px',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '6px',
                            }}
                          >
                            <span>{opt.emoji || '🔹'}</span>
                            <strong>{opt.label || (r ? r.name : opt.role_id)}</strong>
                          </span>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '14px' }}>
                  <button className="btn-danger" onClick={() => handleDelete(menu.message_id)} style={{ padding: '6px 14px', fontSize: '12px' }}>
                    Delete Menu
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '600px', maxHeight: '90vh', overflowY: 'auto' }}>
            <h3 style={{ marginTop: 0 }}>Create Self-Role Menu</h3>
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group">
                <label className="form-label">Menu Title</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.title}
                  onChange={e => setFormData({ ...formData, title: e.target.value })}
                  placeholder="e.g. Notification & Region Roles"
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Menu Description</label>
                <textarea
                  className="form-input"
                  rows={2}
                  value={formData.description}
                  onChange={e => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Instructions for members..."
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Destination Discord Channel</label>
                <Select
                  value={formData.channel_id}
                  onChange={val => setFormData({ ...formData, channel_id: val })}
                  options={channelSelectOptions}
                  placeholder="Select channel where menu will be posted..."
                  searchable
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">Accent Color</label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input
                      type="color"
                      value={formData.embed_color}
                      onChange={e => setFormData({ ...formData, embed_color: e.target.value })}
                      style={{ width: '40px', height: '38px', borderRadius: '6px', border: 'none', cursor: 'pointer' }}
                    />
                    <input
                      type="text"
                      className="form-input"
                      value={formData.embed_color}
                      onChange={e => setFormData({ ...formData, embed_color: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Banner Image URL (Optional)</label>
                  <input
                    type="url"
                    className="form-input"
                    value={formData.image_url}
                    onChange={e => setFormData({ ...formData, image_url: e.target.value })}
                    placeholder="https://..."
                  />
                </div>
              </div>

              {/* Role Options */}
              <div className="form-group">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <label className="form-label" style={{ margin: 0 }}>Roles to Assign</label>
                  {roleOptions.length < 25 && (
                    <button type="button" onClick={handleAddRoleOption} style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>
                      + Add Another Role
                    </button>
                  )}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {roleOptions.map((opt, i) => (
                    <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1fr 1fr auto', gap: '8px', alignItems: 'center' }}>
                      <Select
                        value={opt.role_id}
                        onChange={val => handleRoleOptionChange('role_id', val, i)}
                        options={roleSelectOptions}
                        placeholder="Select Role..."
                        searchable
                      />
                      <input
                        type="text"
                        className="form-input"
                        placeholder="Button label..."
                        value={opt.label}
                        onChange={e => handleRoleOptionChange('label', e.target.value, i)}
                      />
                      <input
                        type="text"
                        className="form-input"
                        placeholder="Emoji"
                        value={opt.emoji}
                        onChange={e => handleRoleOptionChange('emoji', e.target.value, i)}
                        style={{ textAlign: 'center' }}
                      />
                      <select
                        className="form-input"
                        value={opt.color}
                        onChange={e => handleRoleOptionChange('color', e.target.value, i)}
                      >
                        <option value="primary">Blurple</option>
                        <option value="secondary">Grey</option>
                        <option value="success">Green</option>
                        <option value="danger">Red</option>
                      </select>
                      {roleOptions.length > 1 && (
                        <button type="button" className="btn-secondary" onClick={() => handleRemoveRoleOption(i)} style={{ padding: '8px 12px' }}>
                          ✕
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Publishing...' : '🎭 Publish Menu to Discord'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default SelfRoles;
