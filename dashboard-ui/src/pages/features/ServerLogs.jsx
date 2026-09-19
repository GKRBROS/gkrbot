import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  ScrollText,
  Save,
  CheckCircle2,
  AlertCircle,
  Hash,
  Layers,
  SlidersHorizontal,
  Check,
  X
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import Badge from '../../components/Badge';
import Skeleton from '../../components/Skeleton';

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
      setSuccess('Server log routing and event tracking rules saved successfully!');
      setTimeout(() => setSuccess(''), 3000);
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

  const channelOptions = [
    { value: '', label: 'Default (Use Primary Fallback Channel)' },
    ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))
  ];

  const primaryChannelOptions = [
    { value: '', label: 'None (Disabled)' },
    ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))
  ];

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="120px" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px' }}>
          <Skeleton height="260px" />
          <Skeleton height="260px" />
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={ScrollText}
        title="Server Audit Logs"
        subtitle="Route dedicated channels for member, message, voice, role, security, and command audit records."
        actions={
          <Button
            variant="primary"
            size="sm"
            icon={Save}
            loading={saving}
            onClick={handleSave}
          >
            Save Log Configuration
          </Button>
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

      {/* Master Configuration Card */}
      <Card>
        <CardHeader>
          <CardTitle>Global Audit Logging Dispatcher</CardTitle>
          <CardDescription>
            Master enable switch and the default fallback Discord channel for all logging categories.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(280px, 1.5fr)', gap: '20px', alignItems: 'center' }}>
            <div style={{
              padding: '14px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)'
            }}>
              <Toggle
                checked={enabled}
                onChange={setEnabled}
                label="Enable Audit Logging"
                description="When enabled, bot generates and dispatches embeds for configured server events."
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Primary Fallback Audit Channel
              </label>
              <Select
                value={logChannelId}
                onChange={setLogChannelId}
                options={primaryChannelOptions}
                placeholder="Select default log channel..."
                searchable
              />
              <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                Used when a specific category doesn't have its own dedicated channel assigned below.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Category Routing Cards Grid */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Category Dedicated Routing & Events
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Split different event types into separate channels to keep moderation streams organized.
            </p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
          {categories.map(cat => {
            const catEvents = eventCategories[cat.key] || [];
            const activeInCat = catEvents.filter(e => enabledEvents.includes(e)).length;
            const currentCatChannel = categoryChannels[cat.key] || '';

            return (
              <Card key={cat.key} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <CardContent style={{ padding: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-main)' }}>
                      {cat.title}
                    </h4>
                    <Badge variant={activeInCat > 0 ? 'primary' : 'neutral'} size="sm">
                      {activeInCat} / {catEvents.length} Active
                    </Badge>
                  </div>
                  <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', margin: '0 0 16px', lineHeight: 1.4 }}>
                    {cat.desc}
                  </p>

                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                      Dedicated Destination Channel
                    </label>
                    <Select
                      value={currentCatChannel}
                      onChange={val => handleCategoryChannelChange(cat.key, val)}
                      options={channelOptions}
                      placeholder="Default (Use Primary Fallback)"
                      searchable
                    />
                  </div>

                  {/* Event Toggles */}
                  <div style={{ borderTop: '1px solid var(--border)', paddingTop: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        Tracked Events
                      </span>
                      <div style={{ display: 'flex', gap: '10px', fontSize: '12px' }}>
                        <button
                          type="button"
                          onClick={() => toggleAllCategoryEvents(cat.key, true)}
                          style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', fontWeight: 600, padding: 0 }}
                        >
                          Select All
                        </button>
                        <span style={{ color: 'var(--border)' }}>|</span>
                        <button
                          type="button"
                          onClick={() => toggleAllCategoryEvents(cat.key, false)}
                          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}
                        >
                          Clear
                        </button>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                      {catEvents.map(evt => {
                        const isChecked = enabledEvents.includes(evt);
                        const label = evt.replace(`${cat.key}_`, '').replace(/_/g, ' ');
                        return (
                          <label
                            key={evt}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                              padding: '6px 8px',
                              borderRadius: 'var(--radius-sm)',
                              background: isChecked ? 'rgba(88, 101, 242, 0.08)' : 'var(--bg-surface)',
                              border: '1px solid var(--border)',
                              cursor: 'pointer',
                              fontSize: '12px',
                              color: isChecked ? 'var(--text-main)' : 'var(--text-muted)',
                              transition: 'all 120ms ease'
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => toggleEvent(evt)}
                              style={{ accentColor: 'var(--primary)' }}
                            />
                            <span style={{ textTransform: 'capitalize', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                              {label}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default ServerLogs;
