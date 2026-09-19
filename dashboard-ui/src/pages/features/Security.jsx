import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  ShieldCheck,
  Zap,
  Scan,
  Share2,
  CheckCircle2,
  AlertCircle,
  Hash,
  Users,
  Clock,
  MessageSquare
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
