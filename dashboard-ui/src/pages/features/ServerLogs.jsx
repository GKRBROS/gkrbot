import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

function ServerLogs() {
  const { guildId } = useParams();
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [enabled, setEnabled] = useState(true);
  const [logChannelId, setLogChannelId] = useState('');
  const [categoryChannels, setCategoryChannels] = useState({});
  const [enabledEvents, setEnabledEvents] = useState([]);
  const [categories, setCategories] = useState([]);
  const [eventCategories, setEventCategories] = useState({});

  const fetchData = async () => {
    try {
      setLoading(true);
      const [logsRes, chRes] = await Promise.all([
        api.get(`/guilds/${guildId}/server-logs`),
        api.get(`/guilds/${guildId}/channels`),
      ]);

      const { config, categories: cats, event_categories } = logsRes.data;
      setEnabled(config.enabled ?? true);
      setLogChannelId(config.log_channel_id ? String(config.log_channel_id) : '');
      setCategoryChannels(config.category_channels || {});
      setEnabledEvents(config.enabled_events || []);
      setCategories(cats || []);
      setEventCategories(event_categories || {});
      setChannels(chRes.data.channels || []);
      setError('');
    } catch (err) {
      console.error('Failed to load server logs config', err);
      setError(err.response?.data?.error || 'Failed to load server logs config');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const handleSave = async () => {
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/server-logs`, {
        log_channel_id: logChannelId || null,
        enabled,
        enabled_events: enabledEvents,
        category_channels: categoryChannels,
      });
      setSuccess('📋 Server log routing and event configuration saved successfully!');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save server logs config');
    } finally {
      setSaving(false);
    }
  };

  const handleCategoryChannelChange = (catKey, chId) => {
    setCategoryChannels({
      ...categoryChannels,
      [catKey]: chId || null,
    });
  };

  const toggleEvent = (eventKey) => {
    if (enabledEvents.includes(eventKey)) {
      setEnabledEvents(enabledEvents.filter(e => e !== eventKey));
    } else {
      setEnabledEvents([...enabledEvents, eventKey]);
    }
  };

  const toggleAllCategoryEvents = (catKey, enable) => {
    const catEvents = eventCategories[catKey] || [];
    if (enable) {
      const merged = Array.from(new Set([...enabledEvents, ...catEvents]));
      setEnabledEvents(merged);
    } else {
      setEnabledEvents(enabledEvents.filter(e => !catEvents.includes(e)));
    }
  };

  const channelOptions = [{ value: '', label: 'Default (Use Primary Fallback)' }, ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))];
  const primaryChannelOptions = [{ value: '', label: 'None' }, ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))];

  if (loading) {
    return <div className="feature-page" style={{ padding: '40px', textAlign: 'center' }}>Loading Server Logs Configuration...</div>;
  }

  return (
    <div className="feature-page">
      <div className="feature-header">
        <div>
          <h1 className="feature-title">📋 Server Audit Logs</h1>
          <p className="feature-desc">Configure dedicated channels for member, message, voice, role, security and command audit logs.</p>
        </div>
        <button className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : '💾 Save Log Configuration'}
        </button>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span>{error}</span>
          <button className="btn-secondary" onClick={() => setError('')} style={{ padding: '2px 8px' }}>✕</button>
        </div>
      )}

      {success && (
        <div className="alert alert-success" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span>{success}</span>
          <button className="btn-secondary" onClick={() => setSuccess('')} style={{ padding: '2px 8px' }}>✕</button>
        </div>
      )}

      {/* Master Settings */}
      <div className="dashboard-card" style={{ padding: '24px', marginBottom: '24px' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>General Logging Setup</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '20px', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontSize: '15px', fontWeight: '600' }}>
            <input
              type="checkbox"
              checked={enabled}
              onChange={e => setEnabled(e.target.checked)}
            />
            <span>Enable Event Logging</span>
          </label>

          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">Primary Fallback Log Channel</label>
            <Select
              value={logChannelId}
              onChange={setLogChannelId}
              options={primaryChannelOptions}
              placeholder="Select default log channel..."
              searchable
            />
          </div>
        </div>
      </div>

      {/* Category Routing Cards */}
      <div style={{ marginBottom: '24px' }}>
        <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: 'var(--text-main)' }}>
          Category Dedicated Routing & Events
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
          {categories.map(cat => {
            const catEvents = eventCategories[cat.key] || [];
            const activeInCat = catEvents.filter(e => enabledEvents.includes(e)).length;
            const currentCatChannel = categoryChannels[cat.key] || '';

            return (
              <div key={cat.key} className="dashboard-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <h4 style={{ margin: 0, fontSize: '16px', color: 'var(--text-main)' }}>{cat.title}</h4>
                    <span className="badge badge-primary" style={{ fontSize: '11px' }}>
                      {activeInCat}/{catEvents.length} Events
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 14px', lineHeight: 1.4 }}>
                    {cat.desc}
                  </p>

                  <div className="form-group" style={{ marginBottom: '16px' }}>
                    <label className="form-label" style={{ fontSize: '12px' }}>Destination Channel</label>
                    <Select
                      value={currentCatChannel}
                      onChange={val => handleCategoryChannelChange(cat.key, val)}
                      options={channelOptions}
                      placeholder="Default (Use Primary Fallback)"
                      searchable
                    />
                  </div>

                  {/* Event Toggles */}
                  <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)' }}>Events</span>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          type="button"
                          onClick={() => toggleAllCategoryEvents(cat.key, true)}
                          style={{ background: 'none', border: 'none', color: 'var(--primary)', fontSize: '11px', cursor: 'pointer', fontWeight: '600', padding: 0 }}
                        >
                          All
                        </button>
                        <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>•</span>
                        <button
                          type="button"
                          onClick={() => toggleAllCategoryEvents(cat.key, false)}
                          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '11px', cursor: 'pointer', padding: 0 }}
                        >
                          None
                        </button>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
                      {catEvents.map(evt => (
                        <label key={evt} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={enabledEvents.includes(evt)}
                            onChange={() => toggleEvent(evt)}
                          />
                          <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                            {evt.replace(`${cat.key}_`, '').replace('_', ' ')}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default ServerLogs;
