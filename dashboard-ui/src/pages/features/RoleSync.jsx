import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

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

  const selectedSourceGuildObj = availableSources.find(g => g.id === sourceGuildId);
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
          ? `✅ Rule added! Backfilled ${synced} member(s) (${qualifying} qualifying checked).`
          : '✅ Rule added successfully!'
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
      const qualifying = res.data.qualifying ?? 0;
      setSuccess(`✅ Backfill complete: Synced ${synced} member(s) (${qualifying} checked).`);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to execute backfill');
    } finally {
      setBackfillingId(null);
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '300px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="page-header" style={{ marginBottom: '24px' }}>
        <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span>🔄</span> Cross-Server Role Sync
        </h1>
        <p className="page-subtitle">
          Synchronize member roles across your network of servers. When a user holds a verified role in Server A, they automatically receive the linked role in this server.
        </p>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: '16px' }}>{error}</div>}
      {success && <div className="alert alert-success" style={{ marginBottom: '16px' }}>{success}</div>}

      <div className="grid-2 stagger" style={{ gap: '24px', alignItems: 'start' }}>
        {/* Create Rule Panel */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '8px' }}>
            ➕ Link New Roles
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '20px' }}>
            Select a source server where the bot is also present, and choose which role should mirror to this server.
          </p>

          <form onSubmit={handleAddRule}>
            {/* Step 1: Source Guild */}
            <div className="form-group">
              <label className="form-label">1. Source Server</label>
              <Select
                value={sourceGuildId}
                onChange={(v) => {
                  setSourceGuildId(v);
                  setSourceRoleId('');
                }}
                options={availableSources.map(g => ({
                  value: g.id,
                  label: `${g.name} (${g.roles.length} roles)`,
                }))}
                placeholder="Select a source server..."
                searchable
              />
              {availableSources.length === 0 && (
                <span style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '4px', display: 'block' }}>
                  The bot is not present in any other servers yet. Invite the bot to the source server first.
                </span>
              )}
            </div>

            {/* Step 2: Source Role */}
            <div className="form-group">
              <label className="form-label">2. Source Role (In Source Server)</label>
              <Select
                value={sourceRoleId}
                onChange={setSourceRoleId}
                options={sourceRoles.map(r => ({
                  value: r.id,
                  label: r.name,
                }))}
                placeholder={sourceGuildId ? "Select role from source server..." : "Choose source server first"}
                disabled={!sourceGuildId || sourceRoles.length === 0}
                searchable
              />
            </div>

            {/* Step 3: Target Role */}
            <div className="form-group">
              <label className="form-label">3. Target Role (In THIS Server)</label>
              <Select
                value={targetRoleId}
                onChange={setTargetRoleId}
                options={targetRoles.map(r => ({
                  value: r.id,
                  label: r.name,
                }))}
                placeholder="Select target role to grant..."
                searchable
              />
            </div>

            {/* Backfill Toggle */}
            <div style={{
              background: 'rgba(255,255,255,0.02)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '20px',
            }}>
              <div>
                <div style={{ fontWeight: '600', fontSize: '14px', color: '#fff' }}>⚡ Backfill Existing Members</div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Immediately assign this role to any existing members who already hold the source role.
                </div>
              </div>
              <button
                type="button"
                className={`toggle ${backfill ? 'active' : ''}`}
                onClick={() => setBackfill(!backfill)}
                aria-label="Toggle Backfill"
              ></button>
            </div>

            <button
              type="submit"
              disabled={saving || !sourceGuildId || !sourceRoleId || !targetRoleId}
              className="btn btn-primary"
              style={{ width: '100%', display: 'flex', justifyContent: 'center', gap: '8px' }}
            >
              <span>{saving ? '⏳' : '🔗'}</span>
              {saving ? 'Linking & Syncing...' : 'Link & Activate Role Sync'}
            </button>
          </form>
        </div>

        {/* Active Rules List */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none' }}>
              📋 Active Sync Rules ({rules.length})
            </h3>
            <button
              type="button"
              onClick={fetchRoleSync}
              className="btn"
              style={{ fontSize: '12px', padding: '4px 10px', background: 'var(--bg-surface)' }}
            >
              🔄 Refresh
            </button>
          </div>

          {rules.length === 0 ? (
            <div style={{
              textAlign: 'center',
              padding: '48px 16px',
              color: 'var(--text-muted)',
              background: 'rgba(255,255,255,0.01)',
              borderRadius: '10px',
              border: '1px dashed var(--border)',
            }}>
              <div style={{ fontSize: '32px', marginBottom: '8px' }}>🔄</div>
              <div style={{ fontWeight: '600', fontSize: '15px', color: '#fff', marginBottom: '4px' }}>No Role Sync Rules Configured</div>
              <div style={{ fontSize: '13px', maxWidth: '340px', margin: '0 auto' }}>
                Use the form on the left to link roles from any server where this bot is present.
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {rules.map(rule => (
                <div
                  key={rule.id}
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    borderRadius: '10px',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
                    {/* Source */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.5px' }}>
                        From: {rule.source_guild_name}
                      </span>
                      <span className="badge" style={{ background: 'rgba(99,102,241,0.15)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.3)' }}>
                        @{rule.source_role_name}
                      </span>
                    </div>

                    <div style={{ fontSize: '20px', color: 'var(--text-muted)' }}>➔</div>

                    {/* Target */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.5px' }}>
                        To This Server:
                      </span>
                      <span className="badge" style={{ background: 'rgba(34,197,94,0.15)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.3)' }}>
                        @{rule.target_role_name}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'flex-end',
                    gap: '8px',
                    borderTop: '1px solid rgba(255,255,255,0.04)',
                    paddingTop: '10px',
                  }}>
                    <button
                      type="button"
                      disabled={backfillingId === rule.id}
                      onClick={() => handleManualBackfill(rule.id)}
                      className="btn"
                      style={{ fontSize: '12px', padding: '5px 12px', background: 'rgba(255,255,255,0.05)', color: '#fff' }}
                      title="Scan members right now and grant the role to anyone who qualifies"
                    >
                      {backfillingId === rule.id ? '⏳ Backfilling...' : '⚡ Backfill Now'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteRule(rule.id)}
                      className="btn btn-danger"
                      style={{ fontSize: '12px', padding: '5px 12px' }}
                    >
                      🗑️ Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
