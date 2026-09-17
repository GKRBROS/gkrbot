import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync } from '../../sync';
import { Select } from '../../components/Select';
import { useBotName } from '../../BotContext';

const CARD_STYLES = [
  {
    id: 'legacy',
    label: 'Legacy Neon',
    emoji: '🟣',
    desc: 'Split-panel purple/cyan glow with avatar ring',
    badge: 'Classic Original',
    accent: '#8b5cf6',
  },
  {
    id: 'glass',
    label: 'Minimalist Glass',
    emoji: '⚪',
    desc: 'Centered avatar, soft halo glow & frosted glass',
    badge: 'Modern Clean',
    accent: '#6366f1',
  },
  {
    id: 'ticket',
    label: 'Ticket Pass',
    emoji: '🎫',
    desc: 'VIP boarding pass with tear-off stub & barcode',
    badge: 'Creative VIP',
    accent: '#ec4899',
  },
  {
    id: 'cinematic',
    label: 'Cinematic Poster',
    emoji: '🎬',
    desc: 'Bold moody typography & wide letterbox banner',
    badge: 'Bold Impact',
    accent: '#14b8a6',
  },
];

const PRESET_BACKGROUNDS = [
  { name: 'Cyber Neon', url: 'https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=1200&auto=format&fit=crop' },
  { name: 'Deep Space', url: 'https://images.unsplash.com/photo-1506703719100-a0f3a48c0f86?q=80&w=1200&auto=format&fit=crop' },
  { name: 'Synthwave Sunset', url: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?q=80&w=1200&auto=format&fit=crop' },
  { name: 'Abstract Gradient', url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=1200&auto=format&fit=crop' },
];

const PLACEHOLDERS = [
  { label: '{user}', desc: 'Mentions the new member (<@ID>)' },
  { label: '{username}', desc: "Member's display name" },
  { label: '{server}', desc: 'Server name' },
  { label: '{count}', desc: 'Current member count' },
];

function Welcome() {
  const { guildId } = useParams();
  const botName = useBotName();

  const [activeTab, setActiveTab] = useState('card'); // 'card' | 'message' | 'autorole' | 'leave'
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [syncOpen, setSyncOpen] = useState(false);

  // Test state
  const [testingWelcome, setTestingWelcome] = useState(false);
  const [testingLeave, setTestingLeave] = useState(false);
  const [testNotice, setTestNotice] = useState(null);

  const [config, setConfig] = useState({
    enabled: false,
    channel_id: '',
    message: 'Welcome to the server, {user}! 🎉',
    card_style: 'legacy',
    background_url: '',
    show_avatar: true,
    show_guild_icon: false,
    draw_avatar: true,
    draw_text: true,
    welcome_role_id: '',
    bot_role_id: '',
    leave_enabled: false,
    leave_channel_id: '',
    leave_message: '**{user}** left the server.',
    leave_image_url: '',
  });

  const fetchData = useCallback(async () => {
    try {
      const [welcomeRes, channelsRes, rolesRes] = await Promise.all([
        api.get(`/guilds/${guildId}/welcome`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/roles`).catch(() => ({ data: { roles: [] } })),
      ]);

      if (welcomeRes.data.config) {
        const c = welcomeRes.data.config;
        setConfig({
          enabled: c.enabled ?? false,
          channel_id: c.channel_id || '',
          message: c.message || 'Welcome to the server, {user}! 🎉',
          card_style: c.card_style || 'legacy',
          background_url: c.background_path ? '' : '', // will allow setting fresh URL
          show_avatar: c.show_avatar ?? true,
          show_guild_icon: c.show_guild_icon ?? false,
          draw_avatar: c.draw_avatar ?? true,
          draw_text: c.draw_text ?? true,
          welcome_role_id: c.welcome_role_id || '',
          bot_role_id: c.bot_role_id || '',
          leave_enabled: c.leave_enabled ?? false,
          leave_channel_id: c.leave_channel_id || '',
          leave_message: c.leave_message || '**{user}** left the server.',
          leave_image_url: c.leave_image_url || '',
        });
      }
      setChannels(channelsRes.data.channels || []);
      setRoles(rolesRes.data.roles || []);
    } catch (err) {
      console.error('Failed to fetch welcome config', err);
    }
    setLoading(false);
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await api.post(`/guilds/${guildId}/welcome`, withSync(config));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save welcome config');
    }
    setSaving(false);
  };

  const handleTest = async (type) => {
    if (type === 'welcome') setTestingWelcome(true);
    else setTestingLeave(true);
    setTestNotice(null);

    try {
      const res = await api.post(`/guilds/${guildId}/welcome/test`, { type });
      setTestNotice({ type: 'success', message: res.data?.message || `Test ${type} message sent to Discord!` });
      setTimeout(() => setTestNotice(null), 5000);
    } catch (err) {
      setTestNotice({ type: 'error', message: err.response?.data?.error || `Failed to dispatch test ${type}` });
    } finally {
      if (type === 'welcome') setTestingWelcome(false);
      else setTestingLeave(false);
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '380px' }}></div>
      </div>
    );
  }

  const activeStyleMeta = CARD_STYLES.find(s => s.id === config.card_style) || CARD_STYLES[0];

  return (
    <div className="animate-fade-in">
      {/* Top Header */}
      <div className="page-header flex justify-between items-center" style={{ flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
        <div>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span>👋</span> Welcome & Leave Studio
          </h1>
          <p className="page-subtitle">
            Create ultra-clean welcome cards, automatic member & bot roles, and departure announcements.
          </p>
        </div>
        <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => handleTest('welcome')}
            disabled={testingWelcome || !config.channel_id}
            className="btn"
            title={!config.channel_id ? 'Set a Welcome Channel first' : 'Send a simulated welcome card to Discord'}
            style={{
              background: 'rgba(99, 102, 241, 0.15)',
              border: '1px solid #6366f1',
              color: '#c7d2fe',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>{testingWelcome ? '⏳' : '🧪'}</span>
            {testingWelcome ? 'Dispatching...' : 'Test Welcome'}
          </button>
          <button
            type="button"
            onClick={() => setSyncOpen(true)}
            className="btn"
            style={{
              background: 'rgba(88, 101, 242, 0.15)',
              border: '1px solid var(--primary)',
              color: 'var(--text-main)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>🔄</span> Sync Servers
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: '16px' }}>{error}</div>}
      {testNotice && (
        <div
          className={`alert ${testNotice.type === 'success' ? 'alert-success' : 'alert-error'}`}
          style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
        >
          <span>{testNotice.message}</span>
          <button type="button" onClick={() => setTestNotice(null)} style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer' }}>✖</button>
        </div>
      )}

      {/* Global Enable Toggle Banner */}
      <div className="glass-panel" style={{ padding: '16px 20px', marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            width: '44px',
            height: '44px',
            borderRadius: '12px',
            background: config.enabled ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.12)',
            border: `1px solid ${config.enabled ? 'rgba(34, 197, 94, 0.4)' : 'rgba(239, 68, 68, 0.3)'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '22px',
          }}>
            {config.enabled ? '🟢' : '🔴'}
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '16px', color: 'var(--text-main)' }}>
              Welcome System is {config.enabled ? 'Enabled' : 'Disabled'}
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              {config.enabled
                ? 'Welcome cards and greetings will be delivered automatically whenever a member joins.'
                : 'Turn this on to begin greeting incoming members.'}
            </div>
          </div>
        </div>
        <button
          type="button"
          className={`toggle ${config.enabled ? 'active' : ''}`}
          onClick={() => setConfig(c => ({ ...c, enabled: !c.enabled }))}
          aria-label="Toggle Welcome System"
        ></button>
      </div>

      {/* Modern Navigation Tabs */}
      <div style={{
        display: 'flex',
        gap: '8px',
        borderBottom: '1px solid var(--border)',
        marginBottom: '24px',
        overflowX: 'auto',
        paddingBottom: '4px'
      }}>
        {[
          { id: 'card', label: '🎴 Card Design & Styles', desc: '4 Styles & Custom Background' },
          { id: 'message', label: '💬 Welcome Channel & Text', desc: 'Channel & Variables' },
          { id: 'autorole', label: '🤖 Auto-Roles on Join', desc: 'Human & Bot Roles' },
          { id: 'leave', label: '🚪 Leave Announcements', desc: 'Departure Alerts' },
        ].map(t => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActiveTab(t.id)}
            style={{
              background: activeTab === t.id ? 'rgba(88, 101, 242, 0.18)' : 'transparent',
              border: 'none',
              borderBottom: activeTab === t.id ? '2px solid var(--primary)' : '2px solid transparent',
              color: activeTab === t.id ? '#fff' : 'var(--text-muted)',
              fontWeight: activeTab === t.id ? '600' : '500',
              padding: '10px 16px',
              borderRadius: '8px 8px 0 0',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'all 0.2s',
              whiteSpace: 'nowrap',
            }}
          >
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {/* TAB 1: CARD DESIGN & STYLES */}
      {activeTab === 'card' && (
        <div className="grid-2 stagger" style={{ gap: '24px' }}>
          {/* Left Column: Style Picker & Options */}
          <div className="flex flex-col gap-4">
            <div className="glass-panel" style={{ padding: '24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none' }}>
                  🎨 Choose Card Style
                </h3>
                <span className="badge badge-primary">{activeStyleMeta.label} Active</span>
              </div>

              {/* 4 Card Style Tiles */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '20px' }}>
                {CARD_STYLES.map(style => {
                  const isSelected = config.card_style === style.id;
                  return (
                    <div
                      key={style.id}
                      onClick={() => setConfig({ ...config, card_style: style.id })}
                      style={{
                        background: isSelected ? 'rgba(88, 101, 242, 0.15)' : 'var(--bg-surface)',
                        border: isSelected ? `2px solid ${style.accent}` : '1px solid var(--border)',
                        borderRadius: '10px',
                        padding: '14px',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        boxShadow: isSelected ? `0 0 16px ${style.accent}33` : 'none',
                        position: 'relative',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <span style={{ fontSize: '24px' }}>{style.emoji}</span>
                        {isSelected && (
                          <span style={{
                            fontSize: '10px',
                            background: style.accent,
                            color: '#fff',
                            fontWeight: 'bold',
                            padding: '2px 6px',
                            borderRadius: '4px'
                          }}>SELECTED</span>
                        )}
                      </div>
                      <div style={{ fontWeight: '600', fontSize: '14px', color: '#fff', marginBottom: '4px' }}>
                        {style.label}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: '1.3' }}>
                        {style.desc}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Card Element Toggles */}
              <h4 style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                Card Overlays & Elements
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '10px 14px', borderRadius: '8px' }}>
                  <div>
                    <div style={{ fontWeight: '500', fontSize: '14px' }}>👤 Draw Avatar Circle</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Renders the user profile photo on the generated image</div>
                  </div>
                  <button
                    type="button"
                    className={`toggle ${config.draw_avatar ? 'active' : ''}`}
                    onClick={() => setConfig(c => ({ ...c, draw_avatar: !c.draw_avatar }))}
                  ></button>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '10px 14px', borderRadius: '8px' }}>
                  <div>
                    <div style={{ fontWeight: '500', fontSize: '14px' }}>🔠 Draw Text Overlays</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Renders username, welcome greeting & member count on card</div>
                  </div>
                  <button
                    type="button"
                    className={`toggle ${config.draw_text ? 'active' : ''}`}
                    onClick={() => setConfig(c => ({ ...c, draw_text: !c.draw_text }))}
                  ></button>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '10px 14px', borderRadius: '8px' }}>
                  <div>
                    <div style={{ fontWeight: '500', fontSize: '14px' }}>🛡️ Show Server Icon</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Displays the server icon badge on supported card layouts</div>
                  </div>
                  <button
                    type="button"
                    className={`toggle ${config.show_guild_icon ? 'active' : ''}`}
                    onClick={() => setConfig(c => ({ ...c, show_guild_icon: !c.show_guild_icon }))}
                  ></button>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '10px 14px', borderRadius: '8px' }}>
                  <div>
                    <div style={{ fontWeight: '500', fontSize: '14px' }}>🖼️ Show Embed Thumbnail</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Attach user avatar as the Discord message embed thumbnail</div>
                  </div>
                  <button
                    type="button"
                    className={`toggle ${config.show_avatar ? 'active' : ''}`}
                    onClick={() => setConfig(c => ({ ...c, show_avatar: !c.show_avatar }))}
                  ></button>
                </div>
              </div>
            </div>

            {/* Custom Background URL */}
            <div className="glass-panel" style={{ padding: '24px' }}>
              <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '12px' }}>
                🖼️ Custom Background
              </h3>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '14px' }}>
                Provide a direct image or GIF URL (recommended size: <strong>1024x500</strong>) to replace the default dark canvas.
              </p>
              <div className="form-group" style={{ marginBottom: '12px' }}>
                <input
                  type="text"
                  className="input-field"
                  placeholder="https://example.com/custom-background.png or .gif"
                  value={config.background_url}
                  onChange={e => setConfig({ ...config, background_url: e.target.value })}
                />
              </div>

              {/* Presets */}
              <div style={{ marginBottom: '10px' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>Or pick a curated wallpaper:</div>
                <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
                  {PRESET_BACKGROUNDS.map(p => (
                    <button
                      key={p.name}
                      type="button"
                      className="btn"
                      style={{ fontSize: '12px', padding: '5px 10px', background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
                      onClick={() => setConfig({ ...config, background_url: p.url })}
                    >
                      ✨ {p.name}
                    </button>
                  ))}
                  {config.background_url && (
                    <button
                      type="button"
                      className="btn btn-danger"
                      style={{ fontSize: '12px', padding: '5px 10px' }}
                      onClick={() => setConfig({ ...config, background_url: 'none' })}
                    >
                      ❌ Reset to Default
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Live Interactive Card Canvas Mockup */}
          <div className="flex flex-col gap-4">
            <div className="glass-panel flex flex-col" style={{ padding: '24px', background: 'var(--bg-surface)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none' }}>
                  👁️ Real-Time Card Canvas
                </h3>
                <span className="badge" style={{ background: 'rgba(255,255,255,0.06)', color: '#fff' }}>
                  1024 × 500 Aspect Ratio
                </span>
              </div>

              {/* CARD MOCKUP VIEWPORT */}
              <div style={{
                position: 'relative',
                width: '100%',
                aspectRatio: '1024 / 500',
                borderRadius: '14px',
                overflow: 'hidden',
                background: '#12131a',
                border: '1px solid rgba(255,255,255,0.1)',
                boxShadow: '0 12px 32px rgba(0,0,0,0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                {/* Optional Background Image */}
                {config.background_url && config.background_url !== 'none' && (
                  <div style={{
                    position: 'absolute',
                    inset: 0,
                    backgroundImage: `url(${config.background_url})`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                    opacity: 0.85,
                    filter: config.card_style === 'glass' ? 'blur(3px)' : 'none',
                  }} />
                )}

                {/* 1. LEGACY NEON MOCKUP */}
                {config.card_style === 'legacy' && (
                  <div style={{
                    position: 'relative',
                    width: '100%',
                    height: '100%',
                    background: config.background_url && config.background_url !== 'none'
                      ? 'rgba(12, 13, 20, 0.75)'
                      : 'linear-gradient(135deg, #0d0f1a 0%, #15102a 60%, #0a1128 100%)',
                    display: 'flex',
                    alignItems: 'center',
                    padding: '0 40px',
                    gap: '36px',
                  }}>
                    {/* Glowing orbs */}
                    <div style={{ position: 'absolute', top: '-10%', left: '15%', width: '220px', height: '220px', background: '#8b5cf6', filter: 'blur(80px)', opacity: 0.35, borderRadius: '50%' }}></div>
                    <div style={{ position: 'absolute', bottom: '-10%', right: '10%', width: '240px', height: '240px', background: '#06b6d4', filter: 'blur(90px)', opacity: 0.35, borderRadius: '50%' }}></div>

                    {/* Avatar Circle */}
                    {config.draw_avatar && (
                      <div style={{
                        position: 'relative',
                        width: '120px',
                        height: '120px',
                        borderRadius: '50%',
                        background: 'linear-gradient(135deg, #a855f7, #3b82f6)',
                        padding: '4px',
                        boxShadow: '0 0 25px rgba(168, 85, 247, 0.6)',
                        flexShrink: 0,
                      }}>
                        <div style={{
                          width: '100%',
                          height: '100%',
                          borderRadius: '50%',
                          background: '#1f2937',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '44px',
                          color: '#fff',
                        }}>
                          👤
                        </div>
                      </div>
                    )}

                    {/* Text block */}
                    {config.draw_text && (
                      <div style={{ position: 'relative', zIndex: 2 }}>
                        <div style={{ fontSize: '13px', fontWeight: 'bold', letterSpacing: '2px', color: '#38bdf8', textTransform: 'uppercase', marginBottom: '4px' }}>
                          WELCOME TO THE SERVER
                        </div>
                        <div style={{ fontSize: '28px', fontWeight: '900', color: '#fff', textShadow: '0 2px 10px rgba(0,0,0,0.5)', lineHeight: 1.1, marginBottom: '8px' }}>
                          NewUser#0001
                        </div>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(8px)', padding: '4px 12px', borderRadius: '20px', fontSize: '12px', color: '#e2e8f0' }}>
                          <span>🎉 Member #1,234</span>
                          {config.show_guild_icon && <span>• 🛡️ Server</span>}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 2. MINIMALIST GLASS MOCKUP */}
                {config.card_style === 'glass' && (
                  <div style={{
                    position: 'relative',
                    width: '100%',
                    height: '100%',
                    background: config.background_url && config.background_url !== 'none'
                      ? 'rgba(10, 10, 14, 0.72)'
                      : 'linear-gradient(180deg, #16171c 0%, #1a1b24 100%)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    {/* Soft Center Halo */}
                    <div style={{ position: 'absolute', top: '15%', width: '260px', height: '140px', background: '#826eff', filter: 'blur(50px)', opacity: 0.45, borderRadius: '50%' }}></div>

                    {config.draw_avatar && (
                      <div style={{
                        position: 'relative',
                        width: '100px',
                        height: '100px',
                        borderRadius: '50%',
                        border: '2px solid rgba(255, 255, 255, 0.4)',
                        boxShadow: '0 12px 24px rgba(0,0,0,0.6)',
                        background: '#1f2430',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '40px',
                        marginBottom: '14px',
                        zIndex: 2,
                      }}>
                        👤
                      </div>
                    )}

                    {config.draw_text && (
                      <div style={{ textAlign: 'center', zIndex: 2 }}>
                        <div style={{ fontSize: '24px', fontWeight: '800', color: '#ffffff', letterSpacing: '0.5px', marginBottom: '4px' }}>
                          NewUser
                        </div>
                        <div style={{ fontSize: '13px', color: 'rgba(255,255,255,0.7)', fontWeight: '500' }}>
                          Welcome to the server • Member #1,234
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 3. TICKET PASS MOCKUP */}
                {config.card_style === 'ticket' && (
                  <div style={{
                    position: 'relative',
                    width: '90%',
                    height: '80%',
                    background: '#181a20',
                    borderRadius: '12px',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    display: 'flex',
                    boxShadow: '0 10px 30px rgba(0,0,0,0.6)',
                    overflow: 'hidden',
                  }}>
                    {/* Main Ticket Section */}
                    <div style={{ flex: 3, padding: '20px 24px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: '10px', letterSpacing: '2px', fontWeight: 'bold', color: '#ec4899', textTransform: 'uppercase' }}>
                          VIP SERVER PASS • OFFICIAL ENTRY
                        </div>
                        <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>
                          #001234
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', margin: '8px 0' }}>
                        {config.draw_avatar && (
                          <div style={{ width: '64px', height: '64px', borderRadius: '10px', background: '#262934', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '28px', border: '1px solid #ec4899' }}>
                            👤
                          </div>
                        )}
                        {config.draw_text && (
                          <div>
                            <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#fff' }}>NewUser</div>
                            <div style={{ fontSize: '12px', color: '#9ca3af' }}>Granted Member Access</div>
                          </div>
                        )}
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '8px', fontSize: '11px', color: '#6b7280' }}>
                        <span>GATE: 01</span>
                        <span>SERVER: FAMILY</span>
                        <span>DATE: TODAY</span>
                      </div>
                    </div>

                    {/* Perforated Divider */}
                    <div style={{
                      width: '0px',
                      borderLeft: '2px dashed rgba(255,255,255,0.2)',
                      position: 'relative',
                    }}>
                      <div style={{ position: 'absolute', top: '-10px', left: '-10px', width: '20px', height: '20px', background: '#12131a', borderRadius: '50%' }}></div>
                      <div style={{ position: 'absolute', bottom: '-10px', left: '-10px', width: '20px', height: '20px', background: '#12131a', borderRadius: '50%' }}></div>
                    </div>

                    {/* Tear-Off Stub */}
                    <div style={{ flex: 1, background: 'rgba(236, 72, 153, 0.08)', padding: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ fontSize: '10px', fontWeight: 'bold', color: '#ec4899', textAlign: 'center' }}>ADMIT ONE</div>
                      <div style={{
                        display: 'flex',
                        gap: '2px',
                        height: '32px',
                        alignItems: 'center',
                      }}>
                        {[6, 3, 8, 4, 12, 2, 7, 5, 10, 4, 8, 3, 9, 2].map((w, idx) => (
                          <div key={idx} style={{ width: `${w > 6 ? 3 : 2}px`, height: '100%', background: 'rgba(255,255,255,0.5)' }}></div>
                        ))}
                      </div>
                      <div style={{ fontSize: '9px', color: '#6b7280', fontFamily: 'monospace' }}>PASS VALID</div>
                    </div>
                  </div>
                )}

                {/* 4. CINEMATIC POSTER MOCKUP */}
                {config.card_style === 'cinematic' && (
                  <div style={{
                    position: 'relative',
                    width: '100%',
                    height: '100%',
                    background: config.background_url && config.background_url !== 'none'
                      ? 'none'
                      : 'linear-gradient(135deg, #090d16 0%, #030712 100%)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    padding: '24px 32px',
                  }}>
                    {/* Big blurred avatar in background top right */}
                    <div style={{
                      position: 'absolute',
                      right: '-30px',
                      top: '-30px',
                      width: '240px',
                      height: '240px',
                      borderRadius: '50%',
                      background: 'linear-gradient(135deg, #14b8a6, #06b6d4)',
                      opacity: 0.25,
                      filter: 'blur(30px)',
                    }}></div>

                    {/* Top line */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 2 }}>
                      <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#2dd4bf', letterSpacing: '2px', borderBottom: '2px solid #2dd4bf', paddingBottom: '2px' }}>
                        MEMBER No. 1,234
                      </div>
                      <div style={{ fontSize: '12px', fontWeight: 'bold', color: 'rgba(255,255,255,0.6)', letterSpacing: '1px' }}>
                        SERVER RECEPTION
                      </div>
                    </div>

                    {/* Big title */}
                    <div style={{ zIndex: 2, marginBottom: '6px' }}>
                      <div style={{ fontSize: '38px', fontWeight: '900', color: '#fff', letterSpacing: '-0.5px', textTransform: 'uppercase', lineHeight: 1 }}>
                        NEWUSER
                      </div>
                      <div style={{ fontSize: '13px', color: '#99f6e4', marginTop: '4px', fontWeight: '500' }}>
                        has entered the server
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Save changes footer */}
              <div className="flex justify-end mt-4 pt-4" style={{ borderTop: '1px solid var(--border)', gap: '10px' }}>
                <button
                  type="button"
                  onClick={handleSave}
                  className={`btn ${saved ? 'btn-success' : 'btn-primary'}`}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : saved ? '✅ Saved!' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: WELCOME MESSAGE & CHANNEL */}
      {activeTab === 'message' && (
        <div className="grid-2 stagger" style={{ gap: '24px' }}>
          {/* Form Settings */}
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '16px' }}>
              💬 Delivery Channel & Text
            </h3>

            <div className="form-group">
              <label className="form-label">Welcome Channel</label>
              <Select
                value={config.channel_id}
                onChange={v => setConfig({ ...config, channel_id: v })}
                options={channels.map(ch => ({ value: ch.id, label: '# ' + ch.name }))}
                placeholder="Select a welcome channel..."
                searchable
              />
              <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
                The channel where greetings and welcome cards will be sent.
              </span>
            </div>

            <div className="form-group">
              <label className="form-label">Custom Message Content</label>
              <textarea
                className="input-field"
                rows={5}
                value={config.message}
                onChange={e => setConfig({ ...config, message: e.target.value })}
                placeholder="Welcome to {server}, {user}! 🎉"
                style={{ fontFamily: 'monospace' }}
              />
            </div>

            <div>
              <label className="form-label">Dynamic Variables</label>
              <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
                {PLACEHOLDERS.map(p => (
                  <button
                    key={p.label}
                    type="button"
                    className="badge badge-primary"
                    title={p.desc}
                    style={{ cursor: 'pointer', border: 'none' }}
                    onClick={() => setConfig(c => ({ ...c, message: c.message + ' ' + p.label }))}
                  >
                    + {p.label}
                  </button>
                ))}
              </div>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px', display: 'block' }}>
                Click any tag above to insert it at the end of your message.
              </span>
            </div>

            <div className="flex justify-end mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
              <button
                type="button"
                onClick={handleSave}
                className={`btn ${saved ? 'btn-success' : 'btn-primary'}`}
                disabled={saving}
              >
                {saving ? 'Saving...' : saved ? '✅ Saved!' : 'Save Changes'}
              </button>
            </div>
          </div>

          {/* Discord Message Preview */}
          <div className="glass-panel flex flex-col" style={{ padding: '24px', background: 'var(--bg-surface)' }}>
            <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '16px' }}>
              👁️ Discord Message Mockup
            </h3>

            <div style={{
              background: '#313338',
              borderRadius: '8px',
              padding: '16px',
              display: 'flex',
              gap: '14px',
              border: '1px solid rgba(255,255,255,0.05)',
            }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                background: 'linear-gradient(135deg, var(--primary), var(--accent))',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                fontWeight: 'bold',
              }}>
                🤖
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '4px' }}>
                  <span style={{ fontWeight: '600', color: 'white', fontSize: '15px' }}>{botName} Bot</span>
                  <span style={{ fontSize: '10px', background: '#5865F2', padding: '1px 5px', borderRadius: '3px', textTransform: 'uppercase', color: '#fff', fontWeight: 'bold' }}>APP</span>
                  <span style={{ fontSize: '12px', color: '#949ba4' }}>Today at 12:00 PM</span>
                </div>

                <div style={{ color: '#dbdee1', fontSize: '14px', lineHeight: '1.5', whiteSpace: 'pre-wrap', marginBottom: '12px' }}>
                  {config.message
                    .replace(/{user}/g, '@NewMember')
                    .replace(/{username}/g, 'NewMember')
                    .replace(/{server}/g, 'Family Server')
                    .replace(/{count}/g, '1,234') || 'Start typing a message to preview...'}
                </div>

                {/* Simulated Welcome Card Attachment */}
                <div style={{
                  maxWidth: '380px',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: '#1e1f22',
                  padding: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                }}>
                  <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: '#5865F2', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '20px' }}>
                    {activeStyleMeta.emoji}
                  </div>
                  <div>
                    <div style={{ fontWeight: 'bold', color: '#fff', fontSize: '13px' }}>
                      welcome_{config.card_style}.png
                    </div>
                    <div style={{ fontSize: '11px', color: '#949ba4' }}>
                      {activeStyleMeta.label} Card Attached
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex justify-end mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
              <button
                type="button"
                onClick={() => handleTest('welcome')}
                disabled={testingWelcome || !config.channel_id}
                className="btn btn-secondary"
              >
                {testingWelcome ? 'Dispatching...' : '🧪 Send Test to Channel'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: AUTO-ROLES ON JOIN */}
      {activeTab === 'autorole' && (
        <div className="glass-panel stagger" style={{ padding: '24px', maxWidth: '800px' }}>
          <div style={{ marginBottom: '20px' }}>
            <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '6px' }}>
              🤖 Automatic Role Assignment
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', margin: 0 }}>
              Roles specified here will be granted automatically to newly joining members without needing manual staff intervention.
            </p>
          </div>

          <div className="grid-2" style={{ gap: '20px', marginBottom: '24px' }}>
            {/* Member Auto-Role */}
            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '10px', padding: '18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                <span style={{ fontSize: '24px' }}>👤</span>
                <div>
                  <div style={{ fontWeight: '600', color: '#fff', fontSize: '15px' }}>Member Auto-Role</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Assigned to human members upon join</div>
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '8px' }}>
                <Select
                  value={config.welcome_role_id}
                  onChange={v => setConfig({ ...config, welcome_role_id: v })}
                  options={[
                    { value: '', label: 'None (Disabled)' },
                    ...roles.map(r => ({ value: r.id, label: r.name })),
                  ]}
                  placeholder="Select a role..."
                  searchable
                />
              </div>

              {config.welcome_role_id && (
                <button
                  type="button"
                  onClick={() => setConfig({ ...config, welcome_role_id: '' })}
                  style={{ background: 'transparent', border: 'none', color: 'var(--danger)', fontSize: '12px', cursor: 'pointer', padding: 0 }}
                >
                  Clear Member Role
                </button>
              )}
            </div>

            {/* Bot Auto-Role */}
            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '10px', padding: '18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                <span style={{ fontSize: '24px' }}>🤖</span>
                <div>
                  <div style={{ fontWeight: '600', color: '#fff', fontSize: '15px' }}>Bot Auto-Role</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Assigned specifically to added bots</div>
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '8px' }}>
                <Select
                  value={config.bot_role_id}
                  onChange={v => setConfig({ ...config, bot_role_id: v })}
                  options={[
                    { value: '', label: 'None (Disabled)' },
                    ...roles.map(r => ({ value: r.id, label: r.name })),
                  ]}
                  placeholder="Select a bot role..."
                  searchable
                />
              </div>

              {config.bot_role_id && (
                <button
                  type="button"
                  onClick={() => setConfig({ ...config, bot_role_id: '' })}
                  style={{ background: 'transparent', border: 'none', color: 'var(--danger)', fontSize: '12px', cursor: 'pointer', padding: 0 }}
                >
                  Clear Bot Role
                </button>
              )}
            </div>
          </div>

          <div className="flex justify-end" style={{ borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
            <button
              type="button"
              onClick={handleSave}
              className={`btn ${saved ? 'btn-success' : 'btn-primary'}`}
              disabled={saving}
            >
              {saving ? 'Saving...' : saved ? '✅ Saved!' : 'Save Auto-Roles'}
            </button>
          </div>
        </div>
      )}

      {/* TAB 4: LEAVE ANNOUNCEMENTS */}
      {activeTab === 'leave' && (
        <div className="stagger">
          <div className="toggle-wrapper" style={{ marginBottom: '24px' }}>
            <div>
              <div style={{ fontWeight: '600', marginBottom: '4px', fontSize: '15px' }}>Enable Leave Messages</div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Send an announcement when a member departs from the server.</div>
            </div>
            <button
              type="button"
              className={`toggle ${config.leave_enabled ? 'active' : ''}`}
              onClick={() => setConfig(c => ({ ...c, leave_enabled: !c.leave_enabled }))}
              aria-label="Toggle Leave Messages"
            ></button>
          </div>

          <div className="grid-2" style={{ gap: '24px' }}>
            {/* Leave Editor Panel */}
            <div className="glass-panel" style={{ padding: '24px', opacity: config.leave_enabled ? 1 : 0.5, pointerEvents: config.leave_enabled ? 'auto' : 'none', transition: 'all 0.3s' }}>
              <div className="form-group">
                <label className="form-label">Leave Channel</label>
                <Select
                  value={config.leave_channel_id}
                  onChange={v => setConfig({ ...config, leave_channel_id: v })}
                  options={[{ value: '', label: 'None (Disabled)' }, ...channels.map(ch => ({ value: ch.id, label: '# ' + ch.name }))]}
                  placeholder="Select a channel..."
                  searchable
                />
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
                <label className="form-label">Custom Image or GIF URL (Optional)</label>
                <input
                  type="text"
                  className="input-field"
                  value={config.leave_image_url}
                  onChange={e => setConfig({ ...config, leave_image_url: e.target.value })}
                  placeholder="https://example.com/farewell.gif"
                />
              </div>

              <div className="flex justify-end mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
                <button
                  type="button"
                  onClick={handleSave}
                  className={`btn ${saved ? 'btn-success' : 'btn-primary'}`}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : saved ? '✅ Saved!' : 'Save Leave Settings'}
                </button>
              </div>
            </div>

            {/* Leave Preview Panel */}
            <div className="glass-panel flex flex-col" style={{ padding: '24px', background: 'var(--bg-surface)' }}>
              <h3 className="section-title" style={{ margin: 0, padding: 0, border: 'none', marginBottom: '16px' }}>
                👁️ Leave Message Preview
              </h3>

              <div style={{
                background: '#313338',
                borderRadius: '8px',
                padding: '16px',
                display: 'flex',
                gap: '14px',
              }}>
                <div style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #ef4444, #f97316)',
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                }}>
                  👋
                </div>
                <div style={{ width: '100%' }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px' }}>
                    <span style={{ fontWeight: '600', color: 'white', fontSize: '15px' }}>{botName} Bot</span>
                    <span style={{ fontSize: '10px', background: '#5865F2', padding: '1px 5px', borderRadius: '3px', textTransform: 'uppercase', color: '#fff' }}>APP</span>
                  </div>

                  <div style={{ background: '#2b2d31', borderRadius: '6px', borderLeft: '4px solid #ef4444', padding: '12px' }}>
                    <div style={{ fontWeight: 'bold', color: '#f87171', marginBottom: '6px', fontSize: '13px' }}>
                      MEMBER DEPARTURE
                    </div>
                    <div style={{ color: '#dbdee1', fontSize: '14px', lineHeight: '1.4', whiteSpace: 'pre-wrap' }}>
                      {config.leave_message
                        .replace(/{user}/g, 'LeavingUser')
                        .replace(/{username}/g, 'LeavingUser')
                        .replace(/{server}/g, 'Family Server')
                        .replace(/{count}/g, '1,233') || 'Start typing to preview...'}
                    </div>
                    {config.leave_image_url && (
                      <div style={{ marginTop: '12px' }}>
                        <img
                          src={config.leave_image_url}
                          alt="Leave visual"
                          style={{ maxWidth: '100%', maxHeight: '180px', borderRadius: '4px' }}
                          onError={e => (e.target.style.display = 'none')}
                        />
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex justify-end mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
                <button
                  type="button"
                  onClick={() => handleTest('leave')}
                  disabled={testingLeave || !config.leave_channel_id}
                  className="btn btn-secondary"
                >
                  {testingLeave ? 'Dispatching...' : '🧪 Send Test Leave'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Multi-Server Sync Modal */}
      <SyncModal
        isOpen={syncOpen}
        onClose={() => setSyncOpen(false)}
        currentGuildId={guildId}
        moduleName="welcome"
        moduleLabel="Welcome & Leave Studio"
      />
    </div>
  );
}

export default Welcome;
