import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Megaphone,
  Send,
  Webhook,
  AlertCircle,
  CheckCircle2,
  Palette,
  Hash,
  Bell,
  Trash2,
  ExternalLink
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import { Select } from '../../components/Select';
import Skeleton from '../../components/Skeleton';
import { useBotName } from '../../BotContext';

const COLOR_PRESETS = [
  '#8A2BE2', // Purple / GKR Theme
  '#5865F2', // Discord Blurple
  '#57F287', // Green
  '#FEE75C', // Yellow
  '#ED4245', // Red
  '#EB459E', // Pink
  '#FF7F50', // Coral / Orange
  '#00BFFF', // Deep Sky Blue
  '#FFFFFF', // White
  '#23272A', // Dark Slate
];

export default function Announce() {
  const { guildId } = useParams();
  const botName = useBotName() || 'GKR Bot';

  const [channels, setChannels] = useState([]);
  const [webhooks, setWebhooks] = useState({});
  const [loading, setLoading] = useState(true);

  // Form State
  const [selectedChannel, setSelectedChannel] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [color, setColor] = useState('#8A2BE2');
  const [ping, setPing] = useState('none');

  // Status
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Webhook Setup State
  const [webhookChannel, setWebhookChannel] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [savingWebhook, setSavingWebhook] = useState(false);
  const [webhookError, setWebhookError] = useState('');
  const [webhookSuccess, setWebhookSuccess] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const [chanRes, hookRes] = await Promise.all([
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/announce/webhook`).catch(() => ({ data: { webhooks: {} } })),
      ]);

      const chList = chanRes.data.channels || [];
      setChannels(chList);
      if (chList.length > 0) {
        setSelectedChannel(prev => prev || chList[0].id);
        setWebhookChannel(prev => prev || chList[0].id);
      }
      setWebhooks(hookRes.data?.webhooks || {});
      setError('');
    } catch (err) {
      console.error('Failed to load announce data', err);
      setError(err.response?.data?.error || 'Failed to load channels.');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSend = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!selectedChannel) {
      return setError('Please choose a destination channel.');
    }
    if (!body.trim()) {
      return setError('Announcement message cannot be empty.');
    }

    setSending(true);
    try {
      await api.post(`/guilds/${guildId}/announce`, {
        channel_id: selectedChannel,
        title: title.trim(),
        body: body.trim(),
        color,
        ping,
      });

      setSuccess('Announcement sent successfully! 🎉');
      setTitle('');
      setBody('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to send announcement.');
    } finally {
      setSending(false);
    }
  };

  const handleSaveWebhook = async (e) => {
    e.preventDefault();
    setWebhookError('');
    setWebhookSuccess('');

    if (!webhookChannel) {
      return setWebhookError('Select a channel first.');
    }

    setSavingWebhook(true);
    try {
      await api.post(`/guilds/${guildId}/announce/webhook`, {
        channel_id: webhookChannel,
        webhook_url: webhookUrl.trim(),
      });

      setWebhookSuccess(webhookUrl.trim() ? 'Webhook configured for channel!' : 'Webhook removed for channel.');
      setWebhookUrl('');
      // Refresh webhooks map
      const res = await api.get(`/guilds/${guildId}/announce/webhook`);
      setWebhooks(res.data?.webhooks || {});
    } catch (err) {
      setWebhookError(err.response?.data?.error || 'Failed to save webhook.');
    } finally {
      setSavingWebhook(false);
    }
  };

  const selectedChannelName = channels.find(c => c.id === selectedChannel)?.name || 'channel';
  const hasWebhookConfigured = Boolean(webhooks[selectedChannel]);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <Skeleton height={60} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20 }}>
          <Skeleton height={400} />
          <Skeleton height={400} />
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, paddingBottom: 40 }}>
      <PageHeader
        title="Announcements & Embeds"
        description="Broadcast rich Discord embeds with customized sidebar highlight colors, mentions, and webhook support."
        icon={Megaphone}
      />

      {/* Main Grid: Left Composer, Right Live Discord Embed Preview */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 20, alignItems: 'start' }}>
        
        {/* Left: Compose Form */}
        <Card>
          <CardHeader>
            <CardTitle>Create Announcement</CardTitle>
            <CardDescription>
              Custom embed sidebar colors match your server branding.
              {hasWebhookConfigured && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginLeft: 8, color: '#34d399', fontSize: 12 }}>
                  <Webhook size={12} /> Webhook active for #{selectedChannelName}
                </span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSend} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              
              {/* Destination Channel */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>
                  Target Channel
                </label>
                <Select
                  value={selectedChannel}
                  onChange={e => setSelectedChannel(e.target.value)}
                  options={channels.map(c => ({
                    value: c.id,
                    label: `# ${c.name}${webhooks[c.id] ? ' (Webhook)' : ''}`
                  }))}
                  icon={Hash}
                />
              </div>

              {/* Title */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>
                  Title (Optional)
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="e.g. Server Maintenance Notice"
                  maxLength={256}
                  style={{
                    width: '100%',
                    padding: '9px 12px',
                    borderRadius: 8,
                    background: 'var(--bg-input, rgba(255,255,255,0.05))',
                    border: '1px solid var(--border-color, rgba(255,255,255,0.1))',
                    color: 'var(--text-main, #fff)',
                    fontSize: 14,
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                />
              </div>

              {/* Message Body */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>
                  Message Content *
                </label>
                <textarea
                  value={body}
                  onChange={e => setBody(e.target.value)}
                  placeholder="Type your announcement message here... Supports Discord Markdown (*bold*, _italic_, `code`, etc.)"
                  rows={5}
                  required
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 8,
                    background: 'var(--bg-input, rgba(255,255,255,0.05))',
                    border: '1px solid var(--border-color, rgba(255,255,255,0.1))',
                    color: 'var(--text-main, #fff)',
                    fontSize: 14,
                    lineHeight: 1.5,
                    resize: 'vertical',
                    outline: 'none',
                    boxSizing: 'border-box',
                    fontFamily: 'inherit'
                  }}
                />
              </div>

              {/* Ping / Mention */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>
                  Mention / Notification
                </label>
                <div style={{ display: 'flex', gap: 10 }}>
                  {[
                    { id: 'none', label: 'None' },
                    { id: 'here', label: '@here' },
                    { id: 'everyone', label: '@everyone' },
                  ].map(p => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setPing(p.id)}
                      style={{
                        flex: 1,
                        padding: '8px 10px',
                        borderRadius: 8,
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: 'pointer',
                        border: ping === p.id ? '1px solid #8A2BE2' : '1px solid rgba(255,255,255,0.1)',
                        background: ping === p.id ? 'rgba(138,43,226,0.18)' : 'rgba(255,255,255,0.04)',
                        color: ping === p.id ? '#c084fc' : 'var(--text-sub)',
                        transition: 'all 0.15s ease'
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Embed Sidebar Highlight Color Picker */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Palette size={14} /> Embed Sidebar Highlight Color
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        width: 18,
                        height: 18,
                        borderRadius: 4,
                        background: color,
                        border: '1px solid rgba(255,255,255,0.3)',
                        boxShadow: `0 0 8px ${color}66`,
                        display: 'inline-block'
                      }}
                    />
                    <input
                      type="text"
                      value={color}
                      onChange={e => setColor(e.target.value)}
                      placeholder="#8A2BE2"
                      maxLength={7}
                      style={{
                        width: 76,
                        padding: '3px 6px',
                        fontSize: 12,
                        borderRadius: 6,
                        border: '1px solid rgba(255,255,255,0.15)',
                        background: 'rgba(0,0,0,0.2)',
                        color: 'var(--text-main)',
                        fontFamily: 'monospace',
                        textAlign: 'center'
                      }}
                    />
                  </div>
                </div>

                {/* Color Preset Palette */}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  {COLOR_PRESETS.map(c => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setColor(c)}
                      title={c}
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: 7,
                        background: c,
                        border: color.toUpperCase() === c.toUpperCase() ? '2px solid #ffffff' : '2px solid rgba(255,255,255,0.12)',
                        cursor: 'pointer',
                        padding: 0,
                        boxShadow: color.toUpperCase() === c.toUpperCase() ? `0 0 10px ${c}aa` : 'none',
                        transform: color.toUpperCase() === c.toUpperCase() ? 'scale(1.1)' : 'scale(1)',
                        transition: 'all 0.15s ease'
                      }}
                    />
                  ))}
                  {/* Native Color Picker */}
                  <label
                    title="Choose custom color"
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 7,
                      border: '2px solid rgba(255,255,255,0.2)',
                      background: 'rgba(255,255,255,0.06)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      overflow: 'hidden',
                      position: 'relative'
                    }}
                  >
                    <Palette size={14} color="#aaa" />
                    <input
                      type="color"
                      value={color.startsWith('#') && color.length === 7 ? color : '#8A2BE2'}
                      onChange={e => setColor(e.target.value)}
                      style={{
                        position: 'absolute',
                        opacity: 0,
                        width: '100%',
                        height: '100%',
                        cursor: 'pointer'
                      }}
                    />
                  </label>
                </div>
              </div>

              {/* Status Alerts */}
              {error && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 8, background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)', color: '#f87171', fontSize: 13 }}>
                  <AlertCircle size={16} /> {error}
                </div>
              )}
              {success && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 8, background: 'rgba(52,211,153,0.12)', border: '1px solid rgba(52,211,153,0.3)', color: '#34d399', fontSize: 13 }}>
                  <CheckCircle2 size={16} /> {success}
                </div>
              )}

              {/* Submit Button */}
              <Button
                type="submit"
                variant="primary"
                disabled={sending}
                icon={Send}
                style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}
              >
                {sending ? 'Sending Announcement…' : `Send to #${selectedChannelName}`}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Right: Live Discord Embed Preview */}
        <Card>
          <CardHeader>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <CardTitle>Discord Live Preview</CardTitle>
                <CardDescription>Real-time rendering with sidebar highlight</CardDescription>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-sub)', fontFamily: 'monospace' }}>
                Sidebar: <span style={{ color, fontWeight: 700 }}>{color}</span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {/* Discord Dark Mock Container */}
            <div
              style={{
                background: '#313338',
                borderRadius: 10,
                padding: '18px 16px',
                fontFamily: '"gg sans", "Noto Sans", Helvetica, Arial, sans-serif',
                color: '#dbdee1',
                boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
                border: '1px solid rgba(255,255,255,0.06)'
              }}
            >
              {/* Message Sender Row */}
              <div style={{ display: 'flex', gap: 12 }}>
                {/* Avatar */}
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    background: hasWebhookConfigured
                      ? 'linear-gradient(135deg, #10b981, #06b6d4)'
                      : 'linear-gradient(135deg, #7c3aed, #4f46e5)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 18,
                    flexShrink: 0,
                    boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
                  }}
                >
                  {hasWebhookConfigured ? '⚡' : '🤖'}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Sender Header */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                    <span style={{ fontWeight: 600, fontSize: 15, color: '#f2f3f5' }}>
                      {hasWebhookConfigured ? 'Custom Webhook' : botName}
                    </span>
                    <span
                      style={{
                        background: '#5865F2',
                        color: '#ffffff',
                        fontSize: 9,
                        fontWeight: 700,
                        padding: '1px 4px',
                        borderRadius: 3,
                        lineHeight: '13px',
                        letterSpacing: '0.04em'
                      }}
                    >
                      {hasWebhookConfigured ? 'WEBHOOK' : 'BOT'}
                    </span>
                    <span style={{ fontSize: 11, color: '#949ba4' }}>
                      Today at {new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  {/* Optional Ping Mention */}
                  {ping !== 'none' && (
                    <div style={{ marginBottom: 6 }}>
                      <span
                        style={{
                          fontSize: 13,
                          color: '#c9cdfb',
                          background: 'rgba(88,101,242,0.18)',
                          padding: '1px 5px',
                          borderRadius: 3,
                          fontWeight: 500
                        }}
                      >
                        {ping === 'everyone' ? '@everyone' : '@here'}
                      </span>
                    </div>
                  )}

                  {/* Embed Container with Dynamic Highlight Border */}
                  <div
                    style={{
                      background: '#2b2d31',
                      borderRadius: '0 4px 4px 0',
                      borderLeft: `4px solid ${color}`,
                      padding: '12px 16px',
                      marginTop: 4,
                      boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.03)',
                      transition: 'border-color 0.2s ease'
                    }}
                  >
                    {/* Embed Title */}
                    {(title || !body) && (
                      <div
                        style={{
                          fontWeight: 700,
                          fontSize: 15,
                          color: '#f2f3f5',
                          marginBottom: body ? 8 : 0,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6
                        }}
                      >
                        📢 {title || 'Announcement Title'}
                      </div>
                    )}

                    {/* Embed Description */}
                    <div
                      style={{
                        fontSize: 13.5,
                        color: '#dbdee1',
                        lineHeight: 1.5,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word'
                      }}
                    >
                      {body || (
                        <span style={{ color: '#80848e', fontStyle: 'italic' }}>
                          Your announcement text will render here with the live sidebar highlight...
                        </span>
                      )}
                    </div>

                    {/* Embed Footer */}
                    <div
                      style={{
                        marginTop: 12,
                        paddingTop: 8,
                        borderTop: '1px solid rgba(255,255,255,0.04)',
                        fontSize: 11,
                        color: '#949ba4',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6
                      }}
                    >
                      <span
                        style={{
                          width: 14,
                          height: 14,
                          borderRadius: '50%',
                          background: color,
                          display: 'inline-block'
                        }}
                      />
                      <span>{botName} — Official Announcement</span>
                      <span>•</span>
                      <span>{new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-sub)', textAlign: 'center' }}>
              💡 Sidebar line adjusts automatically to <code style={{ color, fontWeight: 700 }}>{color}</code>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Webhook Configuration Card */}
      <Card>
        <CardHeader>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Webhook size={16} color="#10b981" />
            </div>
            <div>
              <CardTitle>Webhook Delivery (Optional)</CardTitle>
              <CardDescription>
                Bind a Discord Webhook URL to send announcements with custom bot avatars and names.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSaveWebhook} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>
                  Channel
                </label>
                <Select
                  value={webhookChannel}
                  onChange={e => setWebhookChannel(e.target.value)}
                  options={channels.map(c => ({
                    value: c.id,
                    label: `# ${c.name}${webhooks[c.id] ? ' (configured)' : ''}`
                  }))}
                  icon={Hash}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>
                  Webhook URL
                </label>
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={e => setWebhookUrl(e.target.value)}
                  placeholder={webhooks[webhookChannel] ? `Active: ${webhooks[webhookChannel]}` : 'https://discord.com/api/webhooks/...'}
                  style={{
                    width: '100%',
                    padding: '9px 12px',
                    borderRadius: 8,
                    background: 'var(--bg-input, rgba(255,255,255,0.05))',
                    border: '1px solid var(--border-color, rgba(255,255,255,0.1))',
                    color: 'var(--text-main, #fff)',
                    fontSize: 13,
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                />
              </div>
            </div>

            {webhookError && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)', color: '#f87171', fontSize: 13 }}>
                <AlertCircle size={15} /> {webhookError}
              </div>
            )}
            {webhookSuccess && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(52,211,153,0.12)', border: '1px solid rgba(52,211,153,0.3)', color: '#34d399', fontSize: 13 }}>
                <CheckCircle2 size={15} /> {webhookSuccess}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              {webhooks[webhookChannel] && (
                <Button
                  type="button"
                  variant="danger"
                  disabled={savingWebhook}
                  icon={Trash2}
                  onClick={() => {
                    setWebhookUrl('');
                    handleSaveWebhook({ preventDefault: () => {} });
                  }}
                >
                  Remove Webhook
                </Button>
              )}
              <Button
                type="submit"
                variant="secondary"
                disabled={savingWebhook}
                icon={Webhook}
              >
                {savingWebhook ? 'Saving…' : 'Save Webhook URL'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
