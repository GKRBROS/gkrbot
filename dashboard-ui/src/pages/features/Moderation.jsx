import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  ShieldAlert,
  Users,
  Share2,
  Plus,
  Trash2,
  Terminal,
  CheckCircle2,
  AlertCircle,
  BookOpen,
  Shield,
  Tag
} from 'lucide-react';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync, syncParams } from '../../sync';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

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
      setError(err.response?.data?.error || 'Failed to load moderation settings');
    } finally {
      setLoading(false);
    }
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
      setError(err.response?.data?.error || 'Failed to designate staff role');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemoveRole = async (roleId) => {
    try {
      await api.delete(`/guilds/${guildId}/moderation/staff-roles/${roleId}`, { params: syncParams() });
      setStaffRoleIds(prev => prev.filter(id => id !== roleId));
    } catch (err) {
      console.error('Failed to remove staff role', err);
      setError(err.response?.data?.error || 'Failed to remove staff role');
    }
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="240px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  const getRole = (id) => {
    return roles.find(r => String(r.id) === String(id)) || { id, name: `Role ${id}`, color: '#99aab5' };
  };

  const roleOptions = roles.map(r => ({
    value: r.id,
    label: `@${r.name}`
  }));

  const commandsList = [
    { cmd: '/mute <user> <duration> [reason]', desc: 'Timeouts a member with rich infraction logging.' },
    { cmd: '/unmute <user> [reason]', desc: 'Lifts an active timeout from a server member.' },
    { cmd: '/mutelist', desc: 'Lists all currently timed-out or muted server members.' },
    { cmd: '/warn <user> <reason>', desc: 'Issues an official warning and advances the punishment ladder.' },
    { cmd: '/warnings <user>', desc: 'Shows complete warning history and active disciplinary records.' },
    { cmd: '/saye <message> /sayt', desc: 'Broadcasts official announcements as rich embeds or plaintext.' },
  ];

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={ShieldAlert}
        title="Moderation & Staff Roles"
        subtitle="Authorize specific moderator roles to execute bot discipline commands without granting full server admin rights."
        actions={
          <Button
            variant="outline"
            size="sm"
            icon={Share2}
            onClick={() => setSyncOpen(true)}
          >
            Sync to Servers
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

      {/* Designated Staff Roles Card */}
      <Card>
        <CardHeader>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <CardTitle>Designated Staff Roles</CardTitle>
              <CardDescription>
                Members holding any of these roles gain permission to use bot moderation commands (/warn, /mute, /unmute).
              </CardDescription>
            </div>
            <Badge variant="primary" size="sm">{staffRoleIds.length} Active Roles</Badge>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Add Staff Role Form */}
          <form onSubmit={handleAddRole} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ flex: '1', minWidth: '260px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Select Server Role
              </label>
              <Select
                value={selectedRole}
                onChange={setSelectedRole}
                options={roleOptions}
                placeholder="Choose a role to grant staff access..."
                searchable
              />
            </div>
            <Button
              type="submit"
              variant="primary"
              icon={Plus}
              loading={submitting}
              disabled={!selectedRole}
            >
              Add Staff Role
            </Button>
          </form>

          {/* Active Staff Roles Badges */}
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
            <span style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Assigned Moderator Roles
            </span>

            {staffRoleIds.length === 0 ? (
              <div style={{
                padding: '16px',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-muted)',
                fontSize: '13px'
              }}>
                No specific roles assigned yet. Currently only server members with native Discord Administrator permissions can invoke moderation commands.
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
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)',
                        padding: '7px 12px'
                      }}
                    >
                      <span
                        style={{
                          width: '10px',
                          height: '10px',
                          borderRadius: '50%',
                          background: role.color && role.color !== '#000000' ? role.color : 'var(--primary)'
                        }}
                      />
                      <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-main)' }}>
                        @{role.name}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRemoveRole(id)}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#f87171',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          padding: '2px',
                          marginLeft: '2px'
                        }}
                        title="Remove staff role"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Moderation Command Reference Card */}
      <Card>
        <CardHeader>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Terminal size={19} color="var(--primary)" />
            <div>
              <CardTitle>Moderation Command Reference</CardTitle>
              <CardDescription>Slash commands accessible to members with designated staff roles.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '14px' }}>
            {commandsList.map(c => (
              <div
                key={c.cmd}
                style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '14px 16px'
                }}
              >
                <code style={{
                  color: 'var(--primary)',
                  fontWeight: 600,
                  fontSize: '13px',
                  display: 'block',
                  marginBottom: '4px',
                  fontFamily: 'monospace'
                }}>
                  {c.cmd}
                </code>
                <span style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                  {c.desc}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Cross Server Sync Modal */}
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
