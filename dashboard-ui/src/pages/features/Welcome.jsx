import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import SyncModal from './SyncModal';
import { withSync } from '../../sync';
import { Select } from '../../components/Select';
import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import { Toggle } from '../../components/Toggle';
import { PageHeader } from '../../components/PageHeader';
import { useBotName } from '../../BotContext';
import {
  UserPlus,
  Palette,
  MessageSquare,
  Shield,
  LogOut,
  Send,
  RotateCcw,
  Check,
  Save,
  Image as ImageIcon,
  Sliders,
  Sparkles,
  Bot,
  User,
  AlertCircle,
  HelpCircle,
  Ticket,
  Film,
  Layers,
  Flame,
  CheckCircle2,
  RefreshCw,
  QrCode,
  Globe
} from 'lucide-react';

const CARD_STYLES = [
  {
    id: 'legacy',
    label: 'Legacy Neon',
    badge: 'Cyber Glow',
    desc: 'Dual-tone vibrant glow with avatar ring and cyber accents.',
    accent: '#8b5cf6',
    icon: Flame,
  },
  {
    id: 'glass',
    label: 'Minimalist Glass',
    badge: 'Frosted Modern',
    desc: 'Translucent frosted glass card with atmospheric twilight blur.',
    accent: '#6366f1',
    icon: Layers,
  },
  {
    id: 'ticket',
    label: 'Ticket Pass',
    badge: 'VIP Boarding',
    desc: 'Event boarding pass featuring barcode stub and perforation line.',
    accent: '#ec4899',
    icon: Ticket,
  },
  {
    id: 'cinematic',
    label: 'Cinematic Poster',
    badge: 'Wide Letterbox',
    desc: 'Dramatic wide letterbox format with bold editorial typography.',
    accent: '#14b8a6',
    icon: Film,
  },
];

const PRESET_BACKGROUNDS = [
  { name: 'Cyber Neon', url: 'https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=1200&auto=format&fit=crop' },
  { name: 'Deep Space', url: 'https://images.unsplash.com/photo-1506703719100-a0f3a48c0f86?q=80&w=1200&auto=format&fit=crop' },
  { name: 'Synthwave Sunset', url: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?q=80&w=1200&auto=format&fit=crop' },
  { name: 'Abstract Gradient', url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=1200&auto=format&fit=crop' },
];

const PLACEHOLDERS = [
  { label: '{user}', desc: 'Mentions member (<@ID>)' },
  { label: '{username}', desc: "Member's display name" },
  { label: '{server}', desc: 'Server name' },
  { label: '{count}', desc: 'Total member count' },
];

export function Welcome() {
  const { guildId } = useParams();
  const botName = useBotName();

  const [activeTab, setActiveTab] = useState('card');
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [channelsError, setChannelsError] = useState('');
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
    card_only: false,
    background_url: '',
    has_background: false,
    clear_background: false,
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

  const [savedConfig, setSavedConfig] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    setChannelsError('');

    // Each request is independent so one failure never blanks the others.
    const [welcomeRes, channelsRes, rolesRes] = await Promise.allSettled([
      api.get(`/guilds/${guildId}/welcome`),
      api.get(`/guilds/${guildId}/channels`),
      api.get(`/guilds/${guildId}/roles`),
    ]);

    if (welcomeRes.status === 'fulfilled') {
      const c = welcomeRes.value.data?.config;
      if (c) {
        const normalized = {
          enabled: c.enabled ?? false,
          channel_id: c.channel_id || '',
          message: c.message || 'Welcome to the server, {user}! 🎉',
          card_style: c.card_style || 'legacy',
          card_only: c.card_only ?? false,
          background_url: '',
          has_background: c.has_background ?? Boolean(c.background_path),
          clear_background: false,
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
        };
        setConfig(normalized);
        setSavedConfig(normalized);
      }
    } else {
      console.error('Failed to load welcome configuration', welcomeRes.reason);
      setError(
        welcomeRes.reason?.response?.data?.error ||
        welcomeRes.reason?.message ||
        'Failed to load configuration. Please try again.'
      );
    }

    if (channelsRes.status === 'fulfilled') {
      const d = channelsRes.value.data;
      const list = Array.isArray(d) ? d : (d?.channels || []);
      setChannels(list);
      if (!list.length) {
        setChannelsError('Bot sees no channels in this server. Check the bot is in the server and has View Channels permission.');
      }
    } else {
      console.error('Failed to load channels', channelsRes.reason);
      setChannels([]);
      setChannelsError(
        channelsRes.reason?.response?.data?.error ||
        channelsRes.reason?.message ||
        'Failed to load channels.'
      );
    }

    if (rolesRes.status === 'fulfilled') {
      const d = rolesRes.value.data;
      setRoles(Array.isArray(d) ? d : (d?.roles || []));
    } else {
      setRoles([]);
    }

    setLoading(false);
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Check if form has unsaved modifications
  const isDirty = useMemo(() => {
    if (!savedConfig) return false;
    return (
      config.enabled !== savedConfig.enabled ||
      config.channel_id !== savedConfig.channel_id ||
      config.message !== savedConfig.message ||
      config.card_style !== savedConfig.card_style ||
      config.card_only !== savedConfig.card_only ||
      config.background_url !== '' ||
      config.show_avatar !== savedConfig.show_avatar ||
      config.show_guild_icon !== savedConfig.show_guild_icon ||
      config.draw_avatar !== savedConfig.draw_avatar ||
      config.draw_text !== savedConfig.draw_text ||
      config.welcome_role_id !== savedConfig.welcome_role_id ||
      config.bot_role_id !== savedConfig.bot_role_id ||
      config.leave_enabled !== savedConfig.leave_enabled ||
      config.leave_channel_id !== savedConfig.leave_channel_id ||
      config.leave_message !== savedConfig.leave_message ||
      config.leave_image_url !== savedConfig.leave_image_url
    );
  }, [config, savedConfig]);

  const handleSave = async () => {
    try {
      setSaving(true);
      setError('');

      const payload = {
        enabled: config.enabled,
        channel_id: config.channel_id,
        message: config.message,
        card_style: config.card_style,
        card_only: config.card_only,
        show_avatar: config.show_avatar,
        show_guild_icon: config.show_guild_icon,
        draw_avatar: config.draw_avatar,
        draw_text: config.draw_text,
        welcome_role_id: config.welcome_role_id,
        bot_role_id: config.bot_role_id,
        leave_enabled: config.leave_enabled,
        leave_channel_id: config.leave_channel_id,
        leave_message: config.leave_message,
        leave_image_url: config.leave_image_url,
      };

      if (config.background_url) {
        payload.background_url = config.background_url;
      }
      if (config.clear_background) {
        payload.clear_background = true;
      }

      await withSync(guildId, 'welcome', payload, () =>
        api.post(`/guilds/${guildId}/welcome`, payload)
      );

      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      await fetchData();
    } catch (err) {
      console.error('Failed to save welcome configuration', err);
      setError(err.response?.data?.error || 'Failed to save configuration.');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (savedConfig) {
      setConfig({ ...savedConfig });
      setError('');
    }
  };

  const handleTestWelcome = async () => {
    try {
      setTestingWelcome(true);
      setTestNotice(null);
      const res = await api.post(`/guilds/${guildId}/welcome/test`);
      setTestNotice({ type: 'success', message: res.data?.message || 'Welcome card test dispatched to channel!' });
    } catch (err) {
      setTestNotice({
        type: 'error',
        message: err.response?.data?.error || 'Failed to dispatch test welcome message.'
      });
    } finally {
      setTestingWelcome(false);
    }
  };

  // Accept numeric (0 text, 5 announcement) and string types; keep channels with no type.
  const isTextChannel = c => {
    const t = c.type;
    if (t === undefined || t === null) return true;
    if (typeof t === 'number' || /^\d+$/.test(String(t))) return [0, 5].includes(Number(t));
    return /text|news|announ/i.test(String(t));
  };
  const textChannels = channels.filter(isTextChannel);
  const channelOptions = [
    { value: '', label: 'Select a channel...' },
    ...textChannels.map(c => ({ value: c.id, label: `#${c.name}` }))
  ];

  const roleOptions = [
    { value: '', label: 'No role assigned' },
    ...roles.map(r => ({ value: r.id, label: `@${r.name}` }))
  ];

  const activeStyleMeta = CARD_STYLES.find(s => s.id === config.card_style) || CARD_STYLES[0];

  return (
    <div className="flex flex-col gap-6 animate-fade-in pb-28! sm:pb-32!">
      {/* Top Page Header */}
      <PageHeader
        title="Welcome & Leave Studio"
        description="Craft automated greeting banners, entrance messages, role onboarding, and departure alerts."
        icon={UserPlus}
        badge={config.enabled ? 'Active System' : 'Disabled'}
        badgeVariant={config.enabled ? 'success' : 'neutral'}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={Send}
              loading={testingWelcome}
              onClick={handleTestWelcome}
              title="Dispatches a live simulation to the configured welcome channel"
            >
              Test Welcome
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={RotateCcw}
              onClick={() => setSyncOpen(true)}
              title="Copy settings to other servers"
            >
              Sync Servers
            </Button>
          </div>
        }
      />

      {/* Inline Notifications */}
      {testNotice && (
        <div className={`p-4! rounded-xl flex items-center justify-between gap-3 text-sm border ${testNotice.type === 'success'
            ? 'bg-success/10 border-success/30 text-success'
            : 'bg-danger/10 border-danger/30 text-danger'
          }`}>
          <div className="flex items-center gap-2">
            {testNotice.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            <span>{testNotice.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setTestNotice(null)}
            className="text-xs opacity-70 hover:opacity-100 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <div className="p-4! rounded-xl bg-danger/10 border border-danger/30 text-danger flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
          <button type="button" onClick={() => setError('')} className="text-xs opacity-70 hover:opacity-100 underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Main Feature Toggle Banner */}
      <div className={`p-4! sm:p-5! rounded-2xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${config.enabled
          ? 'bg-primary/10 border-primary/30 shadow-sm'
          : 'bg-surface border-border'
        }`}>
        <div className="flex items-center gap-3.5">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${config.enabled ? 'bg-primary text-white shadow-md' : 'bg-card text-muted border border-border'
            }`}>
            <UserPlus size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-main">Welcome Automation System</h3>
              <Badge variant={config.enabled ? 'success' : 'neutral'} size="sm">
                {config.enabled ? 'Enabled' : 'Paused'}
              </Badge>
            </div>
            <p className="text-xs sm:text-sm text-muted mt-0.5!">
              Automatically render banner graphics and deliver greetings when new members join.
            </p>
          </div>
        </div>

        <Toggle
          checked={config.enabled}
          onChange={v => setConfig(c => ({ ...c, enabled: v }))}
          ariaLabel="Toggle Welcome Automation"
        />
      </div>

      {/* Navigation Tabs Bar */}
      <div className="flex items-center gap-1 border-b border-border pb-1! overflow-x-auto no-scrollbar">
        <button
          type="button"
          onClick={() => setActiveTab('card')}
          className={`flex items-center gap-2 px-4! py-2.5! rounded-lg text-sm font-medium transition-all shrink-0 ${activeTab === 'card'
              ? 'bg-primary text-white shadow-sm'
              : 'text-muted hover:text-main hover:bg-surface'
            }`}
        >
          <Palette size={16} />
          <span>Card Design & Layout</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('message')}
          className={`flex items-center gap-2 px-4! py-2.5! rounded-lg text-sm font-medium transition-all shrink-0 ${activeTab === 'message'
              ? 'bg-primary text-white shadow-sm'
              : 'text-muted hover:text-main hover:bg-surface'
            }`}
        >
          <MessageSquare size={16} />
          <span>Channel & Text</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('roles')}
          className={`flex items-center gap-2 px-4! py-2.5! rounded-lg text-sm font-medium transition-all shrink-0 ${activeTab === 'roles'
              ? 'bg-primary text-white shadow-sm'
              : 'text-muted hover:text-main hover:bg-surface'
            }`}
        >
          <Shield size={16} />
          <span>Auto-Roles on Join</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('leave')}
          className={`flex items-center gap-2 px-4! py-2.5! rounded-lg text-sm font-medium transition-all shrink-0 ${activeTab === 'leave'
              ? 'bg-primary text-white shadow-sm'
              : 'text-muted hover:text-main hover:bg-surface'
            }`}
        >
          <LogOut size={16} />
          <span>Leave Alerts</span>
        </button>
      </div>

      {/* TAB 1: CARD DESIGN & LIVE PREVIEW */}
      {activeTab === 'card' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Configuration Controls (7 Cols) */}
          <div className="lg:col-span-6 xl:col-span-7 flex flex-col gap-5">
            {/* Style Selector */}
            <Card>
              <CardHeader>
                <div>
                  <CardTitle icon={Palette}>Card Graphic Style</CardTitle>
                  <CardDescription>Select the layout template for rendered welcome cards.</CardDescription>
                </div>
                <Badge variant="primary" size="sm">{activeStyleMeta.badge}</Badge>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2 gap-3.5">
                  {CARD_STYLES.map(style => {
                    const isSelected = config.card_style === style.id;
                    const StyleIcon = style.icon;
                    return (
                      <div
                        key={style.id}
                        onClick={() => setConfig({ ...config, card_style: style.id })}
                        role="button"
                        tabIndex={0}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && setConfig({ ...config, card_style: style.id })}
                        className={`p-3.5! sm:p-4! rounded-xl border cursor-pointer transition-all flex flex-col justify-between select-none ${isSelected
                            ? 'bg-primary/10 border-primary ring-1 ring-primary/40 shadow-sm'
                            : 'bg-surface border-border hover:border-border-hover hover:bg-card'
                          }`}
                      >
                        <div>
                          <div className="flex items-start justify-between gap-2 mb-1.5!">
                            <div className="flex items-center gap-2.5 min-w-0">
                              <div
                                className="w-7 h-7 rounded-lg flex items-center justify-center text-white shrink-0 shadow-sm"
                                style={{ backgroundColor: style.accent }}
                              >
                                <StyleIcon size={15} />
                              </div>
                              <div className="min-w-0">
                                <span className="text-sm font-semibold text-main truncate block">{style.label}</span>
                                <span className="text-[11px] text-muted block leading-tight">{style.badge}</span>
                              </div>
                            </div>
                            {isSelected ? (
                              <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0">
                                <Check size={13} className="font-bold" />
                              </div>
                            ) : (
                              <div className="w-5 h-5 rounded-full border border-border shrink-0" />
                            )}
                          </div>
                          <p className="text-xs text-muted leading-relaxed mt-2! line-clamp-2">
                            {style.desc}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Elements & Modes */}
            <Card>
              <CardHeader>
                <div>
                  <CardTitle icon={Sliders}>Card Elements & Modes</CardTitle>
                  <CardDescription>Fine-tune which visual layers are composited onto the banner.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-3.5">
                  <Toggle
                    label="Draw Member Avatar"
                    description="Renders the user profile photo on the card banner"
                    checked={config.draw_avatar}
                    onChange={v => setConfig(c => ({ ...c, draw_avatar: v }))}
                  />

                  <Toggle
                    label="Draw Text Overlays"
                    description="Renders username, welcome greeting & member count on the image"
                    checked={config.draw_text}
                    onChange={v => setConfig(c => ({ ...c, draw_text: v }))}
                  />

                  <Toggle
                    label="Display Server Icon"
                    description="Shows the server icon badge on supported card layouts"
                    checked={config.show_guild_icon}
                    onChange={v => setConfig(c => ({ ...c, show_guild_icon: v }))}
                  />

                  <Toggle
                    label="Embed Thumbnail"
                    description="Attaches user avatar as the Discord embed thumbnail"
                    checked={config.show_avatar}
                    onChange={v => setConfig(c => ({ ...c, show_avatar: v }))}
                  />

                  <Toggle
                    label="Post Mode: Card Only"
                    description="Posts solely the rendered banner image directly, omitting the text embed"
                    checked={config.card_only}
                    onChange={v => setConfig(c => ({ ...c, card_only: v }))}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Custom Background */}
            <Card>
              <CardHeader>
                <div>
                  <CardTitle icon={ImageIcon}>Custom Background</CardTitle>
                  <CardDescription>Direct image or GIF URL (recommended: 1024×500).</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                {config.has_background && (
                  <div className="flex items-center justify-between p-3! rounded-lg bg-success/10 border border-success/25 mb-4! text-xs">
                    <span className="text-success font-medium flex items-center gap-1.5">
                      <Check size={14} /> Custom server background active
                    </span>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => setConfig(c => ({ ...c, background_url: 'none', clear_background: true, has_background: false }))}
                    >
                      Remove
                    </Button>
                  </div>
                )}

                <div className="form-group mb-3!">
                  <input
                    type="text"
                    className="input-field"
                    placeholder="https://example.com/custom-background.png or .gif"
                    value={config.background_url}
                    onChange={e => setConfig({ ...config, background_url: e.target.value })}
                  />
                </div>

                <div>
                  <span className="text-xs text-muted block mb-2!">Or select a curated preset:</span>
                  <div className="flex flex-wrap gap-2 items-center">
                    {PRESET_BACKGROUNDS.map(p => (
                      <button
                        key={p.name}
                        type="button"
                        className={`btn btn-sm ${config.background_url === p.url ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setConfig({ ...config, background_url: p.url })}
                      >
                        {p.name}
                      </button>
                    ))}
                    {config.background_url && config.background_url !== 'none' && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm text-danger hover:bg-danger/10"
                        onClick={() => setConfig({ ...config, background_url: 'none' })}
                      >
                        Reset Background
                      </button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right Column: Live Interactive Card Mockup (5 Cols) */}
          <div className="lg:col-span-6 xl:col-span-5 lg:sticky lg:top-[76px]">
            <Card>
              <CardHeader>
                <div className="min-w-0">
                  <CardTitle icon={Sparkles}>Live Graphic Preview</CardTitle>
                  <CardDescription className="truncate">Real-time simulation of the 1024×500 rendered card.</CardDescription>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant="neutral" size="sm">1024 × 500 px</Badge>
                </div>
              </CardHeader>
              <CardContent>
                {/* 1024x500 Aspect Ratio Container */}
                <div className="relative w-full aspect-[1024/500] min-h-[190px] sm:min-h-[220px] rounded-xl overflow-hidden bg-[#090b10] border border-white/10 shadow-2xl flex items-center justify-center select-none">
                  {/* Background Layer */}
                  {config.background_url && config.background_url !== 'none' ? (
                    <div
                      className="absolute inset-0 bg-cover bg-center"
                      style={{
                        backgroundImage: `url(${config.background_url})`,
                        filter: config.card_style === 'glass' ? 'blur(3px)' : 'none',
                      }}
                    />
                  ) : null}

                  {/* 1. Legacy Neon Mockup */}
                  {config.card_style === 'legacy' && (
                    <div
                      className="relative w-full h-full flex items-center px-4! sm:px-8! gap-3.5 sm:gap-6 overflow-hidden"
                      style={{
                        background: config.background_url && config.background_url !== 'none'
                          ? 'rgba(10, 12, 20, 0.78)'
                          : 'radial-gradient(circle at 20% 30%, #1e1b4b 0%, #0c0f1d 70%, #070913 100%)',
                      }}
                    >
                      {/* Ambient Neon Blobs */}
                      <div className="absolute -top-10 -left-10 w-44 h-44 bg-purple-500/25 blur-3xl rounded-full pointer-events-none" />
                      <div className="absolute -bottom-10 -right-10 w-52 h-52 bg-cyan-500/20 blur-3xl rounded-full pointer-events-none" />

                      {/* Cyber grid lines */}
                      <div
                        className="absolute inset-0 opacity-[0.07] pointer-events-none"
                        style={{
                          backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
                          backgroundSize: '24px 24px',
                        }}
                      />

                      {/* Avatar */}
                      {config.draw_avatar && (
                        <div className="relative w-13 h-13 sm:w-18 sm:h-18 rounded-full bg-gradient-to-tr from-purple-500 via-indigo-500 to-cyan-400 p-[2px]! shadow-[0_0_20px_rgba(168,85,247,0.4)] shrink-0 z-10">
                          <div className="w-full h-full rounded-full bg-gray-950 flex items-center justify-center text-white">
                            <User size={26} className="text-cyan-300" />
                          </div>
                          <span className="absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full bg-emerald-500 border-2 border-gray-950 shadow" />
                        </div>
                      )}

                      {/* Text */}
                      {config.draw_text ? (
                        <div className="relative z-10 min-w-0 flex-1">
                          <div className="text-[9px] sm:text-[11px] font-bold tracking-widest text-cyan-400 uppercase mb-0.5! flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 inline-block animate-pulse shrink-0" />
                            <span className="truncate">WELCOME TO THE SERVER</span>
                          </div>
                          <div className="text-base sm:text-xl font-extrabold text-white leading-tight truncate drop-shadow-md">
                            NewUser#0001
                          </div>
                          <div className="inline-flex items-center gap-1.5 bg-white/10 backdrop-blur-md px-2.5! py-0.5! rounded-full text-[10px] sm:text-[11px] text-gray-200 mt-1.5! border border-white/15 max-w-full">
                            <span className="shrink-0">Member #1,234</span>
                            {config.show_guild_icon && (
                              <span className="flex items-center gap-1 text-cyan-300 truncate">
                                • <Globe size={11} className="shrink-0" /> <span className="truncate">Community</span>
                              </span>
                            )}
                          </div>
                        </div>
                      ) : !config.draw_avatar ? (
                        <div className="text-xs text-muted/60 text-center w-full z-10">
                          [Graphic banner background only — overlays disabled]
                        </div>
                      ) : null}
                    </div>
                  )}

                  {/* 2. Minimalist Glass Mockup */}
                  {config.card_style === 'glass' && (
                    <div
                      className="relative w-full h-full flex flex-col items-center justify-center p-3! sm:p-4! overflow-hidden"
                      style={{
                        background: config.background_url && config.background_url !== 'none'
                          ? 'rgba(12, 14, 24, 0.72)'
                          : 'linear-gradient(145deg, #0d111c 0%, #151928 50%, #0a0d16 100%)',
                      }}
                    >
                      {/* Frosted Center Glass Tile */}
                      <div className="relative w-[90%] max-w-[420px] rounded-2xl bg-white/[0.04] border border-white/15 backdrop-blur-md shadow-2xl flex flex-col items-center justify-center p-3! sm:p-4! text-center my-auto!">
                        <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-indigo-400/50 to-transparent" />

                        {config.draw_avatar && (
                          <div className="relative w-12 h-12 sm:w-16 sm:h-16 rounded-full border-2 border-white/30 shadow-xl bg-gray-900/80 flex items-center justify-center text-white mb-2! z-10 ring-4 ring-indigo-500/20 shrink-0">
                            <User size={24} className="text-indigo-300" />
                          </div>
                        )}

                        {config.draw_text ? (
                          <div className="z-10 min-w-0 max-w-full">
                            <div className="text-sm sm:text-base font-bold text-white tracking-wide truncate">
                              NewUser
                            </div>
                            <div className="text-[10px] sm:text-[11px] text-indigo-200/80 mt-0.5! truncate">
                              Welcome to the server • Member #1,234
                            </div>
                            {config.show_guild_icon && (
                              <div className="mt-1! text-[9px] sm:text-[10px] text-white/50 flex items-center justify-center gap-1 truncate">
                                <Globe size={10} className="shrink-0" /> <span className="truncate">Verified Discord Server</span>
                              </div>
                            )}
                          </div>
                        ) : !config.draw_avatar ? (
                          <div className="text-xs text-muted/60 text-center w-full z-10">
                            [Glass container with overlays disabled]
                          </div>
                        ) : null}
                      </div>
                    </div>
                  )}

                  {/* 3. Ticket Pass Mockup */}
                  {config.card_style === 'ticket' && (
                    <div
                      className="relative w-full h-full flex items-center justify-center p-2.5! sm:p-4!"
                      style={{
                        background: config.background_url && config.background_url !== 'none'
                          ? 'rgba(10, 11, 18, 0.75)'
                          : 'linear-gradient(135deg, #12141f 0%, #0d0e17 100%)',
                      }}
                    >
                      <div className="relative w-[95%] h-[90%] bg-[#171926] rounded-xl border border-pink-500/30 flex shadow-2xl overflow-hidden">
                        {/* Left section: Ticket Main */}
                        <div className="flex-[3] p-3! sm:p-3.5! flex flex-col justify-between min-w-0 h-full">
                          <div className="flex justify-between items-center text-[9px] sm:text-[10px]">
                            <span className="font-bold text-pink-400 tracking-wider truncate">VIP BOARDING PASS</span>
                            <span className="text-white/40 font-mono shrink-0 ml-2!">#001234</span>
                          </div>

                          <div className="flex items-center gap-2.5 my-1! min-w-0">
                            {config.draw_avatar && (
                              <div className="w-9 h-9 sm:w-11 sm:h-11 rounded-lg bg-gray-900 border border-pink-500/40 flex items-center justify-center text-pink-300 shrink-0">
                                <User size={18} />
                              </div>
                            )}
                            {config.draw_text ? (
                              <div className="min-w-0 flex-1">
                                <div className="text-xs sm:text-sm font-bold text-white leading-tight truncate">
                                  NewUser
                                </div>
                                <div className="text-[9px] sm:text-[10px] text-gray-400 truncate">
                                  Granted Member Clearance
                                </div>
                              </div>
                            ) : null}
                          </div>

                          <div className="flex justify-between border-t border-white/10 pt-1! text-[8px] sm:text-[9px] text-gray-400 font-mono gap-1 min-w-0 overflow-hidden">
                            <span className="truncate">GATE: 01</span>
                            <span className="truncate">DATE: TODAY</span>
                            {config.show_guild_icon && <span className="truncate">AUTH: OK</span>}
                          </div>
                        </div>

                        {/* Perforated Divider */}
                        <div className="w-0 border-l border-dashed border-white/20 relative shrink-0">
                          <div className="absolute -top-1.5 -left-1.5 w-3 h-3 rounded-full bg-[#090b10]" />
                          <div className="absolute -bottom-1.5 -left-1.5 w-3 h-3 rounded-full bg-[#090b10]" />
                        </div>

                        {/* Right Stub: Barcode */}
                        <div className="flex-1 bg-pink-500/10 p-2! sm:p-2.5! flex flex-col items-center justify-between shrink-0 min-w-[56px] h-full">
                          <span className="text-[7px] sm:text-[8px] font-bold text-pink-400 uppercase tracking-widest">ADMIT</span>
                          <div className="flex gap-0.5 h-5 sm:h-6 items-center">
                            {[2, 3, 1, 3, 2, 3, 1, 2].map((w, idx) => (
                              <div key={idx} className="bg-white/60" style={{ width: `${w}px`, height: '100%' }} />
                            ))}
                          </div>
                          <span className="text-[7px] sm:text-[8px] text-gray-400 font-mono">VALID</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 4. Cinematic Poster Mockup */}
                  {config.card_style === 'cinematic' && (
                    <div
                      className="relative w-full h-full flex flex-col justify-between overflow-hidden"
                      style={{
                        background: config.background_url && config.background_url !== 'none'
                          ? 'rgba(4, 7, 14, 0.7)'
                          : 'radial-gradient(circle at 75% 50%, #0d2827 0%, #08151c 45%, #04070e 100%)',
                      }}
                    >
                      {/* Top Letterbox Cinema Bar */}
                      <div className="relative z-10 w-full px-3! sm:px-4! py-1.5! bg-black/75 backdrop-blur-sm border-b border-teal-500/20 flex justify-between items-center text-[8px] sm:text-[9px] tracking-wider text-teal-400 font-mono gap-2 min-w-0 overflow-hidden">
                        <span className="font-bold border-b border-teal-400/80 pb-0.5! truncate">
                          MEMBER NO. 1,234
                        </span>
                        <span className="text-white/60 uppercase truncate">
                          ARRIVAL RECEPTION TERMINAL
                        </span>
                      </div>

                      {/* Center Stage Dramatic Area */}
                      <div className="relative z-10 flex items-center px-4! sm:px-8! gap-3 sm:gap-5 my-auto! min-w-0">
                        {config.draw_avatar && (
                          <div className="relative w-13 h-13 sm:w-16 sm:h-16 rounded-full border-2 border-teal-400/80 bg-gray-950 flex items-center justify-center text-teal-300 shadow-[0_0_24px_rgba(20,184,166,0.4)] shrink-0">
                            <User size={24} />
                          </div>
                        )}

                        {config.draw_text ? (
                          <div className="min-w-0 flex-1">
                            <div className="text-base sm:text-xl font-black text-white uppercase tracking-tight truncate drop-shadow-lg">
                              NEWUSER
                            </div>
                            <div className="text-[10px] sm:text-xs text-teal-300 font-medium tracking-wide uppercase mt-0.5! truncate">
                              has joined the community
                            </div>
                          </div>
                        ) : !config.draw_avatar ? (
                          <div className="text-xs text-teal-400/60 text-center w-full">
                            [Cinematic Letterbox Canvas • Overlays Disabled]
                          </div>
                        ) : null}
                      </div>

                      {/* Bottom Letterbox Cinema Bar */}
                      <div className="relative z-10 w-full px-3! sm:px-4! py-1.5! bg-black/75 backdrop-blur-sm border-t border-teal-500/20 flex justify-between items-center text-[8px] sm:text-[9px] text-gray-400 font-mono gap-2 min-w-0 overflow-hidden">
                        <span className="truncate">STATUS: AUTHORIZED</span>
                        {config.show_guild_icon && <span className="hidden sm:inline truncate">VERIFIED GUILD</span>}
                        <span className="truncate">SECURE ARRIVAL</span>
                      </div>
                    </div>
                  )}

                  {/* Watermark Tag */}
                  {config.card_style !== 'cinematic' && (
                    <div className="absolute top-2.5 right-2.5 z-20 pointer-events-none opacity-40 hover:opacity-100 transition-opacity">
                      <span className="text-[9px] font-mono text-white/70 bg-black/50 px-1.5! py-0.5! rounded">
                        Live Simulation
                      </span>
                    </div>
                  )}
                </div>

                <div className="mt-3! text-center text-xs text-muted">
                  Interactive real-time preview reflecting your selected visual style and element toggles.
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* TAB 2: CHANNEL & MESSAGE TEXT */}
      {activeTab === 'message' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={MessageSquare}>Delivery Channel & Content</CardTitle>
                <CardDescription>Specify where the greeting posts and customize text variables.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="form-group mb-4!">
                <label className="form-label">Welcome Channel</label>
                <Select
                  value={config.channel_id}
                  onChange={v => setConfig({ ...config, channel_id: v })}
                  options={channelOptions}
                  searchable
                />
                {channelsError && (
                  <div className="flex items-center justify-between gap-3 mt-2! text-xs text-danger">
                    <span>{channelsError}</span>
                    <button type="button" onClick={fetchData} className="underline shrink-0">Retry</button>
                  </div>
                )}
              </div>

              <div className="form-group mb-4!">
                <label className="form-label">Welcome Message Text</label>
                <textarea
                  className="input-field min-h-[120px] font-mono text-sm leading-relaxed"
                  value={config.message}
                  onChange={e => setConfig({ ...config, message: e.target.value })}
                  placeholder="Welcome to the server, {user}! 🎉"
                />
              </div>

              <div>
                <label className="form-label mb-2! block">Dynamic Text Variables</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {PLACEHOLDERS.map(p => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => setConfig(c => ({ ...c, message: `${c.message} ${p.label}` }))}
                      className="p-2! rounded-lg bg-surface border border-border text-left hover:border-primary/50 transition-colors"
                    >
                      <code className="text-xs font-bold text-primary block">{p.label}</code>
                      <span className="text-[11px] text-muted">{p.desc}</span>
                    </button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={Bot}>Discord Message Simulation</CardTitle>
                <CardDescription>Approximation of the Discord client message delivery.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="p-4! rounded-xl bg-[#1e1f22] border border-[#2b2d31] font-sans text-sm text-gray-200">
                <div className="flex items-center gap-2 mb-2!">
                  <span className="font-bold text-white">{botName || 'GKR Bot'}</span>
                  <span className="bg-[#5865f2] text-[10px] text-white font-semibold px-1! py-0.2! rounded">BOT</span>
                  <span className="text-xs text-gray-400">Today at 12:00 PM</span>
                </div>
                <div className="text-gray-100 whitespace-pre-line leading-relaxed mb-3! break-words">
                  {config.message
                    .replace('{user}', '@NewUser')
                    .replace('{username}', 'NewUser')
                    .replace('{server}', 'My Awesome Discord')
                    .replace('{count}', '1,234')}
                </div>
                {!config.card_only && (
                  <div className="text-xs text-indigo-400 bg-indigo-500/10 p-2! rounded border border-indigo-500/20">
                    🖼️ Card banner graphic is attached to this greeting.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 3: AUTO-ROLES ON JOIN */}
      {activeTab === 'roles' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={Shield}>Human Member Onboarding Role</CardTitle>
                <CardDescription>Automatically granted to regular users upon joining.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="form-group">
                <label className="form-label">Member Role</label>
                <Select
                  value={config.welcome_role_id}
                  onChange={v => setConfig({ ...config, welcome_role_id: v })}
                  options={roleOptions}
                  searchable
                />
              </div>
              <p className="text-xs text-muted mt-2!">
                Make sure the bot's highest role is positioned above this role in Server Settings &gt; Roles.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={Bot}>Bot Integration Role</CardTitle>
                <CardDescription>Automatically granted to newly authorized bot applications.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="form-group">
                <label className="form-label">Bot Role</label>
                <Select
                  value={config.bot_role_id}
                  onChange={v => setConfig({ ...config, bot_role_id: v })}
                  options={roleOptions}
                  searchable
                />
              </div>
              <p className="text-xs text-muted mt-2!">
                Useful for categorizing automated integrations separate from regular members.
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 4: LEAVE ALERTS */}
      {activeTab === 'leave' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={LogOut}>Departure Notifications</CardTitle>
                <CardDescription>Post an announcement when a member leaves or is removed.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-4!">
                <Toggle
                  label="Enable Leave Alerts"
                  description="Broadcast departure messages when members exit the server"
                  checked={config.leave_enabled}
                  onChange={v => setConfig({ ...config, leave_enabled: v })}
                />
              </div>

              {config.leave_enabled && (
                <div className="flex flex-col gap-4 pt-4! border-t border-border">
                  <div className="form-group">
                    <label className="form-label">Departure Log Channel</label>
                    <Select
                      value={config.leave_channel_id}
                      onChange={v => setConfig({ ...config, leave_channel_id: v })}
                      options={channelOptions}
                      searchable
                    />
                    {channelsError && (
                      <div className="flex items-center justify-between gap-3 mt-2! text-xs text-danger">
                        <span>{channelsError}</span>
                        <button type="button" onClick={fetchData} className="underline shrink-0">Retry</button>
                      </div>
                    )}
                  </div>

                  <div className="form-group">
                    <label className="form-label">Departure Message Text</label>
                    <textarea
                      className="input-field min-h-[100px] font-mono text-sm leading-relaxed"
                      value={config.leave_message}
                      onChange={e => setConfig({ ...config, leave_message: e.target.value })}
                      placeholder="**{user}** left the server."
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Departure Image URL (Optional)</label>
                    <input
                      type="text"
                      className="input-field"
                      placeholder="https://example.com/farewell.gif"
                      value={config.leave_image_url}
                      onChange={e => setConfig({ ...config, leave_image_url: e.target.value })}
                    />
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Departure Message Simulation */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={Bot}>Departure Message Simulation</CardTitle>
                <CardDescription>Approximation of the departure notice in Discord.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="p-4! rounded-xl bg-[#1e1f22] border border-[#2b2d31] font-sans text-sm text-gray-200">
                <div className="flex items-center gap-2 mb-2!">
                  <span className="font-bold text-white">{botName || 'GKR Bot'}</span>
                  <span className="bg-[#5865f2] text-[10px] text-white font-semibold px-1! py-0.2! rounded">BOT</span>
                  <span className="text-xs text-gray-400">Today at 12:00 PM</span>
                </div>
                <div className="text-gray-100 whitespace-pre-line leading-relaxed mb-3! break-words">
                  {config.leave_message
                    .replace('{user}', 'DepartedMember')
                    .replace('{username}', 'DepartedMember')
                    .replace('{server}', 'My Awesome Discord')
                    .replace('{count}', '1,233')}
                </div>
                {config.leave_image_url && (
                  <div className="mt-2! rounded-lg overflow-hidden border border-white/10 max-h-48 bg-black/40">
                    <img
                      src={config.leave_image_url}
                      alt="Departure attachment preview"
                      className="w-full h-auto object-cover max-h-48"
                      onError={e => { e.currentTarget.style.display = 'none'; }}
                    />
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {(isDirty || saving || saved) && (
        <div className="sticky bottom-4 z-40 mt-8!">
          <div className="p-3.5! sm:p-4! rounded-2xl bg-card/95 backdrop-blur-md border border-border shadow-2xl flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 sm:gap-4 max-w-3xl mx-auto!">
            <div className="flex items-center gap-2">
              {isDirty ? (
                <span className="text-xs font-semibold text-warning flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-warning animate-pulse shrink-0" />
                  <span>Unsaved changes pending</span>
                </span>
              ) : saved ? (
                <span className="text-xs font-semibold text-success flex items-center gap-1.5">
                  <Check size={14} className="shrink-0" /> <span>Settings saved successfully</span>
                </span>
              ) : (
                <span className="text-xs text-muted">All settings saved to server</span>
              )}
            </div>

            <div className="flex items-center gap-2.5 justify-end">
              {isDirty && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleReset}
                  disabled={saving}
                >
                  Discard
                </Button>
              )}

              <Button
                variant="primary"
                size="sm"
                icon={Save}
                loading={saving}
                onClick={handleSave}
                disabled={!isDirty && !saving}
              >
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Sync Servers Modal */}
      {syncOpen && (
        <SyncModal
          isOpen={syncOpen}
          onClose={() => setSyncOpen(false)}
          sourceGuildId={guildId}
          featureKey="welcome"
          featureTitle="Welcome & Leave Studio"
        />
      )}
    </div>
  );
}

export default Welcome;