import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Tags,
  Plus,
  Trash2,
  Palette,
  Hash,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  Send
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import Modal from '../../components/Modal';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

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
    title: 'Select Your Community Roles',
    description: 'Click any button below to receive or remove roles from your profile.',
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
    if (field === 'role_id' && !next[index].label) {
      const found = roles.find(r => String(r.id) === String(value));
      if (found) next[index].label = found.name;
    }
    setRoleOptions(next);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    const validOptions = roleOptions.filter(o => o.role_id);
    if (!formData.channel_id || validOptions.length === 0) {
      setError('Target destination channel and at least one role must be configured.');
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
      setSuccess('Self-Role panel deployed to Discord successfully!');
      setShowModal(false);
      setFormData({
        title: 'Select Your Community Roles',
        description: 'Click any button below to receive or remove roles from your profile.',
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
    if (!window.confirm('Delete this self-role menu? The interactive button bindings will be unlinked.')) return;
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

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="240px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Tags}
        title="Self-Assignable Roles"
        subtitle="Deploy interactive Discord button panels allowing server members to claim notification, cosmetic, or game roles."
        actions={
          <Button
            variant="primary"
            size="sm"
            icon={Plus}
            onClick={() => setShowModal(true)}
          >
            Create Role Menu
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

      {/* Role Menus List */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Active Role Panels
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Panels posted to Discord channels currently listening for member clicks.
            </p>
          </div>
          <Badge variant="primary" size="sm">{menus.length} Menus</Badge>
        </div>

        {menus.length === 0 ? (
          <EmptyState
            icon={Tags}
            title="No Role Panels Configured"
            description="Create your first interactive role menu so members can assign themselves roles like Announcement, Region, or Platform."
            actionLabel="Create Role Menu"
            onAction={() => setShowModal(true)}
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
            {menus.map(menu => {
              const ch = channels.find(c => String(c.id) === String(menu.channel_id));
              return (
                <Card key={menu.message_id} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <CardContent style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                      <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: 'var(--text-main)' }}>
                        {menu.title}
                      </h4>
                      <Badge variant="primary" size="sm">
                        #{ch ? ch.name : menu.channel_id}
                      </Badge>
                    </div>

                    <p style={{ fontSize: '13px', color: 'var(--text-muted)', margin: '0 0 16px', lineHeight: 1.45 }}>
                      {menu.description}
                    </p>

                    <div style={{ borderTop: '1px solid var(--border)', paddingTop: '12px' }}>
                      <div style={{ fontSize: '11.5px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
                        Roles Included ({menu.options?.length || 0})
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {menu.options?.map(opt => {
                          const r = roles.find(ro => String(ro.id) === String(opt.role_id));
                          return (
                            <span
                              key={opt.id || opt.role_id}
                              style={{
                                background: 'var(--bg-surface)',
                                border: '1px solid var(--border)',
                                padding: '4px 8px',
                                borderRadius: 'var(--radius-sm)',
                                fontSize: '12px',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '6px'
                              }}
                            >
                              <span>{opt.emoji || '🎭'}</span>
                              <span style={{ fontWeight: 500, color: 'var(--text-main)' }}>
                                {opt.label || (r ? r.name : opt.role_id)}
                              </span>
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  </CardContent>

                  <div style={{
                    padding: '12px 20px',
                    borderTop: '1px solid var(--border)',
                    background: 'rgba(255, 255, 255, 0.01)',
                    display: 'flex',
                    justifyContent: 'flex-end'
                  }}>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={Trash2}
                      onClick={() => handleDelete(menu.message_id)}
                    >
                      Delete Panel
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Creation Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Create Self-Role Menu Panel"
        maxWidth="620px"
      >
        <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Panel Embed Title
            </label>
            <input
              type="text"
              className="form-input"
              value={formData.title}
              onChange={e => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g. Select Your Community Roles"
              required
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Panel Description
            </label>
            <textarea
              className="form-input"
              rows={2}
              value={formData.description}
              onChange={e => setFormData({ ...formData, description: e.target.value })}
              placeholder="Instructions for members..."
              required
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Target Discord Channel
            </label>
            <Select
              value={formData.channel_id}
              onChange={val => setFormData({ ...formData, channel_id: val })}
              options={channelSelectOptions}
              placeholder="Select channel where panel will be posted..."
              searchable
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Accent Color
              </label>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input
                  type="color"
                  value={formData.embed_color}
                  onChange={e => setFormData({ ...formData, embed_color: e.target.value })}
                  style={{
                    width: '40px',
                    height: '38px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border)',
                    cursor: 'pointer',
                    background: 'none'
                  }}
                />
                <input
                  type="text"
                  className="form-input"
                  value={formData.embed_color}
                  onChange={e => setFormData({ ...formData, embed_color: e.target.value })}
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Banner Image URL (Optional)
              </label>
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
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                Roles Included ({roleOptions.length}/25)
              </label>
              {roleOptions.length < 25 && (
                <button
                  type="button"
                  onClick={handleAddRoleOption}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--primary)',
                    fontSize: '12.5px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    padding: 0
                  }}
                >
                  + Add Role Option
                </button>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '240px', overflowY: 'auto' }}>
              {roleOptions.map((opt, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(140px, 1.8fr) minmax(120px, 1.4fr) 60px 90px auto', gap: '8px', alignItems: 'center' }}>
                  <Select
                    value={opt.role_id}
                    onChange={val => handleRoleOptionChange('role_id', val, i)}
                    options={roleSelectOptions}
                    placeholder="Role..."
                    searchable
                  />
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Button Label"
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
                    <button
                      type="button"
                      onClick={() => handleRemoveRoleOption(i)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#f87171',
                        cursor: 'pointer',
                        padding: '6px'
                      }}
                      title="Remove option"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
            <Button type="button" variant="outline" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={submitting}>
              Deploy Self-Role Panel
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default SelfRoles;
