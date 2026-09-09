import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync } from '../../sync';

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

  const fetchData = useCallback(async () => {
    try {
      const [secRes, chanRes] = await Promise.all([
        api.get(`/guilds/${guildId}/security`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      if (secRes.data.config) {
        setConfig(secRes.data.config);
      }
      setChannels(chanRes.data.channels || []);
    } catch (err) {
      console.error('Failed to load security config', err);
    }
    setLoading(false);
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSave = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await api.post(`/guilds/${guildId}/security`, withSync(config));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save security configuration');
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '320px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="page-header flex justify-between items-center" style={{ flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 className="page-title">
            <span>🛡️</span> Security & Anti-Spam
          </h2>
          <p className="page-subtitle">
            Configure automated anti-spam protection, mass-mention safeguards, and image scanning.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
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
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn btn-primary"
            style={{ minWidth: '130px' }}
          >
            {saving ? 'Saving...' : saved ? '✓ Saved!' : 'Save Changes'}
          </button>
        </div>
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

      {/* Main Settings Form */}
      <form onSubmit={handleSave}>
        <div className="card glass-panel" style={{ marginBottom: '24px' }}>
          <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', color: 'var(--text-main)' }}>
            ⚡ Anti-Spam & Rate Limiting
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Anti Spam Toggle */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>Enable Anti-Spam Shield</div>
                <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                  Automatically detects rapid message flooding and triggers warnings/mutes.
                </div>
              </div>
              <input
                type="checkbox"
                checked={config.anti_spam_enabled}
                onChange={e => setConfig({ ...config, anti_spam_enabled: e.target.checked })}
                style={{ width: '20px', height: '20px', accentColor: 'var(--primary)', cursor: 'pointer' }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
              <div className="form-group">
                <label className="form-label">Message Limit</label>
                <input
                  type="number"
                  min="2"
                  max="50"
                  className="form-control"
                  value={config.spam_msg_limit}
                  onChange={e => setConfig({ ...config, spam_msg_limit: parseInt(e.target.value) || 5 })}
                />
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
                  Max messages allowed within the time window.
                </span>
              </div>

              <div className="form-group">
                <label className="form-label">Time Window (Seconds)</label>
                <input
                  type="number"
                  min="1"
                  max="60"
                  className="form-control"
                  value={config.spam_time_sec}
                  onChange={e => setConfig({ ...config, spam_time_sec: parseInt(e.target.value) || 5 })}
                />
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
                  Interval used to count incoming messages.
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Safeguards & Scanning */}
        <div className="card glass-panel" style={{ marginBottom: '24px' }}>
          <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', color: 'var(--text-main)' }}>
            🛡️ Content Protection & Image Scanning
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Image Scan Toggle */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>AI / Heuristic Image Scanner</div>
                <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                  Scans image attachments for NSFW, gore, and crypto scam overlays, auto-deleting infractions.
                </div>
              </div>
              <input
                type="checkbox"
                checked={config.image_scan_enabled}
                onChange={e => setConfig({ ...config, image_scan_enabled: e.target.checked })}
                style={{ width: '20px', height: '20px', accentColor: 'var(--primary)', cursor: 'pointer' }}
              />
            </div>

            {/* Mass Mention Limit */}
            <div className="form-group" style={{ maxWidth: '320px' }}>
              <label className="form-label">Mass Mention Threshold</label>
              <input
                type="number"
                min="3"
                max="50"
                className="form-control"
                value={config.mass_mention_limit}
                onChange={e => setConfig({ ...config, mass_mention_limit: parseInt(e.target.value) || 5 })}
              />
              <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
                Flags messages mentioning more than this many users or roles.
              </span>
            </div>

            {/* Log Channel */}
            <div className="form-group" style={{ maxWidth: '420px' }}>
              <label className="form-label">Security Incident Log Channel</label>
              <select
                className="form-control"
                value={config.log_channel_id || ''}
                onChange={e => setConfig({ ...config, log_channel_id: e.target.value })}
              >
                <option value="">-- Disabled (No Logging) --</option>
                {channels.map(ch => (
                  <option key={ch.id} value={ch.id}>#{ch.name}</option>
                ))}
              </select>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
                Where warnings, deleted spam, and scan triggers will be logged.
              </span>
            </div>
          </div>
        </div>
      </form>

      {/* Sync Modal */}
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
