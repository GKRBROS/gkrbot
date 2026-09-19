import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Terminal,
  Plus,
  Trash2,
  Edit2,
  Search,
  CheckCircle2,
  AlertCircle,
  Zap
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function CustomCommands() {
  const { guildId } = useParams();
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [editingName, setEditingName] = useState(null);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState({ name: '', response: '' });

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/custom-commands`);
      setCommands(res.data.commands || []);
    } catch (err) {
      console.error('Failed to load custom commands', err);
      setError(err.response?.data?.error || 'Failed to load custom commands');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      if (editingName) {
        await api.put(`/guilds/${guildId}/custom-commands/${editingName}`, { response: form.response });
        setSuccess(`Command !${editingName} updated successfully!`);
      } else {
        await api.post(`/guilds/${guildId}/custom-commands`, form);
        setSuccess(`Command !${form.name} created successfully!`);
      }
      setForm({ name: '', response: '' });
      setEditingName(null);
      setTimeout(() => setSuccess(''), 3000);
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save command');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (cmd) => {
    setEditingName(cmd.name);
    setForm({ name: cmd.name, response: cmd.response });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (name) => {
    if (!window.confirm(`Delete command "!${name}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/guilds/${guildId}/custom-commands/${name}`);
      setSuccess(`Command !${name} deleted.`);
      setTimeout(() => setSuccess(''), 2500);
      await fetchData();
    } catch (err) {
      console.error('Failed to delete command', err);
      setError(err.response?.data?.error || 'Failed to delete command');
    }
  };

  const cancelEdit = () => {
    setEditingName(null);
    setForm({ name: '', response: '' });
  };

  const filtered = commands.filter(c =>
    c.name.toLowerCase().includes(search.trim().toLowerCase()) ||
    c.response.toLowerCase().includes(search.trim().toLowerCase())
  );

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
        icon={Terminal}
        title="Custom Chat Commands"
        subtitle={
          <span>
            Create text commands triggered with <Badge variant="primary" size="sm" style={{ display: 'inline-flex' }}>!name</Badge> in chat.
            Use <code style={{ color: 'var(--primary)', fontSize: '12px' }}>{'{user}'}</code> <code style={{ color: 'var(--primary)', fontSize: '12px' }}>{'{username}'}</code> <code style={{ color: 'var(--primary)', fontSize: '12px' }}>{'{server}'}</code> <code style={{ color: 'var(--primary)', fontSize: '12px' }}>{'{membercount}'}</code> as variables.
          </span>
        }
      />

      {error && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderRadius: 'var(--radius-md)', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.25)', color: '#f87171', fontSize: '13.5px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><AlertCircle size={17} /><span>{error}</span></div>
          <button onClick={() => setError('')} style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '16px' }}>✕</button>
        </div>
      )}

      {success && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderRadius: 'var(--radius-md)', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.25)', color: '#34d399', fontSize: '13.5px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><CheckCircle2 size={17} /><span>{success}</span></div>
          <button onClick={() => setSuccess('')} style={{ background: 'transparent', border: 'none', color: '#34d399', cursor: 'pointer', fontSize: '16px' }}>✕</button>
        </div>
      )}

      {/* Create / Edit form */}
      <Card>
        <CardHeader>
          <CardTitle>{editingName ? `Editing Command: !${editingName}` : 'Create New Command'}</CardTitle>
          <CardDescription>
            {editingName
              ? 'Update the response text for this command. The command name cannot be changed.'
              : 'Commands are triggered when a member types !name in any server channel.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Command Name
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '18px', fontWeight: 800, color: 'var(--primary)', fontFamily: 'monospace', flexShrink: 0 }}>!</span>
                  <input
                    type="text"
                    className="form-input"
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value.replace(/\s/g, '').toLowerCase() })}
                    placeholder="e.g. rules, info, discord"
                    disabled={!!editingName}
                    required
                    maxLength={30}
                    style={{ fontFamily: 'monospace', flex: 1 }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Response Message
                </label>
                <textarea
                  className="form-input"
                  rows={3}
                  value={form.response}
                  onChange={e => setForm({ ...form, response: e.target.value })}
                  placeholder="Welcome to {server}, {user}! Our Discord is growing — {membercount} members strong!"
                  required
                  maxLength={2000}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              {editingName && (
                <Button type="button" variant="outline" onClick={cancelEdit}>
                  Cancel
                </Button>
              )}
              <Button type="submit" variant="primary" icon={editingName ? Edit2 : Plus} loading={submitting}>
                {editingName ? 'Save Changes' : 'Create Command'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Commands list */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>Command Library</h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>All custom commands available on this server.</p>
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            {commands.length > 3 && (
              <div style={{ position: 'relative' }}>
                <Search size={15} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Search commands..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  style={{ paddingLeft: '32px', width: '200px' }}
                />
              </div>
            )}
            <Badge variant="primary" size="sm">{commands.length} Commands</Badge>
          </div>
        </div>

        {commands.length === 0 ? (
          <EmptyState icon={Terminal} title="No Custom Commands" description="Build your first command above — members trigger it with !commandname in chat." />
        ) : filtered.length === 0 ? (
          <EmptyState icon={Search} title="No Matches Found" description={`No commands match "${search}".`} />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '14px' }}>
            {filtered.map(cmd => (
              <Card key={cmd.id || cmd.name} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <CardContent style={{ padding: '18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                    <code style={{ fontFamily: 'monospace', fontSize: '14px', fontWeight: 700, color: 'var(--primary)', background: 'rgba(88,101,242,0.1)', padding: '3px 8px', borderRadius: '6px' }}>
                      !{cmd.name}
                    </code>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <Button variant="ghost" size="sm" icon={Edit2} onClick={() => handleEdit(cmd)} />
                      <Button variant="ghost" size="sm" icon={Trash2} onClick={() => handleDelete(cmd.name)} style={{ color: '#f87171' }} />
                    </div>
                  </div>
                  <p style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: '1.55', margin: 0, display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', overflow: 'hidden', whiteSpace: 'pre-wrap' }}>
                    {cmd.response}
                  </p>
                  {(cmd.uses !== undefined) && (
                    <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px solid var(--border)', fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Zap size={12} />
                      Used {cmd.uses || 0} time{cmd.uses === 1 ? '' : 's'}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default CustomCommands;
