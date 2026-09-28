import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { ShieldCheck, Link2, MessageSquareWarning, Siren, UserX, CheckCircle2, AlertCircle, Info } from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import Skeleton from '../../components/Skeleton';

const box = { padding: '16px', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)', border: '1px solid var(--border)' };
const note = { margin: '8px 0 0', fontSize: '12.5px', color: 'var(--text-muted)', lineHeight: 1.5 };

function Notice({ tone = 'info', children }) {
  const warn = tone === 'warn';
  return (
    <div style={{
      display: 'flex', gap: '10px', padding: '12px 14px', borderRadius: 'var(--radius-md)', fontSize: '13px', lineHeight: 1.5,
      background: warn ? 'rgba(245, 158, 11, 0.08)' : 'rgba(88, 101, 242, 0.08)',
      border: `1px solid ${warn ? 'rgba(245, 158, 11, 0.25)' : 'rgba(88, 101, 242, 0.25)'}`,
      color: warn ? '#fcd34d' : 'var(--text-sub)',
    }}>
      {warn ? <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 2 }} /> : <Info size={16} style={{ flexShrink: 0, marginTop: 2 }} />}
      <div>{children}</div>
    </div>
  );
}

function Protection() {
  const { guildId } = useParams();
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  const [prot, setProt] = useState({ anti_link: false, anti_spam: false, anti_raid: false, log_channel_id: '' });
  const [hack, setHack] = useState({ enabled: true, log_channel_id: '' });

  const fetchData = useCallback(async () => {
    try {
      const [p, h, c] = await Promise.all([
        api.get(`/guilds/${guildId}/protection`),
        api.get(`/guilds/${guildId}/anti-hacked`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      setProt(p.data.config);
      setHack(h.data.config);
      setChannels(c.data.channels || []);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load protection settings');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = async () => {
    setError('');
    setSaving(true);
    try {
      await Promise.all([
        api.post(`/guilds/${guildId}/protection`, prot),
        api.post(`/guilds/${guildId}/anti-hacked`, hack),
      ]);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save protection settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" /><Skeleton height="260px" /><Skeleton height="200px" />
      </div>
    );
  }

  const channelOptions = [
    { value: '', label: 'No log channel' },
    ...channels.map(ch => ({ value: ch.id, label: `#${ch.name}` })),
  ];

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={ShieldCheck}
        title="Protection Suite"
        subtitle="Anti-link, anti-spam, raid lockdown and hacked-account defence — the same systems as /protection and /antihacked."
        actions={
          <Button variant="primary" size="sm" icon={CheckCircle2} loading={saving} onClick={handleSave}>
            {saved ? 'Saved!' : 'Save Protection'}
          </Button>
        }
      />

      {error && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px',
          borderRadius: 'var(--radius-md)', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.25)',
          color: '#f87171', fontSize: '13.5px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><AlertCircle size={17} /><span>{error}</span></div>
          <button onClick={() => setError('')} style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '16px' }}>✕</button>
        </div>
      )}

      <Card>
        <CardHeader>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ShieldCheck size={20} color="var(--primary)" />
            <div>
              <CardTitle>Server Protection</CardTitle>
              <CardDescription>Members with Manage Messages are exempt from anti-link and anti-spam.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={box}>
            <Toggle
              checked={!!prot.anti_link}
              onChange={v => setProt({ ...prot, anti_link: v })}
              label="Anti-Link"
              description="Deletes messages containing links or Discord invites and posts a short warning that disappears after 5 seconds."
            />
          </div>
          <div style={box}>
            <Toggle
              checked={!!prot.anti_spam}
              onChange={v => setProt({ ...prot, anti_spam: v })}
              label="Anti-Spam"
              description="5 messages in 3 seconds → 5-minute timeout.  3 images in 5 seconds → images deleted and 10-minute timeout."
            />
          </div>
          <div style={box}>
            <Toggle
              checked={!!prot.anti_raid}
              onChange={v => setProt({ ...prot, anti_raid: v })}
              label="Anti-Raid Lockdown"
              description="10 members joining within 10 seconds → removes Send Messages from @everyone."
            />
            {prot.anti_raid && (
              <div style={{ marginTop: 12 }}>
                <Notice tone="warn">
                  The lockdown is <b>not lifted automatically</b>. After a raid, restore Send Messages for @everyone yourself in
                  Server Settings → Roles → @everyone.
                </Notice>
              </div>
            )}
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Protection Alert Channel
            </label>
            <Select
              value={prot.log_channel_id || ''}
              onChange={v => setProt({ ...prot, log_channel_id: v })}
              options={channelOptions}
              placeholder="Select an alert channel..."
              searchable
            />
            <p style={note}>Every anti-link, anti-spam and anti-raid action is logged here.</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <UserX size={20} color="#ef4444" />
            <div>
              <CardTitle>Anti-Hacked Account Protection</CardTitle>
              <CardDescription>Stops compromised accounts that blast scam images or mass pings across channels.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={box}>
            <Toggle
              checked={!!hack.enabled}
              onChange={v => setHack({ ...hack, enabled: v })}
              label="Enable Anti-Hacked Protection"
              description="Watches for image posts and @everyone / role pings spread across several channels within 20 seconds."
            />
          </div>

          <Notice>
            <b>Triggers:</b> a normal member posting spam in <b>2</b> channels, or staff (anyone with a powerful permission) in <b>3</b> channels, within 20 seconds.
            <br /><b>Response:</b> the spam is deleted, roles with powerful permissions are removed (only roles below the bot's top role), and the member is timed out for 25 minutes.
          </Notice>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Anti-Hacked Log Channel
            </label>
            <Select
              value={hack.log_channel_id || ''}
              onChange={v => setHack({ ...hack, log_channel_id: v })}
              options={channelOptions}
              placeholder="Select a log channel..."
              searchable
            />
            <p style={note}>Incident reports (who was caught, roles removed, messages deleted) are posted here.</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default Protection;
