import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  GitCompare,
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Shield,
  Server
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

export default function RoleSync() {
  const { guildId } = useParams();

  const [rules, setRules] = useState([]);
  const [availableSources, setAvailableSources] = useState([]);
  const [targetRoles, setTargetRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Form State
  const [sourceGuildId, setSourceGuildId] = useState('');
  const [sourceRoleId, setSourceRoleId] = useState('');
  const [targetRoleId, setTargetRoleId] = useState('');
  const [backfill, setBackfill] = useState(true);
  const [saving, setSaving] = useState(false);
  const [backfillingId, setBackfillingId] = useState(null);

  const fetchRoleSync = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/role-sync`);
      setRules(res.data.rules || []);
      setAvailableSources(res.data.available_sources || []);
      setTargetRoles(res.data.target_roles || []);
      setError('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load role sync rules');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchRoleSync();
  }, [fetchRoleSync]);

  const selectedSourceGuildObj = availableSources.find(g => String(g.id) === String(sourceGuildId));
  const sourceRoles = selectedSourceGuildObj?.roles || [];

  const handleAddRule = async (e) => {
    e.preventDefault();
    if (!sourceGuildId || !sourceRoleId || !targetRoleId) {
      setError('Please select a source server, source role, and target role.');
      return;
    }

    setSaving(true);
    setError('');
    setSuccess('');

    try {
      const res = await api.post(`/guilds/${guildId}/role-sync`, {
        source_guild_id: sourceGuildId,
        source_role_id: sourceRoleId,
        target_role_id: targetRoleId,
        backfill,
      });

      const synced = res.data.synced ?? 0;
      const qualifying = res.data.qualifying ?? 0;
      setSuccess(
        backfill
          ? `Rule configured! Backfilled ${synced} member(s) (${qualifying} qualifying checked).`
          : 'Role sync rule added successfully!'
      );

      // Reset form
      setSourceRoleId('');
      setTargetRoleId('');
      fetchRoleSync();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add role sync rule');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRule = async (ruleId) => {
    if (!window.confirm('Are you sure you want to delete this role sync rule?')) return;
    try {
      await api.delete(`/guilds/${guildId}/role-sync/${ruleId}`);
      setSuccess('Rule deleted successfully.');
      fetchRoleSync();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete rule');
    }
  };

  const handleManualBackfill = async (ruleId) => {
    setBackfillingId(ruleId);
    setError('');
    setSuccess('');
    try {
      const res = await api.post(`/guilds/${guildId}/role-sync/${ruleId}/backfill`);
      const synced = res.data.synced ?? 0;
      setSuccess(`Backfill complete! Synced ${synced} member(s) across servers.`);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to trigger manual backfill');
    } finally {
      setBackfillingId(null);
    }
  };

  const sourceGuildOptions = availableSources.map(g => ({
    value: g.id,
    label: g.name
  }));

  const sourceRoleOptions = sourceRoles.map(r => ({
    value: r.id,
    label: `@${r.name}`
  }));

  const targetRoleOptions = targetRoles.map(r => ({
    value: r.id,
    label: `@${r.name}`
  }));

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="260px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={GitCompare}
        title="Cross-Server Role Sync"
        subtitle="Automatically synchronize VIP, Subscriber, Booster, or Staff roles from other community servers you manage."
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

      {/* Add Role Sync Rule Form */}
      <Card>
        <CardHeader>
          <CardTitle>Create Role Synchronization Bridge</CardTitle>
          <CardDescription>
            When a member holds a role in the source server, they automatically receive the target role in this server.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAddRule} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '14px', alignItems: 'flex-end' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Source Server
                </label>
                <Select
                  value={sourceGuildId}
                  onChange={val => {
                    setSourceGuildId(val);
                    setSourceRoleId('');
                  }}
                  options={sourceGuildOptions}
                  placeholder="Select source server..."
                  searchable
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Source Server Role
                </label>
                <Select
                  value={sourceRoleId}
                  onChange={setSourceRoleId}
                  options={sourceRoleOptions}
                  placeholder={sourceGuildId ? 'Select source role...' : 'Choose source server first'}
                  disabled={!sourceGuildId}
                  searchable
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Target Role (This Server)
                </label>
                <Select
                  value={targetRoleId}
                  onChange={setTargetRoleId}
                  options={targetRoleOptions}
                  placeholder="Select role to assign here..."
                  searchable
                />
              </div>
            </div>

            <div style={{
              padding: '14px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)'
            }}>
              <Toggle
                checked={backfill}
                onChange={setBackfill}
                label="Instant Backfill"
                description="Immediately scans all current server members and assigns roles to those already eligible."
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
              <Button
                type="submit"
                variant="primary"
                icon={Plus}
                loading={saving}
                disabled={!sourceGuildId || !sourceRoleId || !targetRoleId}
              >
                Create Sync Bridge
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Active Sync Bridges */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Active Sync Bridges
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Live role synchronization rules active between your Discord communities.
            </p>
          </div>
          <Badge variant="primary" size="sm">{rules.length} Active Rules</Badge>
        </div>

        {rules.length === 0 ? (
          <EmptyState
            icon={GitCompare}
            title="No Sync Bridges Configured"
            description="Link roles between your Discord servers above to automatically grant perks to cross-community members."
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {rules.map(rule => (
              <Card key={rule.id} style={{ padding: '16px 20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Server size={16} color="var(--text-muted)" />
                      <span style={{ fontWeight: 600, fontSize: '13.5px', color: 'var(--text-main)' }}>
                        {rule.source_guild_name || 'Source Server'}
                      </span>
                      <Badge variant="neutral" size="sm">
                        @{rule.source_role_name || rule.source_role_id}
                      </Badge>
                    </div>

                    <ArrowRight size={16} color="var(--primary)" />

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Shield size={16} color="var(--primary)" />
                      <span style={{ fontWeight: 600, fontSize: '13.5px', color: 'var(--text-main)' }}>
                        This Server:
                      </span>
                      <Badge variant="primary" size="sm">
                        @{rule.target_role_name || rule.target_role_id}
                      </Badge>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Button
                      variant="outline"
                      size="sm"
                      icon={RefreshCw}
                      loading={backfillingId === rule.id}
                      onClick={() => handleManualBackfill(rule.id)}
                    >
                      Resync
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={Trash2}
                      onClick={() => handleDeleteRule(rule.id)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
