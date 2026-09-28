import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { SitePage } from '../components/SiteLayout';
import { Loader } from '../components/Loader';
import '../admin-panel.css';
import {
  ShieldAlert, Ban, Server, User, Trash2, LogOut, Plus, ArrowLeft, ShieldCheck,
} from 'lucide-react';

function timeAgo(ts) {
  if (!ts) return '';
  const s = Math.floor(Date.now() / 1000) - ts;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function BlacklistManagement({ user }) {
  const [checking, setChecking] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [tab, setTab] = useState('servers'); // servers | members

  const [servers, setServers] = useState(null);
  const [members, setMembers] = useState(null);
  const [error, setError] = useState('');

  const [newId, setNewId] = useState('');
  const [newReason, setNewReason] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/admin/whoami')
      .then(res => setIsAdmin(!!res.data?.is_admin))
      .catch(() => setIsAdmin(false))
      .finally(() => setChecking(false));
  }, []);

  const loadServers = () => api.get('/blacklist/servers').then(r => setServers(r.data.servers || [])).catch(e => setError(e.response?.data?.error || 'Failed to load servers.'));
  const loadMembers = () => api.get('/blacklist/members').then(r => setMembers(r.data.members || [])).catch(e => setError(e.response?.data?.error || 'Failed to load members.'));

  useEffect(() => {
    if (!isAdmin) return;
    loadServers();
    loadMembers();
  }, [isAdmin]);

  const resetForm = () => { setNewId(''); setNewReason(''); };

  const handleAdd = async (e) => {
    e.preventDefault();
    setError('');
    if (!/^\d+$/.test(newId.trim())) {
      setError(`Please enter a valid ${tab === 'servers' ? 'server' : 'user'} ID (numbers only).`);
      return;
    }
    setSaving(true);
    try {
      if (tab === 'servers') {
        await api.post('/blacklist/servers', { guild_id: newId.trim(), reason: newReason.trim() });
        await loadServers();
      } else {
        await api.post('/blacklist/members', { user_id: newId.trim(), reason: newReason.trim() });
        await loadMembers();
      }
      resetForm();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to blacklist.');
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async (id) => {
    setError('');
    try {
      if (tab === 'servers') {
        await api.delete(`/blacklist/servers/${id}`);
        setServers(prev => (prev || []).filter(s => String(s.guild_id) !== String(id)));
      } else {
        await api.delete(`/blacklist/members/${id}`);
        setMembers(prev => (prev || []).filter(m => String(m.user_id) !== String(id)));
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to remove.');
    }
  };

  const handleLeave = async (guildId) => {
    setError('');
    try {
      await api.post(`/blacklist/servers/${guildId}/leave`, { reason: 'Blacklisted + removed via dashboard' });
      await loadServers();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to leave that server.');
    }
  };

  if (checking) {
    return <Loader label="Checking access…" />;
  }

  if (!isAdmin) {
    return (
      <SitePage user={user}>
        <section className="site-section" style={{ paddingTop: 90, textAlign: 'center' }}>
          <div className="container" style={{ maxWidth: 460 }}>
            <ShieldAlert size={40} color="var(--danger)" style={{ marginBottom: 14 }} />
            <h2 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8 }}>Access Denied</h2>
            <p style={{ color: 'var(--text-sub)' }}>
              {user ? "This page is restricted to the bot's owner/admins." : 'Please sign in with an authorized account to view this page.'}
            </p>
          </div>
        </section>
      </SitePage>
    );
  }

  const rows = tab === 'servers' ? servers : members;

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64 }}>
        <div className="container admin-shell">
          <div className="admin-head">
            <div className="site-section-head" style={{ marginBottom: 0 }}>
              <Link to="/admin" className="site-btn site-btn-ghost" style={{ marginBottom: 14, display: 'inline-flex' }}>
                <ArrowLeft size={14} /> <span>Back to Admin Panel</span>
              </Link>
              <div className="site-eyebrow">Bot staff only</div>
              <h2>Blacklist Management</h2>
            </div>
          </div>

          <div className="site-cmd-tabs" style={{ justifyContent: 'flex-start', marginBottom: 20 }}>
            <button type="button" className={`site-cmd-tab ${tab === 'servers' ? 'active' : ''}`} onClick={() => { setTab('servers'); resetForm(); setError(''); }}>
              <Server size={13} style={{ marginRight: 6, verticalAlign: -2 }} /> Servers ({servers === null ? '—' : servers.length})
            </button>
            <button type="button" className={`site-cmd-tab ${tab === 'members' ? 'active' : ''}`} onClick={() => { setTab('members'); resetForm(); setError(''); }}>
              <User size={13} style={{ marginRight: 6, verticalAlign: -2 }} /> Members ({members === null ? '—' : members.length})
            </button>
          </div>

          <div className="site-card" style={{ marginBottom: 20 }}>
            <form onSubmit={handleAdd} style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div className="site-field" style={{ margin: 0, flex: '1 1 200px' }}>
                <label>{tab === 'servers' ? 'Server ID' : 'User ID'}</label>
                <input type="text" value={newId} onChange={e => setNewId(e.target.value)} placeholder={tab === 'servers' ? '123456789012345678' : '123456789012345678'} />
              </div>
              <div className="site-field" style={{ margin: 0, flex: '2 1 260px' }}>
                <label>Reason (optional)</label>
                <input type="text" value={newReason} onChange={e => setNewReason(e.target.value)} placeholder="Why is this being blacklisted?" maxLength={300} />
              </div>
              <button type="submit" className="site-btn site-btn-primary" disabled={saving} style={{ height: 42 }}>
                <Ban size={15} /> <span>{saving ? 'Blacklisting…' : `Blacklist ${tab === 'servers' ? 'Server' : 'Member'}`}</span>
              </button>
            </form>
            {error && <div className="site-alert site-alert-error" style={{ marginTop: 14 }}>{error}</div>}
          </div>

          <div className="site-card">
            {rows === null ? (
              <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
            ) : rows.length === 0 ? (
              <div className="admin-empty">
                <ShieldCheck size={20} style={{ marginBottom: 8, opacity: 0.6 }} />
                <div>Nothing blacklisted — all clear.</div>
              </div>
            ) : (
              <div className="admin-ticket-list">
                {tab === 'servers' ? rows.map(s => (
                  <div key={s.guild_id} className="admin-ticket-row" style={{ alignItems: 'center' }}>
                    <span className="admin-ticket-chip">{s.bot_present ? 'Present' : 'Not in server'}</span>
                    <div className="admin-ticket-body">
                      <div className="admin-ticket-subject">{s.guild_name || 'Unknown server'} <span style={{ color: 'var(--text-faint)', fontWeight: 500 }}>({s.guild_id})</span></div>
                      <div className="admin-ticket-meta">
                        <span>By {s.blacklisted_by ? `<@${s.blacklisted_by}>`.replace(/[<>@]/g, '') : 'unknown'}</span>
                        <span>·</span>
                        <span>{timeAgo(s.blacklisted_at)}</span>
                        {s.reason && (<><span>·</span><span>{s.reason}</span></>)}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {s.bot_present && (
                        <button type="button" onClick={() => handleLeave(s.guild_id)} className="site-btn site-btn-ghost" style={{ padding: '6px 10px' }} title="Leave server">
                          <LogOut size={14} />
                        </button>
                      )}
                      <button type="button" onClick={() => handleRemove(s.guild_id)} className="site-btn site-btn-ghost" style={{ padding: '6px 10px' }} title="Remove from blacklist">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                )) : rows.map(m => (
                  <div key={m.user_id} className="admin-ticket-row" style={{ alignItems: 'center' }}>
                    <span className="admin-ticket-chip">User</span>
                    <div className="admin-ticket-body">
                      <div className="admin-ticket-subject">{m.username || 'Unknown user'} <span style={{ color: 'var(--text-faint)', fontWeight: 500 }}>({m.user_id})</span></div>
                      <div className="admin-ticket-meta">
                        <span>By {m.blacklisted_by || 'unknown'}</span>
                        <span>·</span>
                        <span>{timeAgo(m.blacklisted_at)}</span>
                        {m.reason && (<><span>·</span><span>{m.reason}</span></>)}
                      </div>
                    </div>
                    <button type="button" onClick={() => handleRemove(m.user_id)} className="site-btn site-btn-ghost" style={{ padding: '6px 10px' }} title="Remove from blacklist">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </SitePage>
  );
}

export default BlacklistManagement;
