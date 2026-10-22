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
  Tag,
  Gavel,
  UserX,
  UserCheck,
  RefreshCw
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
  const [successMsg, setSuccessMsg] = useState('');
  const [selectedRole, setSelectedRole] = useState('');
  const [syncOpen, setSyncOpen] = useState(false);

  // Bans management state
  const [bans, setBans] = useState([]);
  const [bansLoading, setBansLoading] = useState(false);
  const [banUserId, setBanUserId] = useState('');
  const [banReason, setBanReason] = useState('');
  const [banning, setBanning] = useState(false);
  const [unbanningId, setUnbanningId] = useState('');
  const [unbanAllLoading, setUnbanAllLoading] = useState(false);

  const fetchBans = useCallback(async () => {
    setBansLoading(true);
    try {
      const res = await api.get(`/guilds/${guildId}/moderation/bans`);
      setBans(res.data.bans || []);
    } catch (err) {
      console.error('Failed to load server bans', err);
    } finally {
      setBansLoading(false);
    }
  }, [guildId]);

  const fetchData = useCallback(async () => {
    try {
      const [modRes, rolesRes] = await Promise.allSettled([
        api.get(`/guilds/${guildId}/moderation`),
        api.get(`/guilds/${guildId}/roles`),
      ]);
      if (modRes.status === 'fulfilled' && modRes.value.data?.staff_roles) {
        setStaffRoleIds(modRes.value.data.staff_roles || []);
      }
      if (rolesRes.status === 'fulfilled' && rolesRes.value.data?.roles) {
        const rList = rolesRes.value.data.roles || [];
        setRoles(rList);
        if (rList.length > 0 && !selectedRole) {
          setSelectedRole(rList[0].id);
        }
      }
      await fetchBans();
    } catch (err) {
      console.error('Failed to load moderation settings', err);
      setError(err.response?.data?.error || 'Failed to load moderation settings');
    } finally {
      setLoading(false);
    }
  }, [guildId, selectedRole, fetchBans]);

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

  const handleBanUser = async (e) => {
    if (e) e.preventDefault();
    if (!banUserId.trim()) return;
    setError('');
    setSuccessMsg('');
    setBanning(true);
    try {
      await api.post(`/guilds/${guildId}/moderation/ban`, {
        user_id: banUserId.trim(),
        reason: banReason.trim() || 'Banned via Web Dashboard',
      });
      setSuccessMsg(`Successfully banned user ${banUserId}`);
      setBanUserId('');
      setBanReason('');
      await fetchBans();
      setTimeout(() => setSuccessMsg(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to ban member');
    } finally {
      setBanning(false);
    }
  };

  const handleUnbanUser = async (userId) => {
    setError('');
    setSuccessMsg('');
    setUnbanningId(userId);
    try {
      await api.post(`/guilds/${guildId}/moderation/unban`, { user_id: userId });
      setSuccessMsg(`Successfully unbanned user ${userId}`);
      setBans(prev => prev.filter(b => b.user.id !== userId));
      setTimeout(() => setSuccessMsg(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to unban user');
    } finally {
      setUnbanningId('');
    }
  };

  const handleUnbanAll = async () => {
    if (!window.confirm('Are you ABSOLUTELY sure you want to UNBAN ALL members from this server? This action cannot be undone.')) {
      return;
    }
    setError('');
    setSuccessMsg('');
    setUnbanAllLoading(true);
    try {
      const res = await api.post(`/guilds/${guildId}/moderation/unbanall`);
      setSuccessMsg(`Mass unban complete! Unbanned ${res.data.count || 0} user(s).`);
      await fetchBans();
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to execute mass unban');
    } finally {
      setUnbanAllLoading(false);
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
    { cmd: '/mod ban <user> [reason]', desc: 'Bans a member with optional purge and security logging.' },
    { cmd: '/mod unban <user_id> [reason]', desc: 'Removes an active ban by Discord user ID.' },
    { cmd: '/mod unbanall', desc: 'Administrative mass unban across the entire server.' },
    { cmd: '/mod banlist', desc: 'Displays currently banned members and ban reasons.' },
    { cmd: '/mod kick <user> [reason]', desc: 'Kicks a member from the server.' },
    { cmd: '/mod timeout <user> <duration> [reason]', desc: 'Applies Discord communication timeout (mute).' },
    { cmd: '/mod untimeout <user>', desc: 'Removes timeout from a muted member.' },
    { cmd: '/warn <user> <reason>', desc: 'Issues an official warning and advances punishment ladder.' },
    { cmd: '/warnings <user>', desc: 'Shows complete warning history and active records.' },
  ];

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={ShieldAlert}
        title="Moderation & Server Discipline"
        subtitle="Authorize specific moderator roles, manage server bans, execute mass unbans, and manage disciplinary enforcement."
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

      {successMsg && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(34, 197, 94, 0.1)',
          border: '1px solid rgba(34, 197, 94, 0.25)',
          color: '#4ade80',
          fontSize: '13.5px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <CheckCircle2 size={17} />
            <span>{successMsg}</span>
          </div>
          <button
            onClick={() => setSuccessMsg('')}
            style={{ background: 'transparent', border: 'none', color: '#4ade80', cursor: 'pointer', fontSize: '16px' }}
          >
            ✕
          </button>
        </div>
      )}

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

      {/* Server Bans & Mass Unban Card */}
      <Card>
        <CardHeader>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Gavel size={20} color="#ef4444" />
              <div>
                <CardTitle style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  Server Bans & Punishments
                  <Badge variant={bans.length > 0 ? 'warning' : 'neutral'} size="sm">
                    {bans.length} Active {bans.length === 1 ? 'Ban' : 'Bans'}
                  </Badge>
                </CardTitle>
                <CardDescription>
                  View and manage banned users, execute targeted unbans, or perform server mass-unbans.
                </CardDescription>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Button
                variant="secondary"
                size="sm"
                onClick={fetchBans}
                loading={bansLoading}
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <RefreshCw size={14} /> Refresh Bans
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleUnbanAll}
                loading={unbanAllLoading}
                style={{ color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.4)' }}
              >
                <UserCheck size={14} /> Unban All Members
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Quick Ban Form */}
          <form onSubmit={handleBanUser} style={{
            display: 'flex',
            gap: '12px',
            flexWrap: 'wrap',
            alignItems: 'flex-end',
            padding: '16px',
            background: 'var(--bg-surface)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border)'
          }}>
            <div style={{ flex: '1', minWidth: '220px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Ban Discord User ID
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="Enter User ID (e.g. 936219932461510667)..."
                value={banUserId}
                onChange={e => setBanUserId(e.target.value)}
              />
            </div>

            <div style={{ flex: '2', minWidth: '260px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Reason for Ban
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="Violation of server rules, raid attempt, etc..."
                value={banReason}
                onChange={e => setBanReason(e.target.value)}
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              loading={banning}
              style={{ background: '#ef4444', borderColor: '#dc2626', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <UserX size={15} /> Ban Member
            </Button>
          </form>

          {/* Active Bans List */}
          <div>
            <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 600, color: 'var(--text-main)' }}>
              Active Server Bans ({bans.length})
            </h4>

            {bansLoading ? (
              <Skeleton height="100px" />
            ) : bans.length === 0 ? (
              <EmptyState
                icon={CheckCircle2}
                title="Clean Record — No Active Bans"
                description="There are currently no members banned from this Discord server."
              />
            ) : (
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                maxHeight: '360px',
                overflowY: 'auto',
                paddingRight: '4px'
              }}>
                {bans.map((b) => (
                  <div
                    key={b.user.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '12px 16px',
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-md)',
                      gap: '12px'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
                      {b.user.avatar ? (
                        <img
                          src={b.user.avatar}
                          alt=""
                          style={{ width: '36px', height: '36px', borderRadius: '50%', objectFit: 'cover' }}
                        />
                      ) : (
                        <div style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '50%',
                          background: 'rgba(239, 68, 68, 0.2)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: '#ef4444'
                        }}>
                          <UserX size={18} />
                        </div>
                      )}
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontWeight: 600, fontSize: '13.5px', color: 'var(--text-main)' }}>
                            {b.user.name}
                          </span>
                          <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                            ID: {b.user.id}
                          </span>
                        </div>
                        <p style={{ margin: '2px 0 0', fontSize: '12.5px', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          Reason: {b.reason}
                        </p>
                      </div>
                    </div>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleUnbanUser(b.user.id)}
                      loading={unbanningId === b.user.id}
                      style={{ color: '#22c55e', borderColor: 'rgba(34, 197, 94, 0.3)', whiteSpace: 'nowrap' }}
                    >
                      <UserCheck size={14} /> Unban
                    </Button>
                  </div>
                ))}
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
