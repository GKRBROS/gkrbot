import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync, syncParams } from '../../sync';

function Moderation() {
  const { guildId } = useParams();
  const [roles, setRoles] = useState([]);
  const [staffRoleIds, setStaffRoleIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [selectedRole, setSelectedRole] = useState('');
  const [syncOpen, setSyncOpen] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [modRes, rolesRes] = await Promise.all([
        api.get(`/guilds/${guildId}/moderation`),
        api.get(`/guilds/${guildId}/roles`),
      ]);
      setStaffRoleIds(modRes.data.staff_roles || []);
      const rList = rolesRes.data.roles || [];
      setRoles(rList);
      if (rList.length > 0 && !selectedRole) {
        setSelectedRole(rList[0].id);
      }
    } catch (err) {
      console.error('Failed to load moderation settings', err);
    }
    setLoading(false);
  }, [guildId, selectedRole]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddRole = async (e) => {
    e.preventDefault();
    if (!selectedRole) return;
    setError('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/moderation/staff-roles`, withSync({ role_id: selectedRole }));
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add staff role');
    }
    setSubmitting(false);
  };

  const handleRemoveRole = async (roleId) => {
    try {
      await api.delete(`/guilds/${guildId}/moderation/staff-roles/${roleId}`, { params: syncParams() });
      setStaffRoleIds(prev => prev.filter(id => id !== roleId));
    } catch (err) {
      console.error('Failed to remove staff role', err);
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '260px' }}></div>
      </div>
    );
  }

  const getRole = (id) => {
    return roles.find(r => r.id === id) || { id, name: `Role ${id}`, color: '#99aab5' };
  };

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="page-header flex justify-between items-center" style={{ flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 className="page-title">
            <span>⚖️</span> Moderation & Staff Roles
          </h2>
          <p className="page-subtitle">
            Manage moderator permissions, staff roles, and administrative bot capabilities.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSyncOpen(true)}
          className="btn"
          style={{
            background: 'rgba(88,101,242,0.15)',
            border: '1px solid var(--primary)',
            color: 'var(--text-main)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <span>🔄</span> Sync to Other Servers
        </button>
      </div>

      {error && (
        <div style={{
          padding: '12px 16px',
          borderRadius: '8px',
          marginBottom: '20px',
          background: 'rgba(239, 68, 68, 0.15)',
          border: '1px solid var(--danger)',
          color: 'var(--danger)',
          fontSize: '14px'
        }}>
          {error}
        </div>
      )}

      {/* Staff Roles Card */}
      <div className="card glass-panel" style={{ marginBottom: '28px' }}>
        <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>
          🛡️ Designated Staff Roles
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '20px' }}>
          Members holding any of these roles can use moderation commands (/mute, /unmute, /warn, /say) without needing full Discord Administrator permission.
        </p>

        {/* Add Role Form */}
        <form onSubmit={handleAddRole} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '24px' }}>
          <select
            className="form-control"
            style={{ maxWidth: '320px' }}
            value={selectedRole}
            onChange={e => setSelectedRole(e.target.value)}
          >
            {roles.map(r => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
          <button
            type="submit"
            disabled={submitting || !selectedRole}
            className="btn btn-primary"
          >
            {submitting ? 'Adding...' : '+ Add Staff Role'}
          </button>
        </form>

        {/* Active Staff Roles */}
        <div>
          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-sub)', marginBottom: '10px' }}>
            Current Staff Roles ({staffRoleIds.length})
          </div>

          {staffRoleIds.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
              No custom staff roles designated yet. Only users with Administrator permissions can moderate.
            </div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              {staffRoleIds.map(id => {
                const role = getRole(id);
                return (
                  <div
                    key={id}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                      background: 'rgba(255,255,255,0.06)',
                      border: `1px solid ${role.color}`,
                      borderRadius: '8px',
                      padding: '6px 12px',
                    }}
                  >
                    <span style={{
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      background: role.color
                    }} />
                    <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-main)' }}>
                      {role.name}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleRemoveRole(id)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--danger)',
                        cursor: 'pointer',
                        fontSize: '14px',
                        marginLeft: '4px',
                        padding: '0 4px'
                      }}
                      title="Remove Role"
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Moderation Toolkit Reference */}
      <div className="card glass-panel">
        <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
          📖 Moderation Commands
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '14px' }}>
          {[
            { cmd: '/mute <user> <duration> [reason]', desc: 'Timeouts a member with rich infraction logging.' },
            { cmd: '/unmute <user> [reason]', desc: 'Lifts a timeout early from a member.' },
            { cmd: '/mutelist', desc: 'Displays all currently muted server members.' },
            { cmd: '/warn <user> <reason>', desc: 'Issues an official warning and triggers punishment ladder.' },
            { cmd: '/warnings <user>', desc: 'Reviews warning history and active infractions.' },
            { cmd: '/saye <message> /sayt', desc: 'Broadcasts official announcements as embeds or plain text.' },
          ].map(c => (
            <div key={c.cmd} style={{
              background: 'rgba(0,0,0,0.2)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '12px 14px'
            }}>
              <code style={{ color: 'var(--accent)', fontWeight: 600, fontSize: '13px', display: 'block', marginBottom: '4px' }}>
                {c.cmd}
              </code>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{c.desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Sync Modal */}
      <SyncModal
        isOpen={syncOpen}
        onClose={() => setSyncOpen(false)}
        currentGuildId={guildId}
        moduleName="moderation"
        moduleLabel="Moderation Staff Roles"
      />
    </div>
  );
}

export default Moderation;
