import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Server,
  Layers,
  Check,
  ArrowRight,
  Shield,
  MessageSquare,
  Sparkles,
  Ticket,
  Tv,
  Scale
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';

const MODULE_OPTIONS = [
  { id: 'welcome', label: 'Welcome & Leave Setup', desc: 'Welcome/leave messages, banners, embed cards & auto-roles', icon: Sparkles },
  { id: 'security', label: 'Security & Anti-Spam', desc: 'Message velocity limits, time windows, mass mention caps & image scanning', icon: Shield },
  { id: 'sticky', label: 'Sticky Messages', desc: 'Persistent channel sticky banners (matches target channel names)', icon: MessageSquare },
  { id: 'autoreact', label: 'Auto Reactions', desc: 'Keyword emoji triggers and reactions (matches channel names)', icon: Sparkles },
  { id: 'tickets', label: 'Tickets System', desc: 'Ticket categories, modal questions & transcripts log routing', icon: Ticket },
  { id: 'streamalerts', label: 'Stream Alerts', desc: 'YouTube / Twitch / Kick notifications and target alert channels', icon: Tv },
  { id: 'moderation', label: 'Staff Roles & Moderation', desc: 'Staff roles, mute durations & mod logs (matched by role names)', icon: Scale },
];

function ServerSync() {
  const { guildId } = useParams();
  const [guilds, setGuilds] = useState([]);
  const [currentGuild, setCurrentGuild] = useState(null);
  const [selectedModules, setSelectedModules] = useState(['welcome', 'security', 'sticky', 'autoreact']);
  const [selectedGuilds, setSelectedGuilds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    const loadGuilds = async () => {
      try {
        const res = await api.get('/users/@me');
        const allGuilds = res.data.guilds || [];
        const current = allGuilds.find(g => g.id === guildId);
        setCurrentGuild(current);
        const others = allGuilds.filter(g => g.id !== guildId);
        setGuilds(others);
      } catch (err) {
        console.error('Failed to load servers for sync:', err);
      }
      setLoading(false);
    };
    loadGuilds();
  }, [guildId]);

  const toggleModule = (id) => {
    setSelectedModules(prev =>
      prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id]
    );
  };

  const toggleGuild = (id) => {
    setSelectedGuilds(prev =>
      prev.includes(id) ? prev.filter(gId => gId !== id) : [...prev, id]
    );
  };

  const handleSelectAllGuilds = () => {
    if (selectedGuilds.length === guilds.length) {
      setSelectedGuilds([]);
    } else {
      setSelectedGuilds(guilds.map(g => g.id));
    }
  };

  const handleSelectAllModules = () => {
    if (selectedModules.length === MODULE_OPTIONS.length) {
      setSelectedModules([]);
    } else {
      setSelectedModules(MODULE_OPTIONS.map(m => m.id));
    }
  };

  const handleExecuteSync = async () => {
    if (selectedGuilds.length === 0 || selectedModules.length === 0) return;
    setSyncing(true);
    setResult(null);
    try {
      const res = await api.post(`/guilds/${guildId}/sync`, {
        target_guild_ids: selectedGuilds,
        modules: selectedModules
      });
      setResult({
        type: 'success',
        text: `Successfully synced ${selectedModules.length} module(s) across ${res.data.synced_servers} target server(s)!`
      });
    } catch (err) {
      setResult({
        type: 'error',
        text: err.response?.data?.error || 'Failed to sync settings. Please try again.'
      });
    }
    setSyncing(false);
  };

  if (loading) {
    return (
      <div className="flex flex-col gap-6 animate-fade-in">
        <div className="skeleton" style={{ height: '72px' }} />
        <div className="skeleton" style={{ height: '100px' }} />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="skeleton" style={{ height: '360px' }} />
          <div className="skeleton" style={{ height: '360px' }} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <PageHeader
        icon={RefreshCw}
        title="Multi-Server Settings Sync"
        subtitle="Replicate and clone bot configurations across multiple Discord servers in a single click."
      />

      {result && (
        <div
          className={`p-4 rounded-xl border flex items-center gap-3 text-sm font-medium ${
            result.type === 'success'
              ? 'bg-success/10 border-success/30 text-success'
              : 'bg-danger/10 border-danger/30 text-danger'
          }`}
        >
          {result.type === 'success' ? (
            <CheckCircle2 size={18} className="shrink-0" />
          ) : (
            <AlertCircle size={18} className="shrink-0" />
          )}
          <span>{result.text}</span>
        </div>
      )}

      {/* Source Server Banner */}
      <Card className="p-5 bg-gradient-to-r from-primary/10 via-card to-card border-primary/20">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            {currentGuild?.icon ? (
              <img
                src={currentGuild.icon}
                alt=""
                className="w-14 h-14 rounded-2xl object-cover shadow-sm ring-2 ring-primary/30"
              />
            ) : (
              <div className="w-14 h-14 rounded-2xl bg-primary text-white font-bold flex items-center justify-center text-xl shadow-sm ring-2 ring-primary/30">
                {currentGuild?.name?.charAt(0) || 'G'}
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <Badge variant="primary" size="sm">SOURCE SERVER (MASTER)</Badge>
              </div>
              <h3 className="text-lg font-bold text-main mt-1">
                {currentGuild?.name}
              </h3>
            </div>
          </div>
          <p className="text-xs text-muted max-w-xs">
            Configurations from this server will be safely cloned and applied to selected target guilds.
          </p>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Step 1: Select Modules */}
        <Card className="p-6 flex flex-col">
          <CardHeader className="p-0 pb-4 mb-3 border-b border-border flex flex-row items-center justify-between">
            <CardTitle icon={Layers}>
              <span>1. Choose Modules to Clone</span>
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSelectAllModules}
              className="text-xs text-primary hover:text-primary-hover"
            >
              {selectedModules.length === MODULE_OPTIONS.length ? 'Deselect All' : 'Select All'}
            </Button>
          </CardHeader>

          <div className="flex flex-col gap-2.5 flex-1 overflow-y-auto max-h-[460px] pr-1">
            {MODULE_OPTIONS.map((mod) => {
              const isChecked = selectedModules.includes(mod.id);
              const Icon = mod.icon;
              return (
                <div
                  key={mod.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleModule(mod.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') toggleModule(mod.id);
                  }}
                  className={`p-3.5 rounded-xl border flex items-start justify-between gap-3 cursor-pointer transition-all duration-150 ${
                    isChecked
                      ? 'bg-primary/10 border-primary/50 shadow-sm shadow-primary/5'
                      : 'bg-card-sub/50 hover:bg-card-sub border-border hover:border-border-hover'
                  }`}
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div className={`p-2 rounded-lg mt-0.5 shrink-0 ${isChecked ? 'bg-primary text-white' : 'bg-border text-muted'}`}>
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-main">
                        {mod.label}
                      </div>
                      <div className="text-xs text-muted mt-0.5 leading-relaxed">
                        {mod.desc}
                      </div>
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {}}
                    className="w-4 h-4 mt-1 accent-primary cursor-pointer shrink-0"
                  />
                </div>
              );
            })}
          </div>
        </Card>

        {/* Step 2: Select Target Servers */}
        <Card className="p-6 flex flex-col">
          <CardHeader className="p-0 pb-4 mb-3 border-b border-border flex flex-row items-center justify-between">
            <CardTitle icon={Server}>
              <span>2. Select Target Servers ({selectedGuilds.length})</span>
            </CardTitle>
            {guilds.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSelectAllGuilds}
                className="text-xs text-primary hover:text-primary-hover"
              >
                {selectedGuilds.length === guilds.length ? 'Deselect All' : 'Select All'}
              </Button>
            )}
          </CardHeader>

          {guilds.length === 0 ? (
            <div className="py-16 text-center text-muted text-sm flex flex-col items-center justify-center flex-1">
              <Server size={36} className="mb-2 opacity-40" />
              <p>No other servers found where you have Administrator permissions and the bot is invited.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5 flex-1 overflow-y-auto max-h-[460px] pr-1">
              {guilds.map((guild) => {
                const isChecked = selectedGuilds.includes(guild.id);
                return (
                  <div
                    key={guild.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => toggleGuild(guild.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') toggleGuild(guild.id);
                    }}
                    className={`p-3 rounded-xl border flex items-center justify-between gap-3 cursor-pointer transition-all duration-150 ${
                      isChecked
                        ? 'bg-primary/10 border-primary/50 shadow-sm shadow-primary/5'
                        : 'bg-card-sub/50 hover:bg-card-sub border-border hover:border-border-hover'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {guild.icon ? (
                        <img
                          src={guild.icon}
                          alt=""
                          className="w-10 h-10 rounded-xl object-cover shrink-0"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-xl bg-primary/20 text-primary font-bold flex items-center justify-center shrink-0">
                          {guild.name.charAt(0)}
                        </div>
                      )}
                      <span className="text-sm font-semibold text-main truncate">
                        {guild.name}
                      </span>
                    </div>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => {}}
                      className="w-4 h-4 accent-primary cursor-pointer shrink-0"
                    />
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {/* Action Footer Bar */}
      <Card className="p-5 bg-card flex flex-col sm:flex-row items-center justify-between gap-4 border-border">
        <div>
          <div className="text-sm font-semibold text-main">
            Ready to Synchronize?
          </div>
          <div className="text-xs text-muted mt-0.5">
            This will replicate {selectedModules.length} module(s) to {selectedGuilds.length} target server(s) using master settings from {currentGuild?.name}.
          </div>
        </div>

        <Button
          variant="primary"
          size="lg"
          onClick={handleExecuteSync}
          disabled={syncing || selectedGuilds.length === 0 || selectedModules.length === 0}
          className="w-full sm:w-auto font-bold shadow-md shadow-primary/20"
        >
          {syncing ? (
            <>
              <RefreshCw size={18} className="animate-spin" />
              <span>Synchronizing Servers...</span>
            </>
          ) : (
            <>
              <RefreshCw size={18} />
              <span>Clone & Sync to {selectedGuilds.length} Server(s)</span>
            </>
          )}
        </Button>
      </Card>
    </div>
  );
}

export default ServerSync;
