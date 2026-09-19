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
  HelpCircle
} from 'lucide-react';

const CARD_STYLES = [
  {
    id: 'legacy',
    label: 'Legacy Neon',
    desc: 'Dual-tone glow with avatar ring and cyber accents',
    badge: 'Classic',
    accent: '#8b5cf6',
  },
  {
    id: 'glass',
    label: 'Minimalist Glass',
    desc: 'Centered avatar with frosted blur and halo glow',
    badge: 'Modern',
    accent: '#6366f1',
  },
  {
    id: 'ticket',
    label: 'Ticket Pass',
    desc: 'VIP boarding pass with tear-off stub and barcode',
    badge: 'VIP Pass',
    accent: '#ec4899',
  },
  {
    id: 'cinematic',
    label: 'Cinematic Poster',
    desc: 'Bold editorial typography with wide letterbox layout',
    badge: 'Impact',
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
    try {
      setLoading(true);
      const [welcomeRes, channelsRes, rolesRes] = await Promise.all([
        api.get(`/guilds/${guildId}/welcome`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/roles`).catch(() => ({ data: { roles: [] } })),
      ]);

      if (welcomeRes.data.config) {
        const c = welcomeRes.data.config;
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
      setChannels(channelsRes.data.channels || []);
      setRoles(rolesRes.data.roles || []);
      setError('');
    } catch (err) {
      console.error('Failed to fetch welcome config', err);
      setError(err.response?.data?.error || 'Failed to load welcome configuration');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Unsaved changes detection
  const isDirty = useMemo(() => {
    if (!savedConfig) return false;
    return (
      config.enabled !== savedConfig.enabled ||
      config.channel_id !== savedConfig.channel_id ||
      config.message !== savedConfig.message ||
      config.card_style !== savedConfig.card_style ||
      config.card_only !== savedConfig.card_only ||
      Boolean(config.background_url) ||
      config.clear_background ||
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

  const handleDiscard = () => {
    if (savedConfig) {
      setConfig({ ...savedConfig, background_url: '', clear_background: false });
    }
  };

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const payload = { ...config };
      if (!payload.background_url) {
        delete payload.background_url;
      }
      await api.post(`/guilds/${guildId}/welcome`, withSync(payload));
      setSaved(true);
      setSavedConfig({ ...config, background_url: '', clear_background: false });
      setTimeout(() => setSaved(false), 2500);
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save welcome configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (type) => {
    if (type === 'welcome') setTestingWelcome(true);
    else setTestingLeave(true);
    setTestNotice(null);

    try {
      const res = await api.post(`/guilds/${guildId}/welcome/test`, { type });
      setTestNotice({ type: 'success', message: res.data?.message || `Test ${type} dispatched to Discord!` });
      setTimeout(() => setTestNotice(null), 5000);
    } catch (err) {
      setTestNotice({ type: 'error', message: err.response?.data?.error || `Failed to dispatch test ${type}` });
    } finally {
      if (type === 'welcome') setTestingWelcome(false);
      else setTestingLeave(false);
    }
  };

  const activeStyleMeta = CARD_STYLES.find(s => s.id === config.card_style) || CARD_STYLES[0];

  if (loading && !savedConfig) {
    return (
      <div className="flex flex-col gap-6 animate-fade-in">
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="w-48 h-6 bg-surface rounded animate-pulse mb-2" />
              <div className="w-72 h-4 bg-surface rounded animate-pulse" />
            </div>
            <div className="w-12 h-6 bg-surface rounded-full animate-pulse" />
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card p-6 h-96" />
          <div className="card p-6 h-96" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      {/* Page Header with Actions */}
      <PageHeader
        icon={UserPlus}
        title="Welcome & Leave Studio"
        subtitle="Configure greeting cards, arrival channels, role automation, and departure alerts."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={Send}
              loading={testingWelcome}
              disabled={!config.channel_id}
              onClick={() => handleTest('welcome')}
              title={!config.channel_id ? 'Select a welcome channel first' : 'Send test card to Discord'}
            >
              Test Welcome
            </Button>
            <Button
              variant="outline"
              size="sm"
              icon={Sliders}
              onClick={() => setSyncOpen(true)}
            >
              Sync Servers
            </Button>
          </div>
        }
      />

      {/* Inline Feedback Alerts */}
      {error && (
        <div className="alert alert-error">
          <AlertCircle size={18} className="shrink-0" />
          <div className="flex-1">{error}</div>
        </div>
      )}

      {testNotice && (
        <div className={`alert ${testNotice.type === 'success' ? 'alert-success' : 'alert-error'}`}>
          <div className="flex-1">{testNotice.message}</div>
          <button
            type="button"
            onClick={() => setTestNotice(null)}
            className="text-muted hover:text-main"
            style={{ background: 'none', border: 'none', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Global Enable / Disable Card */}
      <div className="card p-5 flex items-center justify-between gap-4 border-border">
        <div className="flex items-center gap-4">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold ${
            config.enabled ? 'bg-success/15 text-success border border-success/30' : 'bg-surface text-muted border border-border'
          }`}>
            <Sparkles size={20} />
          </div>
          <div>
            <div className="text-sm font-semibold text-main">
              Welcome Automation System is {config.enabled ? 'Enabled' : 'Disabled'}
            </div>
            <div className="text-xs text-muted">
              {config.enabled
                ? 'Welcome cards and greetings will be delivered automatically whenever a member joins.'
                : 'Turn this on to begin greeting incoming members.'}
            </div>
          </div>
        </div>

        <Toggle
          checked={config.enabled}
          onChange={(v) => setConfig(c => ({ ...c, enabled: v }))}
          size="md"
        />
      </div>

      {/* Modern Workspace Navigation Tabs */}
      <div className="nav-tabs">
        <button
          type="button"
          className={`nav-tab-item ${activeTab === 'card' ? 'active' : ''}`}
          onClick={() => setActiveTab('card')}
        >
          <Palette size={16} />
          <span>Card Design & Layout</span>
        </button>

        <button
          type="button"
          className={`nav-tab-item ${activeTab === 'message' ? 'active' : ''}`}
          onClick={() => setActiveTab('message')}
        >
          <MessageSquare size={16} />
          <span>Channel & Text</span>
        </button>

        <button
          type="button"
          className={`nav-tab-item ${activeTab === 'autorole' ? 'active' : ''}`}
          onClick={() => setActiveTab('autorole')}
        >
          <Shield size={16} />
          <span>Auto-Roles on Join</span>
        </button>

        <button
          type="button"
          className={`nav-tab-item ${activeTab === 'leave' ? 'active' : ''}`}
          onClick={() => setActiveTab('leave')}
        >
          <LogOut size={16} />
          <span>Leave Alerts</span>
        </button>
      </div>

      {/* TAB 1: CARD DESIGN & LAYOUT */}
      {activeTab === 'card' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          {/* Left Column: Card Options */}
          <div className="flex flex-col gap-5">
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
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {CARD_STYLES.map(style => {
                    const isSelected = config.card_style === style.id;
                    return (
                      <div
                        key={style.id}
                        onClick={() => setConfig({ ...config, card_style: style.id })}
                        className={`p-3.5 rounded-lg border cursor-pointer transition-all flex flex-col justify-between ${
                          isSelected
                            ? 'bg-primary/10 border-primary shadow-sm ring-1 ring-primary/30'
                            : 'bg-surface border-border hover:border-border-hover'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-sm font-semibold text-main">{style.label}</span>
                          {isSelected && <Check size={14} className="text-primary" />}
                        </div>
                        <p className="text-xs text-muted line-clamp-2 leading-relaxed">
                          {style.desc}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Overlays & Elements */}
            <Card>
              <CardHeader>
                <div>
                  <CardTitle icon={Sliders}>Card Elements & Modes</CardTitle>
                  <CardDescription>Toggle which details to render on the generated image.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-3">
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
                  <div className="flex items-center justify-between p-3 rounded-lg bg-success/10 border border-success/25 mb-4 text-xs">
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

                <div className="form-group mb-3">
                  <input
                    type="text"
                    className="input-field"
                    placeholder="https://example.com/custom-background.png or .gif"
                    value={config.background_url}
                    onChange={e => setConfig({ ...config, background_url: e.target.value })}
                  />
                </div>

                <div>
                  <span className="text-xs text-muted block mb-2">Or select a curated preset:</span>
                  <div className="flex flex-wrap gap-2">
                    {PRESET_BACKGROUNDS.map(p => (
                      <button
                        key={p.name}
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setConfig({ ...config, background_url: p.url })}
                      >
                        {p.name}
                      </button>
                    ))}
                    {config.background_url && (
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => setConfig({ ...config, background_url: 'none' })}
                      >
                        Reset
                      </button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right Column: Live Interactive Card Mockup */}
          <div className="lg:sticky lg:top-24">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle icon={Sparkles}>Live Graphic Preview</CardTitle>
                  <CardDescription>Real-time simulation of the 1024×500 rendered card.</CardDescription>
                </div>
                <Badge variant="neutral" size="sm">1024 × 500</Badge>
              </CardHeader>
              <CardContent>
                <div className="relative w-full aspect-[1024/500] rounded-xl overflow-hidden bg-[#11141c] border border-white/10 shadow-lg flex items-center justify-center">
                  {/* Background Layer */}
                  {config.background_url && config.background_url !== 'none' && (
                    <div
                      className="absolute inset-0 bg-cover bg-center opacity-85"
                      style={{
                        backgroundImage: `url(${config.background_url})`,
                        filter: config.card_style === 'glass' ? 'blur(3px)' : 'none',
                      }}
                    />
                  )}

                  {/* 1. Legacy Neon Mockup */}
                  {config.card_style === 'legacy' && (
                    <div
                      className="relative w-full h-full flex items-center px-8 sm:px-12 gap-6 sm:gap-8"
                      style={{
                        background: config.background_url && config.background_url !== 'none'
                          ? 'rgba(10, 12, 18, 0.78)'
                          : 'linear-gradient(135deg, #0d0f1a 0%, #15102a 60%, #0a1128 100%)',
                      }}
                    >
                      <div className="absolute top-[-10%] left-[15%] w-48 h-48 bg-purple-500/30 blur-3xl rounded-full" />
                      <div className="absolute bottom-[-10%] right-[10%] w-56 h-56 bg-cyan-500/25 blur-3xl rounded-full" />

                      {config.draw_avatar && (
                        <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-full bg-gradient-to-tr from-purple-500 to-blue-500 p-1 shadow-lg shrink-0 z-10">
                          <div className="w-full h-full rounded-full bg-gray-900 flex items-center justify-center text-white text-2xl">
                            <User size={36} />
                          </div>
                        </div>
                      )}

                      {config.draw_text && (
                        <div className="relative z-10">
                          <div className="text-[11px] sm:text-xs font-bold tracking-widest text-cyan-400 uppercase mb-1">
                            Welcome to the Server
                          </div>
                          <div className="text-xl sm:text-2xl font-extrabold text-white leading-tight mb-2">
                            NewUser#0001
                          </div>
                          <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-sm px-2.5 py-1 rounded-full text-xs text-gray-200">
                            <span>Member #1,234</span>
                            {config.show_guild_icon && <span>• Server</span>}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 2. Minimalist Glass Mockup */}
                  {config.card_style === 'glass' && (
                    <div
                      className="relative w-full h-full flex flex-col items-center justify-center"
                      style={{
                        background: config.background_url && config.background_url !== 'none'
                          ? 'rgba(10, 12, 18, 0.75)'
                          : 'linear-gradient(180deg, #13151f 0%, #171926 100%)',
                      }}
                    >
                      <div className="absolute top-[20%] w-56 h-32 bg-indigo-500/35 blur-3xl rounded-full" />

                      {config.draw_avatar && (
                        <div className="relative w-20 h-20 sm:w-22 sm:h-22 rounded-full border-2 border-white/40 shadow-xl bg-gray-800 flex items-center justify-center text-white text-2xl mb-3 z-10">
                          <User size={32} />
                        </div>
                      )}

                      {config.draw_text && (
                        <div className="text-center z-10">
                          <div className="text-lg sm:text-xl font-bold text-white mb-1">
                            NewUser
                          </div>
                          <div className="text-xs text-white/70">
                            Welcome to the server • Member #1,234
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 3. Ticket Pass Mockup */}
                  {config.card_style === 'ticket' && (
                    <div className="relative w-[92%] h-[82%] bg-[#171922] rounded-xl border border-white/15 flex shadow-2xl overflow-hidden">
                      <div className="flex-[3] p-4 sm:p-5 flex flex-col justify-between">
                        <div className="flex justify-between items-center text-[10px]">
                          <span className="font-bold text-pink-400 tracking-wider">VIP PASS • ENTRY</span>
                          <span className="text-white/40 font-mono">#001234</span>
                        </div>

                        <div className="flex items-center gap-3 my-2">
                          {config.draw_avatar && (
                            <div className="w-12 h-12 rounded-lg bg-gray-800 border border-pink-500/50 flex items-center justify-center text-white shrink-0">
                              <User size={22} />
                            </div>
                          )}
                          {config.draw_text && (
                            <div>
                              <div className="text-base font-bold text-white leading-tight">NewUser</div>
                              <div className="text-[11px] text-gray-400">Granted Member Access</div>
                            </div>
                          )}
                        </div>

                        <div className="flex justify-between border-t border-white/10 pt-2 text-[10px] text-gray-400">
                          <span>GATE: 01</span>
                          <span>DATE: TODAY</span>
                        </div>
                      </div>

                      <div className="w-0 border-l border-dashed border-white/20 relative" />

                      <div className="flex-1 bg-pink-500/10 p-3 flex flex-col items-center justify-between">
                        <span className="text-[9px] font-bold text-pink-400 uppercase">ADMIT</span>
                        <div className="flex gap-0.5 h-7 items-center">
                          {[3, 2, 4, 1, 3, 2, 4, 2].map((w, idx) => (
                            <div key={idx} className="bg-white/50" style={{ width: `${w}px`, height: '100%' }} />
                          ))}
                        </div>
                        <span className="text-[8px] text-gray-400 font-mono">VALID</span>
                      </div>
                    </div>
                  )}

                  {/* 4. Cinematic Poster Mockup */}
                  {config.card_style === 'cinematic' && (
                    <div
                      className="relative w-full h-full flex flex-col justify-between p-6 sm:p-8"
                      style={{
                        background: config.background_url && config.background_url !== 'none'
                          ? 'none'
                          : 'linear-gradient(135deg, #0a0d16 0%, #040710 100%)',
                      }}
                    >
                      <div className="flex justify-between items-center z-10 text-[10px]">
                        <span className="font-bold text-teal-400 tracking-wider border-b border-teal-400 pb-0.5">
                          MEMBER No. 1,234
                        </span>
                        <span className="text-white/60 font-semibold tracking-wider">
                          ARRIVAL RECEPTION
                        </span>
                      </div>

                      <div className="z-10">
                        <div className="text-2xl sm:text-3xl font-black text-white uppercase tracking-tight">
                          NEWUSER
                        </div>
                        <div className="text-xs text-teal-300 mt-1">
                          has joined the community
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* TAB 2: CHANNEL & MESSAGE TEXT */}
      {activeTab === 'message' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          {/* Form */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={MessageSquare}>Delivery Channel & Content</CardTitle>
                <CardDescription>Specify where the greeting posts and customize text variables.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="form-group mb-5">
                <label className="form-label">Welcome Text Channel</label>
                <Select
                  value={config.channel_id}
                  onChange={v => setConfig({ ...config, channel_id: v })}
                  options={channels.map(ch => ({ value: ch.id, label: '# ' + ch.name }))}
                  placeholder="Select a channel..."
                  searchable
                />
                <span className="form-hint">
                  The target Discord text channel where the welcome message will dispatch.
                </span>
              </div>

              <div className="form-group mb-4">
                <label className="form-label">Welcome Message Text</label>
                <textarea
                  className="input-field font-mono text-sm"
                  rows={5}
                  value={config.message}
                  onChange={e => setConfig({ ...config, message: e.target.value })}
                  placeholder="Welcome to {server}, {user}! 🎉"
                />
              </div>

              <div>
                <label className="form-label mb-2 block">Dynamic Placeholders</label>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {PLACEHOLDERS.map(p => (
                    <button
                      key={p.label}
                      type="button"
                      className="badge badge-primary cursor-pointer hover:bg-primary/20"
                      title={p.desc}
                      onClick={() => setConfig(c => ({ ...c, message: (c.message + ' ' + p.label).trim() }))}
                    >
                      + {p.label}
                    </button>
                  ))}
                </div>
                <span className="form-hint">
                  Click any variable to append it to your message.
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Discord Chat Mockup Preview */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={Bot}>Discord Message Preview</CardTitle>
                <CardDescription>Accurate preview of the Discord embed presentation.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="bg-[#313338] rounded-lg p-4 border border-white/5 flex gap-3.5">
                <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-white shrink-0">
                  <Bot size={20} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-2 mb-1">
                    <span className="text-sm font-semibold text-white">{botName || 'GKR'} Bot</span>
                    <span className="text-[10px] bg-[#5865F2] text-white px-1.5 py-0.5 rounded font-bold uppercase">APP</span>
                    <span className="text-xs text-[#949ba4]">Today at 12:00 PM</span>
                  </div>

                  <div className="text-sm text-[#dbdee1] leading-relaxed whitespace-pre-wrap mb-3">
                    {config.message
                      .replace(/{user}/g, '@NewMember')
                      .replace(/{username}/g, 'NewMember')
                      .replace(/{server}/g, 'Family Server')
                      .replace(/{count}/g, '1,234') || 'Type a message on the left to preview...'}
                  </div>

                  {/* Attachment card representation */}
                  <div className="max-w-xs rounded-lg bg-[#1e1f22] p-3 border border-white/10 flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-primary/20 flex items-center justify-center text-primary">
                      <ImageIcon size={18} />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-white">welcome_card.png</div>
                      <div className="text-[11px] text-[#949ba4]">{activeStyleMeta.label} Layout</div>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 3: AUTO-ROLES ON JOIN */}
      {activeTab === 'autorole' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
          {/* Member Auto-Role */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={User}>Human Member Auto-Role</CardTitle>
                <CardDescription>Assigned automatically to standard human users upon joining.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="form-group mb-0">
                <Select
                  value={config.welcome_role_id}
                  onChange={v => setConfig({ ...config, welcome_role_id: v })}
                  options={[
                    { value: '', label: 'None (Disabled)' },
                    ...roles.map(r => ({ value: r.id, label: '@ ' + r.name }))
                  ]}
                  placeholder="Select a member role..."
                  searchable
                />
                <span className="form-hint">
                  Ensure the bot's highest role is positioned above this role in Server Settings &gt; Roles.
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Bot Auto-Role */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={Bot}>Bot Integration Auto-Role</CardTitle>
                <CardDescription>Assigned automatically to newly authorized bot integrations.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="form-group mb-0">
                <Select
                  value={config.bot_role_id}
                  onChange={v => setConfig({ ...config, bot_role_id: v })}
                  options={[
                    { value: '', label: 'None (Disabled)' },
                    ...roles.map(r => ({ value: r.id, label: '@ ' + r.name }))
                  ]}
                  placeholder="Select a bot role..."
                  searchable
                />
                <span className="form-hint">
                  Useful for segregating bot accounts under an exclusive "Bots" role.
                </span>
              </div>
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
                <CardTitle icon={LogOut}>Departure Announcements</CardTitle>
                <CardDescription>Broadcast an alert whenever a member leaves or gets kicked.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-5">
                <Toggle
                  label="Enable Leave Announcements"
                  description="Send departure notices to a dedicated channel"
                  checked={config.leave_enabled}
                  onChange={v => setConfig(c => ({ ...c, leave_enabled: v }))}
                />
              </div>

              {config.leave_enabled && (
                <div className="flex flex-col gap-4">
                  <div className="form-group">
                    <label className="form-label">Leave Announcement Channel</label>
                    <Select
                      value={config.leave_channel_id}
                      onChange={v => setConfig({ ...config, leave_channel_id: v })}
                      options={channels.map(ch => ({ value: ch.id, label: '# ' + ch.name }))}
                      placeholder="Select a leave channel..."
                      searchable
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Departure Message</label>
                    <textarea
                      className="input-field font-mono text-sm"
                      rows={3}
                      value={config.leave_message}
                      onChange={e => setConfig({ ...config, leave_message: e.target.value })}
                      placeholder="**{user}** left the server."
                    />
                  </div>

                  <div className="form-group mb-0">
                    <label className="form-label">Optional Image / Banner URL</label>
                    <input
                      type="text"
                      className="input-field"
                      value={config.leave_image_url}
                      onChange={e => setConfig({ ...config, leave_image_url: e.target.value })}
                      placeholder="https://example.com/goodbye.gif"
                    />
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Test Leave Card */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle icon={Send}>Test Departure Alert</CardTitle>
                <CardDescription>Dispatch a simulated leave message to the configured channel.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted mb-4">
                Sends a test leave alert containing your configured message and optional banner image directly to Discord.
              </p>
              <Button
                variant="secondary"
                icon={Send}
                loading={testingLeave}
                disabled={!config.leave_enabled || !config.leave_channel_id}
                onClick={() => handleTest('leave')}
              >
                Send Test Leave Notice
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Sticky Bottom Action Bar (Unsaved Changes) */}
      {isDirty && (
        <div className="unsaved-changes-banner animate-fade-in">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-warning animate-pulse" />
            <span className="text-sm font-medium text-main">
              You have unsaved changes in Welcome & Leave settings.
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleDiscard}>
              Discard
            </Button>
            <Button variant="primary" size="sm" icon={Save} loading={saving} onClick={handleSave}>
              Save Changes
            </Button>
          </div>
        </div>
      )}

      {/* Sync Servers Modal */}
      {syncOpen && (
        <SyncModal
          featureName="Welcome"
          config={config}
          onClose={() => setSyncOpen(false)}
        />
      )}
    </div>
  );
}

export default Welcome;
