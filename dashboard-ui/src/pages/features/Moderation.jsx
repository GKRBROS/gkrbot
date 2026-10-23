import { useEffect, useState, useCallback, useMemo } from 'react';
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
  Shield,
  Gavel,
  UserX,
  UserCheck,
  RefreshCw,
  Sliders,
  Ban,
  X,
  Save,
  Clock,
  EyeOff
} from 'lucide-react';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync, syncParams } from '../../sync';
import { RoleSelect } from '../../components/RoleSelect';
import { ChannelSelect } from '../../components/ChannelSelect';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import Toggle from '../../components/Toggle';
import { useToast } from '../../components/ToastContext';
import Loader from '../../components/Loader';

function Moderation() {
  const { guildId } = useParams();
  const toast = useToast();

  const [roles, setRoles] = useState([]);
  const [channels, setChannels] = useState([]);
  const [staffRoleIds, setStaffRoleIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRole, setSelectedRole] = useState('');
  const [syncOpen, setSyncOpen] = useState(false);
  const [savingAutomod, setSavingAutomod] = useState(false);

  // Automod state
  const [automod, setAutomod] = useState({
    enabled: 1,
    log_channel_id: '',
    anti_invites: 1,
    anti_links: 0,
    anti_badwords: 1,
    keyword_blacklist: [],
    action: 'delete'
  });
  const [newKeyword, setNewKeyword] = useState('');

  // Infractions state
  const [infractions, setInfractions] = useState([]);
  const [infractionsLoading, setInfractionsLoading] = useState(false);
  const [revokingId, setRevokingId] = useState(null);

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

  const fetchInfractions = useCallback(async () => {
    setInfractionsLoading(true);
    try {
      const res = await api.get(`/guilds/${guildId}/moderation/infractions`);
      setInfractions(res.data.infractions || []);
    } catch (err) {
      console.error('Failed to load infractions', err);
    } finally {
      setInfractionsLoading(false);
    }
  }, [guildId]);

  const fetchData = useCallback(async () => {
    try {
      const [modRes, rolesRes, channelsRes, automodRes] = await Promise.allSettled([
        api.get(`/guilds/${guildId}/moderation`),
        api.get(`/guilds/${guildId}/roles`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/moderation/automod`),
      ]);

      if (modRes.status === 'fulfilled' && modRes.value.data?.staff_roles) {
        setStaffRoleIds(modRes.value.data.staff_roles || []);
      }
      if (rolesRes.status === 'fulfilled' && rolesRes.value.data?.roles) {
        setRoles(rolesRes.value.data.roles || []);
      }
      if (channelsRes.status === 'fulfilled' && channelsRes.value.data?.channels) {
        setChannels(channelsRes.value.data.channels || []);
      }
      if (automodRes.status === 'fulfilled' && automodRes.value.data?.automod) {
        setAutomod(prev => ({
          ...prev,
          ...automodRes.value.data.automod,
          log_channel_id: automodRes.value.data.automod.log_channel_id || ''
        }));
      }

      await Promise.all([fetchBans(), fetchInfractions()]);
    } catch (err) {
      console.error('Failed to load moderation settings', err);
      if (toast) toast('Failed to load moderation data', 'error');
    } finally {
      setLoading(false);
    }
  }, [guildId, fetchBans, fetchInfractions, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddRole = async (e) => {
    e.preventDefault();
    if (!selectedRole) return;
    try {
      await api.post(`/guilds/${guildId}/moderation/staff-roles`, withSync({ role_id: selectedRole }));
      setStaffRoleIds(prev => [...prev.filter(id => id !== selectedRole), selectedRole]);
      setSelectedRole('');
      if (toast) toast('Designated staff role successfully', 'success');
    } catch (err) {
      if (toast) toast(err.response?.data?.error || 'Failed to designate staff role', 'error');
    }
  };

  const handleRemoveRole = async (roleId) => {
    try {
      await api.delete(`/guilds/${guildId}/moderation/staff-roles/${roleId}`, { params: syncParams() });
      setStaffRoleIds(prev => prev.filter(id => id !== roleId));
      if (toast) toast('Removed staff role assignment', 'success');
    } catch (err) {
      if (toast) toast('Failed to remove staff role', 'error');
    }
  };

  const handleSaveAutomod = async () => {
    setSavingAutomod(true);
    try {
      await api.post(`/guilds/${guildId}/moderation/automod`, automod);
      if (toast) toast('AutoMod rules and keyword blacklist saved!', 'success');
    } catch (err) {
      if (toast) toast(err.response?.data?.error || 'Failed to save automod rules', 'error');
    } finally {
      setSavingAutomod(false);
    }
  };

  const handleAddKeyword = (e) => {
    e.preventDefault();
    const word = newKeyword.trim().toLowerCase();
    if (!word) return;
    if (automod.keyword_blacklist.includes(word)) {
      if (toast) toast('Keyword already exists in blacklist', 'warning');
      return;
    }
    setAutomod(prev => ({
      ...prev,
      keyword_blacklist: [...prev.keyword_blacklist, word]
    }));
    setNewKeyword('');
  };

  const handleRemoveKeyword = (word) => {
    setAutomod(prev => ({
      ...prev,
      keyword_blacklist: prev.keyword_blacklist.filter(w => w !== word)
    }));
  };

  const handleRevokeInfraction = async (infractionId) => {
    setRevokingId(infractionId);
    try {
      await api.post(`/guilds/${guildId}/moderation/infractions/${infractionId}/revoke`);
      setInfractions(prev =>
        prev.map(inf => inf.id === infractionId ? { ...inf, status: 'revoked' } : inf)
      );
      if (toast) toast(`Revoked infraction #${infractionId}`, 'success');
    } catch (err) {
      if (toast) toast('Failed to revoke infraction', 'error');
    } finally {
      setRevokingId(null);
    }
  };

  const handleBanUser = async (e) => {
    e.preventDefault();
    if (!banUserId.trim()) {
      if (toast) toast('Please provide a Discord User ID', 'error');
      return;
    }
    setBanning(true);
    try {
      await api.post(`/guilds/${guildId}/moderation/ban`, {
        user_id: banUserId.trim(),
        reason: banReason.trim() || 'Banned via web dashboard'
      });
      setBanUserId('');
      setBanReason('');
      if (toast) toast('User banned successfully', 'success');
      await fetchBans();
    } catch (err) {
      if (toast) toast(err.response?.data?.error || 'Failed to ban user', 'error');
    } finally {
      setBanning(false);
    }
  };

  const handleUnbanUser = async (userId) => {
    setUnbanningId(userId);
    try {
      await api.post(`/guilds/${guildId}/moderation/unban`, { user_id: userId });
      setBans(prev => prev.filter(b => b.user.id !== userId));
      if (toast) toast('User unbanned successfully', 'success');
    } catch (err) {
      if (toast) toast('Failed to unban user', 'error');
    } finally {
      setUnbanningId('');
    }
  };

  const handleUnbanAll = async () => {
    if (!window.confirm('Are you sure you want to unban ALL users? This action cannot be reversed.')) return;
    setUnbanAllLoading(true);
    try {
      const res = await api.post(`/guilds/${guildId}/moderation/unbanall`);
      if (toast) toast(`Successfully unbanned ${res.data.count} users!`, 'success');
      setBans([]);
    } catch (err) {
      if (toast) toast('Failed to unban all members', 'error');
    } finally {
      setUnbanAllLoading(false);
    }
  };

  const getRole = (id) => roles.find(r => String(r.id) === String(id)) || { name: `Role ${id}`, color: '#99aab5' };

  if (loading) {
    return <Loader label="Loading Moderation & AutoMod..." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Moderation & AutoMod Engine"
        description="Automated content moderation rules, keyword filters, infraction tracking, bans, and staff roles."
        icon={ShieldAlert}
        badge="Security Suite"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" icon={Share2} onClick={() => setSyncOpen(true)}>
              Sync Config
            </Button>
            <Button variant="primary" icon={Save} onClick={handleSaveAutomod} loading={savingAutomod}>
              Save AutoMod
            </Button>
          </div>
        }
      />

      {/* AutoMod Rules & Keyword Blacklist */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle icon={Sliders}>AutoMod Shield & Filter Rules</CardTitle>
            <CardDescription>Instant automated enforcement against spam, invites, and unauthorized content.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Toggle
              checked={Boolean(automod.enabled)}
              onChange={val => setAutomod({ ...automod, enabled: val ? 1 : 0 })}
              label="Enable AutoMod Filter Engine"
              description="Actively monitor and filter chat messages in real time"
            />

            <div className="space-y-4 pt-4 border-t border-border">
              <Toggle
                checked={Boolean(automod.anti_invites)}
                onChange={val => setAutomod({ ...automod, anti_invites: val ? 1 : 0 })}
                label="Block Discord Server Invites"
                description="Automatically removes unauthorized discord.gg links"
              />
              <Toggle
                checked={Boolean(automod.anti_links)}
                onChange={val => setAutomod({ ...automod, anti_links: val ? 1 : 0 })}
                label="Block All External Links"
                description="Restricts URL sharing for non-staff members"
              />
              <Toggle
                checked={Boolean(automod.anti_badwords)}
                onChange={val => setAutomod({ ...automod, anti_badwords: val ? 1 : 0 })}
                label="Enforce Keyword Blacklist"
                description="Scans and blocks messages containing blacklisted terms"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-border">
              <div className="form-group">
                <label className="form-label">AutoMod Violation Action</label>
                <select
                  className="form-input"
                  value={automod.action || 'delete'}
                  onChange={e => setAutomod({ ...automod, action: e.target.value })}
                >
                  <option value="delete">Delete Message Only</option>
                  <option value="warn">Delete & Issue Warning</option>
                  <option value="mute">Delete & Timeout (10m)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Moderation Log Channel</label>
                <ChannelSelect
                  value={automod.log_channel_id}
                  onChange={chId => setAutomod({ ...automod, log_channel_id: chId })}
                  channels={channels}
                  allowedTypes={['text', 'news']}
                  placeholder="Select mod log channel..."
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Keyword Blacklist Manager */}
        <Card>
          <CardHeader>
            <CardTitle icon={Ban}>Keyword Blacklist</CardTitle>
            <CardDescription>Messages matching these terms or phrases are automatically blocked.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={handleAddKeyword} className="flex gap-2">
              <input
                type="text"
                className="form-input"
                placeholder="Enter word or phrase to block..."
                value={newKeyword}
                onChange={e => setNewKeyword(e.target.value)}
              />
              <Button type="submit" variant="primary" icon={Plus}>
                Add
              </Button>
            </form>

            <div className="p-3 rounded-lg border border-border bg-surface-card min-h-[140px] max-h-56 overflow-y-auto">
              {automod.keyword_blacklist.length === 0 ? (
                <div className="text-center py-8 text-xs text-muted">
                  No keywords blacklisted. Type a word above to add.
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {automod.keyword_blacklist.map(word => (
                    <span
                      key={word}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-danger/15 text-danger border border-danger/25"
                    >
                      {word}
                      <button
                        type="button"
                        onClick={() => handleRemoveKeyword(word)}
                        className="hover:text-white"
                        title="Remove word"
                      >
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <span className="text-[11px] text-muted block">
              AutoMod checks full and partial word matches case-insensitively.
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Infractions & Warns Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <CardTitle icon={Clock}>Active Infractions & Warnings</CardTitle>
              <CardDescription>Track member infractions, timeouts, and revoke active punishments.</CardDescription>
            </div>
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={fetchInfractions} loading={infractionsLoading}>
              Refresh Infractions
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {infractions.length === 0 ? (
            <div className="py-8 text-center text-muted text-sm border border-dashed border-border rounded-lg">
              No active infractions logged in this server.
            </div>
          ) : (
            <div className="overflow-x-auto border border-border rounded-lg">
              <table className="w-full text-left text-sm">
                <thead className="bg-surface-card text-muted text-xs uppercase border-b border-border">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Infraction</th>
                    <th className="px-4 py-3 font-semibold">User ID</th>
                    <th className="px-4 py-3 font-semibold">Action</th>
                    <th className="px-4 py-3 font-semibold">Reason</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold text-right">Revoke</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {infractions.map(inf => {
                    const isRevoked = inf.status === 'revoked';
                    return (
                      <tr key={inf.id} className="hover:bg-surface-hover/30 transition">
                        <td className="px-4 py-3 font-bold text-main">#{inf.id}</td>
                        <td className="px-4 py-3 font-mono text-xs">{inf.user_id}</td>
                        <td className="px-4 py-3">
                          <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded ${
                            inf.action === 'ban' ? 'bg-danger/20 text-danger' :
                            inf.action === 'mute' ? 'bg-warning/20 text-warning' :
                            'bg-primary/20 text-primary'
                          }`}>
                            {inf.action}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-muted max-w-xs truncate">{inf.reason || 'No reason specified'}</td>
                        <td className="px-4 py-3">
                          <span className={`text-xs font-semibold ${isRevoked ? 'text-muted' : 'text-success'}`}>
                            {isRevoked ? 'Revoked' : 'Active'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          {!isRevoked && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleRevokeInfraction(inf.id)}
                              loading={revokingId === inf.id}
                              className="text-xs"
                            >
                              Revoke
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Staff Roles & Bans Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle icon={Users}>Staff Roles</CardTitle>
                <CardDescription>Members with these roles can use moderation commands.</CardDescription>
              </div>
              <Badge variant="primary" size="sm">{staffRoleIds.length} Roles</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={handleAddRole} className="flex gap-2">
              <div className="flex-1">
                <RoleSelect
                  value={selectedRole}
                  onChange={setSelectedRole}
                  roles={roles}
                  manageableOnly={true}
                  placeholder="Designate a staff role..."
                />
              </div>
              <Button type="submit" variant="primary" icon={Plus} disabled={!selectedRole}>
                Assign
              </Button>
            </form>

            <div className="flex flex-wrap gap-2 pt-2">
              {staffRoleIds.map(id => {
                const r = getRole(id);
                return (
                  <div
                    key={id}
                    className="inline-flex items-center gap-2 px-3 py-1 rounded-lg border border-border bg-surface-card"
                  >
                    <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: r.color || '#99aab5' }} />
                    <span className="text-xs font-semibold text-main">@{r.name}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveRole(id)}
                      className="text-danger hover:text-white"
                      title="Remove staff role"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Server Bans Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <CardTitle icon={Gavel}>Server Bans ({bans.length})</CardTitle>
                <CardDescription>Manage banned users and execute targeted unbans.</CardDescription>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" icon={RefreshCw} onClick={fetchBans} loading={bansLoading} />
                <Button variant="outline" size="sm" onClick={handleUnbanAll} loading={unbanAllLoading} className="text-danger">
                  Unban All
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={handleBanUser} className="flex flex-wrap gap-2">
              <input
                type="text"
                className="form-input flex-1 min-w-[140px]"
                placeholder="User ID..."
                value={banUserId}
                onChange={e => setBanUserId(e.target.value)}
              />
              <input
                type="text"
                className="form-input flex-2 min-w-[160px]"
                placeholder="Reason..."
                value={banReason}
                onChange={e => setBanReason(e.target.value)}
              />
              <Button type="submit" variant="primary" icon={UserX} loading={banning} className="bg-danger border-danger">
                Ban
              </Button>
            </form>

            <div className="max-h-56 overflow-y-auto space-y-2">
              {bans.length === 0 ? (
                <div className="text-center py-6 text-xs text-muted">No members currently banned.</div>
              ) : (
                bans.map(b => (
                  <div key={b.user.id} className="flex items-center justify-between p-2.5 rounded-lg border border-border bg-surface-card">
                    <div className="flex items-center gap-2 truncate">
                      <span className="font-semibold text-xs text-main">{b.user.name}</span>
                      <span className="font-mono text-[10px] text-muted">({b.user.id})</span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleUnbanUser(b.user.id)}
                      loading={unbanningId === b.user.id}
                      className="text-success text-xs"
                    >
                      Unban
                    </Button>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

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
