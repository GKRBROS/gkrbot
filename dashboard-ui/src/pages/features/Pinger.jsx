import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';
import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import { Toggle } from '../../components/Toggle';
import { PageHeader } from '../../components/PageHeader';
import {
  Bell,
  Hash,
  Users,
  MessageSquareText,
  Timer,
  Plus,
  X,
  AlertCircle,
  Check,
  Save,
  RotateCcw,
} from 'lucide-react';

const DEFAULT_CONFIG = {
  enabled: false,
  channel_id: '',
  role_ids: [],
  text: '',
  interval_seconds: 300,
};

export function Pinger() {
  const { guildId } = useParams();

  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [savedConfig, setSavedConfig] = useState(DEFAULT_CONFIG);
  const [limits, setLimits] = useState({ min_interval_seconds: 30, max_roles: 10, max_text_length: 300 });

  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [channelsError, setChannelsError] = useState('');
  const [pendingRole, setPendingRole] = useState('');

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    setChannelsError('');

    const [pingerRes, channelsRes, rolesRes] = await Promise.allSettled([
      api.get(`/guilds/${guildId}/pinger`),
      api.get(`/guilds/${guildId}/channels`),
      api.get(`/guilds/${guildId}/roles`),
    ]);

    if (pingerRes.status === 'fulfilled') {
      const c = pingerRes.value.data?.config;
      if (c) {
        const normalized = {
          enabled: !!c.enabled,
          channel_id: c.channel_id || '',
          role_ids: Array.isArray(c.role_ids) ? c.role_ids : [],
          text: c.text || '',
          interval_seconds: c.interval_seconds || 300,
        };
        setConfig(normalized);
        setSavedConfig(normalized);
      } else {
        setConfig(DEFAULT_CONFIG);
        setSavedConfig(DEFAULT_CONFIG);
      }
      if (pingerRes.value.data?.limits) setLimits(pingerRes.value.data.limits);
    } else {
      console.error('Failed to load Pinger configuration', pingerRes.reason);
      setError(
        pingerRes.reason?.response?.data?.error ||
        pingerRes.reason?.message ||
        'Failed to load configuration. Please try again.'
      );
    }

    if (channelsRes.status === 'fulfilled') {
      const d = channelsRes.value.data;
      setChannels(Array.isArray(d) ? d : (d?.channels || []));
    } else {
      setChannels([]);
      setChannelsError(
        channelsRes.reason?.response?.data?.error ||
        channelsRes.reason?.message ||
        'Failed to load channels.'
      );
    }

    if (rolesRes.status === 'fulfilled') {
      const d = rolesRes.value.data;
      setRoles(Array.isArray(d) ? d : (d?.roles || []));
    } else {
      setRoles([]);
    }

    setLoading(false);
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const isDirty = useMemo(
    () => JSON.stringify(config) !== JSON.stringify(savedConfig),
    [config, savedConfig]
  );

  const isTextChannel = c => {
    const t = c.type;
    if (t === undefined || t === null) return true;
    if (typeof t === 'number' || /^\d+$/.test(String(t))) return [0, 5].includes(Number(t));
    return /text|news|announ/i.test(String(t));
  };
  const channelOptions = [
    { value: '', label: 'Select a channel...' },
    ...channels.filter(isTextChannel).map(c => ({ value: c.id, label: `#${c.name}` }))
  ];

  const roleMap = useMemo(() => Object.fromEntries(roles.map(r => [String(r.id), r.name])), [roles]);
  const addableRoleOptions = [
    { value: '', label: 'Add a role...' },
    ...roles
      .filter(r => !config.role_ids.includes(String(r.id)))
      .map(r => ({ value: r.id, label: `@${r.name}` }))
  ];

  const handleAddRole = () => {
    if (!pendingRole) return;
    if (config.role_ids.length >= limits.max_roles) return;
    setConfig(c => ({ ...c, role_ids: [...c.role_ids, String(pendingRole)] }));
    setPendingRole('');
  };
  const handleRemoveRole = (roleId) => {
    setConfig(c => ({ ...c, role_ids: c.role_ids.filter(r => r !== roleId) }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError('');
      const payload = {
        enabled: config.enabled,
        channel_id: config.channel_id,
        role_ids: config.role_ids,
        text: config.text,
        interval_seconds: config.interval_seconds,
      };
      await api.post(`/guilds/${guildId}/pinger`, payload);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      await fetchData();
    } catch (err) {
      console.error('Failed to save Pinger configuration', err);
      setError(err.response?.data?.error || 'Failed to save configuration.');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setConfig({ ...savedConfig });
    setError('');
  };

  if (loading) {
    return <div className="p-8! text-center text-muted">Loading Pinger...</div>;
  }

  return (
    <div className="flex flex-col gap-6 animate-fade-in pb-28! sm:pb-32!">
      <PageHeader
        title="Pinger"
        description="Keep a single, always-fresh role ping alive in a channel — the previous ping is deleted before the next one is sent."
        icon={Bell}
        badge={config.enabled ? 'Active' : 'Stopped'}
        badgeVariant={config.enabled ? 'success' : 'neutral'}
      />

      {error && (
        <div className="p-4! rounded-xl bg-danger/10 border border-danger/30 text-danger flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
          <button type="button" onClick={() => setError('')} className="text-xs opacity-70 hover:opacity-100 underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Main Feature Toggle Banner */}
      <div className={`p-4! sm:p-5! rounded-2xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
        config.enabled
          ? 'bg-primary/10 border-primary/30 shadow-sm'
          : 'bg-surface border-border'
      }`}>
        <div className="flex items-center gap-3.5">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
            config.enabled ? 'bg-primary text-white shadow-md' : 'bg-card text-muted border border-border'
          }`}>
            <Bell size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-main">Repeating Role Ping</h3>
              <Badge variant={config.enabled ? 'success' : 'neutral'} size="sm">
                {config.enabled ? 'Running' : 'Stopped'}
              </Badge>
            </div>
            <p className="text-xs sm:text-sm text-muted mt-0.5!">
              Re-sends the ping on its interval and removes the previous one each time.
            </p>
          </div>
        </div>

        <Toggle
          checked={config.enabled}
          onChange={v => setConfig(c => ({ ...c, enabled: v }))}
          ariaLabel="Toggle Pinger"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <Card>
          <CardHeader>
            <div>
              <CardTitle icon={Hash}>Channel</CardTitle>
              <CardDescription>Where the repeating ping is posted.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="form-group">
              <label className="form-label">Ping Channel</label>
              <Select
                value={config.channel_id}
                onChange={v => setConfig(c => ({ ...c, channel_id: v }))}
                options={channelOptions}
                searchable
              />
              {channelsError && (
                <div className="flex items-center justify-between gap-3 mt-2! text-xs text-danger">
                  <span>{channelsError}</span>
                  <button type="button" onClick={fetchData} className="underline shrink-0">Retry</button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle icon={Timer}>Interval</CardTitle>
              <CardDescription>How often to re-ping, in seconds (minimum {limits.min_interval_seconds}).</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="form-group">
              <label className="form-label">Re-ping every (seconds)</label>
              <input
                type="number"
                min={limits.min_interval_seconds}
                className="input-field"
                value={config.interval_seconds}
                onChange={e => setConfig(c => ({ ...c, interval_seconds: Number(e.target.value) || limits.min_interval_seconds }))}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle icon={Users}>Roles to Ping</CardTitle>
              <CardDescription>Up to {limits.max_roles} roles get mentioned together in each ping.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2 mb-3!">
              {config.role_ids.length === 0 ? (
                <span className="text-xs text-muted">No roles added yet.</span>
              ) : (
                config.role_ids.map(rid => (
                  <span key={rid} className="inline-flex items-center gap-1.5 px-2.5! py-1! rounded-full bg-primary/10 border border-primary/25 text-xs text-primary">
                    @{roleMap[rid] || rid}
                    <button type="button" onClick={() => handleRemoveRole(rid)} className="hover:text-danger" aria-label="Remove role">
                      <X size={12} />
                    </button>
                  </span>
                ))
              )}
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <Select
                  value={pendingRole}
                  onChange={setPendingRole}
                  options={addableRoleOptions}
                  searchable
                />
              </div>
              <Button
                variant="secondary"
                size="sm"
                icon={Plus}
                onClick={handleAddRole}
                disabled={!pendingRole || config.role_ids.length >= limits.max_roles}
              >
                Add
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle icon={MessageSquareText}>Custom Text</CardTitle>
              <CardDescription>Optional message shown alongside the mentions.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="form-group">
              <label className="form-label">Message</label>
              <textarea
                className="input-field min-h-[100px]"
                value={config.text}
                onChange={e => setConfig(c => ({ ...c, text: e.target.value.slice(0, limits.max_text_length) }))}
                placeholder="Don't forget to check in!"
                maxLength={limits.max_text_length}
              />
              <p className="text-xs text-muted mt-1.5!">{config.text.length} / {limits.max_text_length}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {(isDirty || saving || saved) && (
        <div className="sticky bottom-4 z-40 mt-8!">
          <div className="p-3.5! sm:p-4! rounded-2xl bg-card/95 backdrop-blur-md border border-border shadow-2xl flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 sm:gap-4 max-w-3xl mx-auto!">
            <div className="flex items-center gap-2">
              {isDirty ? (
                <span className="text-xs font-semibold text-warning flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-warning animate-pulse shrink-0" />
                  <span>Unsaved changes pending</span>
                </span>
              ) : saved ? (
                <span className="text-xs font-semibold text-success flex items-center gap-1.5">
                  <Check size={14} className="shrink-0" /> <span>Settings saved successfully</span>
                </span>
              ) : (
                <span className="text-xs text-muted">All settings saved to server</span>
              )}
            </div>

            <div className="flex items-center gap-2.5 justify-end">
              {isDirty && (
                <Button variant="ghost" size="sm" onClick={handleReset} disabled={saving}>
                  Discard
                </Button>
              )}
              <Button
                variant="primary"
                size="sm"
                icon={Save}
                loading={saving}
                onClick={handleSave}
                disabled={!isDirty && !saving}
              >
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Pinger;
