import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  ShieldCheck,
  ShieldAlert,
  Zap,
  Scan,
  Share2,
  CheckCircle2,
  AlertCircle,
  Hash,
  Users,
  Clock,
  MessageSquare,
  Trash2,
  Plus,
  Lock
} from 'lucide-react';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync } from '../../sync';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import Badge from '../../components/Badge';
import Skeleton from '../../components/Skeleton';

function Security() {
  const { guildId } = useParams();
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [syncOpen, setSyncOpen] = useState(false);

  const [config, setConfig] = useState({
    anti_spam_enabled: true,
    spam_msg_limit: 5,
    spam_time_sec: 5,
    mass_mention_limit: 5,
    log_channel_id: '',
    image_scan_enabled: true,
  });

  const [antinuke, setAntinuke] = useState({
    enabled: true,
    strict_mode: true,
    ban_limit: 2,
    kick_limit: 2,
    channel_delete_limit: 1,
    channel_create_limit: 3,
    role_delete_limit: 1,
    role_create_limit: 3,
    anti_bot: true,
    action: 'strip_roles',
    time_window_sec: 20,
  });

  const [whitelist, setWhitelist] = useState([]);
  const [newWhitelistId, setNewWhitelistId] = useState('');
  const [antinukeSaving, setAntinukeSaving] = useState(false);
  const [antinukeSaved, setAntinukeSaved] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [secRes, chanRes, anRes] = await Promise.allSettled([
        api.get(`/guilds/${guildId}/security`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/antinuke`),
      ]);
      if (secRes.status === 'fulfilled' && secRes.value.data?.config) {
        setConfig(secRes.value.data.config);
      }
      if (chanRes.status === 'fulfilled' && chanRes.value.data?.channels) {
        setChannels(chanRes.value.data.channels || []);
      }
      if (anRes.status === 'fulfilled' && anRes.value.data?.config) {
        const c = anRes.value.data.config;
        setAntinuke({
          ...c,
          enabled: Boolean(c.enabled),
          strict_mode: Boolean(c.strict_mode ?? 1),
          anti_bot: Boolean(c.anti_bot),
        });
        if (anRes.value.data.whitelist) {
          setWhitelist(anRes.value.data.whitelist);
        }
      }
    } catch (err) {
      console.error('Failed to load security config', err);
      setError(err.response?.data?.error || 'Failed to load security config');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await api.post(`/guilds/${guildId}/security`, withSync(config));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save security configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAntinuke = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setAntinukeSaving(true);
    try {
      const payload = {
        ...antinuke,
        enabled: antinuke.enabled ? 1 : 0,
        strict_mode: antinuke.strict_mode ? 1 : 0,
        anti_bot: antinuke.anti_bot ? 1 : 0,
      };
      await api.post(`/guilds/${guildId}/antinuke`, payload);
      setAntinukeSaved(true);
      setTimeout(() => setAntinukeSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save Anti-Nuke settings');
    } finally {
      setAntinukeSaving(false);
    }
  };

  const handleAddWhitelist = async (e) => {
    if (e) e.preventDefault();
    if (!newWhitelistId.trim()) return;
    setError('');
    try {
      const res = await api.post(`/guilds/${guildId}/antinuke/whitelist`, { target_id: newWhitelistId.trim() });
      if (res.data.whitelist) setWhitelist(res.data.whitelist);
      setNewWhitelistId('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add to whitelist');
    }
  };

  const handleRemoveWhitelist = async (targetId) => {
    setError('');
    try {
      const res = await api.delete(`/guilds/${guildId}/antinuke/whitelist/${targetId}`);
      if (res.data.whitelist) setWhitelist(res.data.whitelist);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to remove from whitelist');
    }
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="200px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  const channelOptions = [
    { value: '', label: 'Disabled (No Security Channel)' },
    ...channels.map(ch => ({ value: ch.id, label: `#${ch.name}` }))
  ];

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={ShieldCheck}
        title="Security & Anti-Spam"
        subtitle="Automated rate limiting protection, mass-mention safeguards, and heuristic content filtering."
        actions={
          <div style={{ display: 'flex', gap: '10px' }}>
            <Button
              variant="outline"
              size="sm"
              icon={Share2}
              onClick={() => setSyncOpen(true)}
            >
              Sync to Servers
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={CheckCircle2}
              loading={saving}
              onClick={handleSave}
            >
              {saved ? 'Saved!' : 'Save Security Rules'}
            </Button>
          </div>
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

      {/* Anti-Spam Card */}
      <Card>
        <CardHeader>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Zap size={20} color="var(--primary)" />
            <div>
              <CardTitle>Anti-Spam & Rate Limiter</CardTitle>
              <CardDescription>
                Detect and suppress rapid message flooding, duplicate copypastas, and raid spam in real-time.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)'
          }}>
            <Toggle
              checked={config.anti_spam_enabled}
              onChange={val => setConfig({ ...config, anti_spam_enabled: val })}
              label="Enable Anti-Spam Shield"
              description="Automatically throttles members sending messages faster than humanly possible."
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Message Limit
              </label>
              <input
                type="number"
                min="2"
                max="50"
                className="form-input"
                value={config.spam_msg_limit}
                onChange={e => setConfig({ ...config, spam_msg_limit: parseInt(e.target.value, 10) || 5 })}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Maximum number of messages allowed inside the time window.
              </p>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Time Window (Seconds)
              </label>
              <input
                type="number"
                min="1"
                max="60"
                className="form-input"
                value={config.spam_time_sec}
                onChange={e => setConfig({ ...config, spam_time_sec: parseInt(e.target.value, 10) || 5 })}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Evaluation interval used to monitor member message frequency.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Safeguards & Content Scanning Card */}
      <Card>
        <CardHeader>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Scan size={20} color="#10b981" />
            <div>
              <CardTitle>Content Safeguards & Image Filtering</CardTitle>
              <CardDescription>
                Heuristic image scanning, phishing detection, and mass user or role ping shields.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)'
          }}>
            <Toggle
              checked={config.image_scan_enabled}
              onChange={val => setConfig({ ...config, image_scan_enabled: val })}
              label="Automated Image & Attachment Scanner"
              description="Scans incoming image uploads for explicit content, scam QR overlays, and graphic material."
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Mass Mention Threshold
              </label>
              <input
                type="number"
                min="3"
                max="50"
                className="form-input"
                value={config.mass_mention_limit}
                onChange={e => setConfig({ ...config, mass_mention_limit: parseInt(e.target.value, 10) || 5 })}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Blocks and deletes messages pinging more than this number of members or roles.
              </p>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Incident Audit Log Channel
              </label>
              <Select
                value={config.log_channel_id || ''}
                onChange={v => setConfig({ ...config, log_channel_id: v })}
                options={channelOptions}
                placeholder="Select an incident log channel..."
                searchable
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Target channel where auto-deleted violations and rate warnings will be logged.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Anti-Nuke Defense Engine Card */}
      <Card style={{ border: '1px solid rgba(239, 68, 68, 0.3)', background: 'linear-gradient(180deg, rgba(239, 68, 68, 0.04) 0%, rgba(15, 23, 42, 0) 100%)' }}>
        <CardHeader>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <ShieldAlert size={22} color="#ef4444" />
              <div>
                <CardTitle style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  Anti-Nuke Defense Engine
                  <Badge variant={antinuke.enabled ? 'success' : 'neutral'}>
                    {antinuke.enabled ? (antinuke.strict_mode ? '⚡ ULTRA-STRICT LOCKDOWN' : 'ACTIVE') : 'DISABLED'}
                  </Badge>
                </CardTitle>
                <CardDescription>
                  Autonomous real-time anti-raid shield against channel nukes, role stripping, and mass bans.
                </CardDescription>
              </div>
            </div>
            <Button
              variant="primary"
              onClick={handleSaveAntinuke}
              loading={antinukeSaving}
              style={{ background: '#ef4444', borderColor: '#dc2626' }}
            >
              {antinukeSaved ? (
                <>
                  <CheckCircle2 size={16} /> Saved!
                </>
              ) : (
                <>
                  <Lock size={16} /> Save Anti-Nuke Shield
                </>
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '14px' }}>
            <div style={{
              padding: '16px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)'
            }}>
              <Toggle
                checked={antinuke.enabled}
                onChange={val => setAntinuke({ ...antinuke, enabled: val })}
                label="Master Anti-Nuke Engine"
                description="Monitors server audit logs and automatically neutralizes rogue admins or compromised accounts."
              />
            </div>

            <div style={{
              padding: '16px',
              borderRadius: 'var(--radius-md)',
              background: antinuke.strict_mode ? 'rgba(239, 68, 68, 0.08)' : 'var(--bg-surface)',
              border: antinuke.strict_mode ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid var(--border)'
            }}>
              <Toggle
                checked={antinuke.strict_mode}
                onChange={val => setAntinuke({ ...antinuke, strict_mode: val })}
                label="⚡ Strict Lockdown (Instant Quarantine on 1 Delete)"
                description="Immediately freezes & timeouts rogue admins on their 1st unauthorized channel or role deletion."
              />
            </div>
          </div>

          <div style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)'
          }}>
            <Toggle
              checked={antinuke.anti_bot}
              onChange={val => setAntinuke({ ...antinuke, anti_bot: val })}
              label="Anti-Bot Gatekeeper"
              description="Automatically kicks unauthorized bots added by non-whitelisted members and penalizes the inviter."
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Punishment Action
              </label>
              <Select
                value={antinuke.action}
                onChange={v => setAntinuke({ ...antinuke, action: v })}
                options={[
                  { value: 'strip_roles', label: '🛡️ Strip All Roles + 28d Quarantine Timeout (Recommended)' },
                  { value: 'ban', label: '🔨 Permanent Ban from Server' },
                  { value: 'kick', label: '👢 Kick from Server' },
                ]}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Action executed against rogue executors when threshold or strict trigger trips.
              </p>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Channel Deletion Threshold
              </label>
              <input
                type="number"
                min="1"
                max="20"
                className="form-input"
                disabled={antinuke.strict_mode}
                value={antinuke.strict_mode ? 1 : antinuke.channel_delete_limit}
                onChange={e => setAntinuke({ ...antinuke, channel_delete_limit: parseInt(e.target.value, 10) || 1 })}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                {antinuke.strict_mode ? 'Locked to 1 in Strict Lockdown mode.' : 'Maximum deletions allowed within evaluation window.'}
              </p>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Role Deletion Threshold
              </label>
              <input
                type="number"
                min="1"
                max="20"
                className="form-input"
                disabled={antinuke.strict_mode}
                value={antinuke.strict_mode ? 1 : antinuke.role_delete_limit}
                onChange={e => setAntinuke({ ...antinuke, role_delete_limit: parseInt(e.target.value, 10) || 1 })}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                {antinuke.strict_mode ? 'Locked to 1 in Strict Lockdown mode.' : 'Maximum role deletions allowed before punishment.'}
              </p>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Mass Ban Threshold
              </label>
              <input
                type="number"
                min="1"
                max="30"
                className="form-input"
                value={antinuke.ban_limit}
                onChange={e => setAntinuke({ ...antinuke, ban_limit: parseInt(e.target.value, 10) || 2 })}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Bans allowed within evaluation window.
              </p>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Mass Kick Threshold
              </label>
              <input
                type="number"
                min="1"
                max="30"
                className="form-input"
                value={antinuke.kick_limit}
                onChange={e => setAntinuke({ ...antinuke, kick_limit: parseInt(e.target.value, 10) || 2 })}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Kicks allowed within evaluation window.
              </p>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Evaluation Window (Seconds)
              </label>
              <input
                type="number"
                min="5"
                max="60"
                className="form-input"
                value={antinuke.time_window_sec}
                onChange={e => setAntinuke({ ...antinuke, time_window_sec: parseInt(e.target.value, 10) || 20 })}
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Rolling audit window seconds (default: 20s).
              </p>
            </div>
          </div>

          {/* Whitelist Manager */}
          <div style={{
            padding: '18px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: 'var(--text-main)' }}>
                  Trusted Whitelist (Immune Staff & Bots)
                </h4>
                <p style={{ margin: '3px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                  Server Owner is permanently immune. Add co-owners, trusted bots, or senior admins here.
                </p>
              </div>
            </div>

            <form onSubmit={handleAddWhitelist} style={{ display: 'flex', gap: '8px', maxWidth: '500px' }}>
              <input
                type="text"
                placeholder="Enter User or Bot Discord ID (e.g. 123456789012345678)..."
                className="form-input"
                value={newWhitelistId}
                onChange={e => setNewWhitelistId(e.target.value)}
                style={{ flex: 1 }}
              />
              <Button type="submit" variant="secondary" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Plus size={15} /> Add ID
              </Button>
            </form>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '4px' }}>
              {whitelist.length === 0 ? (
                <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  No extra entities whitelisted. Only the server owner has bypass.
                </p>
              ) : (
                whitelist.map(item => (
                  <div
                    key={item.target_id}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '6px 12px',
                      borderRadius: '8px',
                      background: 'rgba(30, 41, 59, 0.8)',
                      border: '1px solid var(--border)',
                      fontSize: '13px',
                      color: 'var(--text-main)',
                      fontFamily: 'monospace'
                    }}
                  >
                    <span>ID: {item.target_id}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveWhitelist(item.target_id)}
                      title="Remove from Whitelist"
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: '#ef4444',
                        padding: '2px',
                        display: 'flex',
                        alignItems: 'center'
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Cross-Server Sync Modal */}
      <SyncModal
        isOpen={syncOpen}
        onClose={() => setSyncOpen(false)}
        currentGuildId={guildId}
        moduleName="security"
        moduleLabel="Security & Anti-Spam"
      />
    </div>
  );
}

export default Security;
