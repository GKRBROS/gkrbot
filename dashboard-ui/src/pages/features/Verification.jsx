import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { BadgeCheck, CheckCircle2, AlertCircle, Send, ExternalLink } from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Skeleton from '../../components/Skeleton';

const label = { display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' };
const note = { margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' };

function Verification() {
  const { guildId } = useParams();
  const [roles, setRoles] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  const [config, setConfig] = useState({ verified_role_id: '', log_channel_id: '', min_account_days: 0 });
  const [savedRole, setSavedRole] = useState(''); // role the bot is actually using right now

  const [panelChannel, setPanelChannel] = useState('');
  const [panelTitle, setPanelTitle] = useState('');
  const [panelDesc, setPanelDesc] = useState('');
  const [posting, setPosting] = useState(false);
  const [posted, setPosted] = useState(null); // message url

  const fetchData = useCallback(async () => {
    try {
      const [v, r, c] = await Promise.all([
        api.get(`/guilds/${guildId}/verification`),
        api.get(`/guilds/${guildId}/roles`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      setConfig(v.data.config);
      setSavedRole(v.data.config.verified_role_id || '');
      setRoles(r.data.roles || []);
      setChannels(c.data.channels || []);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load verification settings');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = async () => {
    setError('');
    setSaving(true);
    try {
      await api.post(`/guilds/${guildId}/verification`, config);
      setSavedRole(config.verified_role_id || '');
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save verification settings');
    } finally {
      setSaving(false);
    }
  };

  const handlePost = async () => {
    setError('');
    setPosted(null);
    if (!panelChannel) { setError('Choose a channel to post the panel in.'); return; }
    setPosting(true);
    try {
      const res = await api.post(`/guilds/${guildId}/verification/panel`, {
        channel_id: panelChannel, title: panelTitle.trim(), description: panelDesc.trim(),
      });
      setPosted(res.data.message_url || true);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to post the verification panel');
    } finally {
      setPosting(false);
    }
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" /><Skeleton height="240px" /><Skeleton height="240px" />
      </div>
    );
  }

  const roleOptions = [{ value: '', label: 'No verified role' }, ...roles.map(r => ({ value: r.id, label: r.name }))];
  const channelOptions = [{ value: '', label: 'No log channel' }, ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))];
  const panelChannelOptions = channels.map(c => ({ value: c.id, label: `#${c.name}` }));
  const unsaved = (config.verified_role_id || '') !== savedRole;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={BadgeCheck}
        title="Verification"
        subtitle="Gate your server behind a one-click “Verify Me” button that grants a role."
        actions={
          <Button variant="primary" size="sm" icon={CheckCircle2} loading={saving} onClick={handleSave}>
            {saved ? 'Saved!' : 'Save Verification'}
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
          <div>
            <CardTitle>Verification Rules</CardTitle>
            <CardDescription>Who gets which role, and how new an account is allowed to be.</CardDescription>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '18px' }}>
          <div>
            <label style={label}>Verified Role</label>
            <Select
              value={config.verified_role_id || ''}
              onChange={v => setConfig({ ...config, verified_role_id: v })}
              options={roleOptions}
              placeholder="Select the role members receive..."
              searchable
            />
            <p style={note}>Must sit below the bot's top role, and can't have Administrator.</p>
          </div>
          <div>
            <label style={label}>Minimum Account Age (days)</label>
            <input
              type="number" min="0" max="365" className="form-input"
              value={config.min_account_days}
              onChange={e => setConfig({ ...config, min_account_days: parseInt(e.target.value, 10) || 0 })}
            />
            <p style={note}>Newer Discord accounts are refused. 0 = no age requirement.</p>
          </div>
          <div>
            <label style={label}>Verification Log Channel</label>
            <Select
              value={config.log_channel_id || ''}
              onChange={v => setConfig({ ...config, log_channel_id: v })}
              options={channelOptions}
              placeholder="Select a log channel..."
              searchable
            />
            <p style={note}>Each successful verification is logged here.</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Send size={20} color="var(--primary)" />
            <div>
              <CardTitle>Post the Verification Panel</CardTitle>
              <CardDescription>Sends the embed with the “✅ Verify Me” button into a channel — same as /verify setup.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {(!savedRole || unsaved) && (
            <div style={{ padding: '12px 14px', borderRadius: 'var(--radius-md)', background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.25)', color: '#fcd34d', fontSize: '13px' }}>
              {!savedRole ? 'Choose a verified role and click “Save Verification” before posting a panel.' : 'You changed the verified role — save first so the panel uses it.'}
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '18px' }}>
            <div>
              <label style={label}>Channel</label>
              <Select value={panelChannel} onChange={setPanelChannel} options={panelChannelOptions} placeholder="Where should the panel go?" searchable />
            </div>
            <div>
              <label style={label}>Panel Title (optional)</label>
              <input type="text" className="form-input" value={panelTitle} maxLength={100} placeholder="✅  Member Verification" onChange={e => setPanelTitle(e.target.value)} />
            </div>
          </div>
          <div>
            <label style={label}>Panel Message (optional)</label>
            <textarea
              className="form-input" rows={4} maxLength={1500} value={panelDesc}
              placeholder="Leave blank to use the default welcome text."
              onChange={e => setPanelDesc(e.target.value)}
              style={{ resize: 'vertical' }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <Button variant="primary" size="sm" icon={Send} loading={posting} onClick={handlePost} disabled={!savedRole || unsaved}>
              Post Panel
            </Button>
            {posted && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#34d399', fontSize: 13.5, fontWeight: 600 }}>
                <CheckCircle2 size={15} /> Panel posted!
                {typeof posted === 'string' && (
                  <a href={posted} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    View <ExternalLink size={12} />
                  </a>
                )}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default Verification;
