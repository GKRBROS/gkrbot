import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';

function Welcome() {
  const { guildId } = useParams();
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [config, setConfig] = useState({
    enabled: false,
    channel_id: '',
    message: 'Welcome to the server, {user}! 🎉',
    leave_enabled: false,
    leave_channel_id: '',
    leave_message: '**{user}** left the server.',
    leave_image_url: '',
  });

  const fetchData = useCallback(async () => {
    try {
      const [welcomeRes, channelsRes] = await Promise.all([
        api.get(`/guilds/${guildId}/welcome`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      if (welcomeRes.data.config) {
        setConfig({
          enabled: welcomeRes.data.config.enabled ?? false,
          channel_id: welcomeRes.data.config.channel_id || '',
          message: welcomeRes.data.config.message || 'Welcome to the server, {user}! 🎉',
          leave_enabled: welcomeRes.data.config.leave_enabled ?? false,
          leave_channel_id: welcomeRes.data.config.leave_channel_id || '',
          leave_message: welcomeRes.data.config.leave_message || '**{user}** left the server.',
          leave_image_url: welcomeRes.data.config.leave_image_url || '',
        });
      }
      setChannels(channelsRes.data.channels || []);
    } catch (err) {
      console.error('Failed to fetch welcome config', err);
    }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await api.post(`/guilds/${guildId}/welcome`, config);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save welcome config');
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '300px' }}></div>
      </div>
    );
  }

  const PLACEHOLDERS = [
    { label: '{user}', desc: 'Mentions the new member' },
    { label: '{username}', desc: "Member's display name" },
    { label: '{server}', desc: 'Server name' },
    { label: '{count}', desc: 'Current member count' },
  ];

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">👋 Welcome Messages</h1>
        <p className="page-subtitle">Configure the welcome message sent when a new member joins.</p>
      </div>

      <form onSubmit={handleSave} className="stagger">
        {error && <div className="alert alert-error">{error}</div>}

        {/* Enable / Disable Toggle */}
        <div className="toggle-wrapper" style={{ marginBottom: '24px' }}>
          <div>
            <div style={{ fontWeight: '600', marginBottom: '4px', fontSize: '15px' }}>Enable Welcome Messages</div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Send a message when a new member joins the server.</div>
          </div>
          <button
            type="button"
            className={`toggle ${config.enabled ? 'active' : ''}`}
            onClick={() => setConfig(c => ({ ...c, enabled: !c.enabled }))}
            aria-label="Toggle Welcome Messages"
          ></button>
        </div>

        <div className="grid-2">
          {/* Editor Panel */}
          <div className="glass-panel" style={{ padding: '24px', opacity: config.enabled ? 1 : 0.5, pointerEvents: config.enabled ? 'auto' : 'none', transition: 'all 0.3s' }}>
            <div className="form-group">
              <label className="form-label">Welcome Channel</label>
              <select
                className="input-field"
                value={config.channel_id}
                onChange={e => setConfig({ ...config, channel_id: e.target.value })}
                required={config.enabled}
              >
                <option value="" disabled>Select a channel...</option>
                {channels.map(ch => (
                  <option key={ch.id} value={ch.id}>#{ch.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Message Content</label>
              <textarea
                className="input-field"
                rows={4}
                value={config.message}
                onChange={e => setConfig({ ...config, message: e.target.value })}
                placeholder="Welcome to {server}, {user}!"
                required={config.enabled}
                style={{ fontFamily: 'monospace' }}
              />
            </div>
            
            <div style={{ marginTop: '16px' }}>
              <label className="form-label">Available Variables</label>
              <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
                {PLACEHOLDERS.map(p => (
                  <span key={p.label} className="badge badge-primary" title={p.desc} style={{ cursor: 'help' }}>
                    {p.label}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Live Preview Panel */}
          <div className="glass-panel flex flex-col" style={{ padding: '24px', background: 'var(--bg-surface)' }}>
            <h3 className="section-title" style={{ marginBottom: '16px', border: 'none', padding: 0 }}>
              👁️ Live Preview
            </h3>
            
            <div style={{ 
              background: '#36393f', 
              borderRadius: '8px', 
              padding: '16px',
              flex: 1,
              display: 'flex',
              gap: '16px'
            }}>
              <div style={{
                width: '40px', height: '40px', borderRadius: '50%',
                background: 'linear-gradient(135deg, var(--primary), var(--accent))',
                flexShrink: 0
              }}></div>
              <div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '4px' }}>
                  <span style={{ fontWeight: '500', color: 'white', fontSize: '15px' }}>GKR Bot</span>
                  <span style={{ fontSize: '10px', background: '#5865F2', padding: '2px 4px', borderRadius: '3px', textTransform: 'uppercase' }}>Bot</span>
                  <span style={{ fontSize: '12px', color: '#72767d' }}>Today at 12:00 PM</span>
                </div>
                <div style={{ color: '#dcddde', fontSize: '14px', lineHeight: '1.4', whiteSpace: 'pre-wrap' }}>
                  {config.message
                    .replace(/{user}/g, '<@NewUser>')
                    .replace(/{username}/g, 'NewUser')
                    .replace(/{server}/g, 'Your Server')
                    .replace(/{count}/g, '42') || 'Start typing to preview...'}
                </div>
              </div>
            </div>

            <div className="flex justify-end mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
              <button type="submit" className={`btn ${saved ? 'btn-success' : 'btn-primary'}`} disabled={saving}>
                {saving ? 'Saving...' : saved ? '✅ Saved!' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>

        <div style={{ marginTop: '48px' }}></div>

        {/* Leave Messages Toggle */}
        <div className="toggle-wrapper" style={{ marginBottom: '24px' }}>
          <div>
            <div style={{ fontWeight: '600', marginBottom: '4px', fontSize: '15px' }}>Enable Leave Messages</div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Send a message when a member leaves the server.</div>
          </div>
          <button
            type="button"
            className={`toggle ${config.leave_enabled ? 'active' : ''}`}
            onClick={() => setConfig(c => ({ ...c, leave_enabled: !c.leave_enabled }))}
            aria-label="Toggle Leave Messages"
          ></button>
        </div>

        <div className="grid-2">
          {/* Leave Editor Panel */}
          <div className="glass-panel" style={{ padding: '24px', opacity: config.leave_enabled ? 1 : 0.5, pointerEvents: config.leave_enabled ? 'auto' : 'none', transition: 'all 0.3s' }}>
            <div className="form-group">
              <label className="form-label">Leave Channel</label>
              <select
                className="input-field"
                value={config.leave_channel_id}
                onChange={e => setConfig({ ...config, leave_channel_id: e.target.value })}
                required={config.leave_enabled}
              >
                <option value="" disabled>Select a channel...</option>
                {channels.map(ch => (
                  <option key={ch.id} value={ch.id}>#{ch.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Leave Message Content</label>
              <textarea
                className="input-field"
                rows={3}
                value={config.leave_message}
                onChange={e => setConfig({ ...config, leave_message: e.target.value })}
                placeholder="**{user}** left the server."
                required={config.leave_enabled}
                style={{ fontFamily: 'monospace' }}
              />
            </div>
            
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Custom Image URL (Optional)</label>
              <input
                type="text"
                className="input-field"
                value={config.leave_image_url}
                onChange={e => setConfig({ ...config, leave_image_url: e.target.value })}
                placeholder="https://example.com/image.gif"
              />
            </div>
          </div>

          {/* Leave Preview Panel */}
          <div className="glass-panel flex flex-col" style={{ padding: '24px', background: 'var(--bg-surface)' }}>
            <h3 className="section-title" style={{ marginBottom: '16px', border: 'none', padding: 0 }}>
              👁️ Leave Preview
            </h3>
            
            <div style={{ 
              background: '#36393f', 
              borderRadius: '8px', 
              padding: '16px',
              flex: 1,
              display: 'flex',
              gap: '16px'
            }}>
              <div style={{
                width: '40px', height: '40px', borderRadius: '50%',
                background: 'linear-gradient(135deg, var(--primary), var(--accent))',
                flexShrink: 0
              }}></div>
              <div style={{ width: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '8px' }}>
                  <span style={{ fontWeight: '500', color: 'white', fontSize: '15px' }}>GKR Bot</span>
                  <span style={{ fontSize: '10px', background: '#5865F2', padding: '2px 4px', borderRadius: '3px', textTransform: 'uppercase' }}>Bot</span>
                </div>
                
                <div style={{ background: '#2b2d31', borderRadius: '4px', borderLeft: '4px solid #2b2d31', padding: '12px' }}>
                   <div style={{ fontWeight: 'bold', color: 'white', marginBottom: '8px' }}>MEMBER LEFT</div>
                   <div style={{ color: '#dcddde', fontSize: '14px', lineHeight: '1.4', whiteSpace: 'pre-wrap' }}>
                     {config.leave_message
                       .replace(/{user}/g, 'LeavingUser')
                       .replace(/{username}/g, 'LeavingUser')
                       .replace(/{server}/g, 'Your Server')
                       .replace(/{count}/g, '41') || 'Start typing to preview...'}
                   </div>
                   {config.leave_image_url && (
                     <div style={{ marginTop: '12px' }}>
                        <img src={config.leave_image_url} alt="Leave visual" style={{ maxWidth: '100%', maxHeight: '200px', borderRadius: '4px' }} onError={(e) => e.target.style.display = 'none'} />
                     </div>
                   )}
                </div>
              </div>
            </div>

            <div className="flex justify-end mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
              <button type="submit" className={`btn ${saved ? 'btn-success' : 'btn-primary'}`} disabled={saving}>
                {saving ? 'Saving...' : saved ? '✅ Saved!' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>

      </form>
    </div>
  );
}

export default Welcome;
