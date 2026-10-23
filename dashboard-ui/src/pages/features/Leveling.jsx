import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import {
  Trophy,
  Sliders,
  Image as ImageIcon,
  Layers,
  Ban,
  Plus,
  Trash2,
  Sparkles,
  Shield,
  CheckCircle2,
  AlertCircle,
  Save,
  Megaphone
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import { ChannelSelect } from '../../components/ChannelSelect';
import { RoleSelect } from '../../components/RoleSelect';
import { useToast } from '../../components/ToastContext';

export function Leveling() {
  const { guildId } = useParams();
  const toast = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);

  // Config state
  const [config, setConfig] = useState({
    enabled: 1,
    xp_multiplier: 1.0,
    card_background_url: '',
    stack_rewards: 1,
    announce_channel_id: '',
    announce_message: 'Congratulations {user}, you leveled up to **Level {level}**!',
    channel_blacklist: []
  });

  // Level rewards state
  const [rewards, setRewards] = useState([]);
  const [newLevel, setNewLevel] = useState('');
  const [newRoleId, setNewRoleId] = useState('');
  const [addingReward, setAddingReward] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [levelRes, channelsRes, rolesRes] = await Promise.all([
        api.get(`/guilds/${guildId}/leveling`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/roles`),
      ]);

      if (levelRes.data?.config) {
        setConfig({
          ...levelRes.data.config,
          announce_channel_id: levelRes.data.config.announce_channel_id || '',
          channel_blacklist: levelRes.data.config.channel_blacklist || []
        });
      }
      setRewards(levelRes.data?.rewards || []);
      setChannels(channelsRes.data?.channels || []);
      setRoles(rolesRes.data?.roles || []);
    } catch (err) {
      console.error('Failed to load leveling system data', err);
      if (toast) toast('Failed to load leveling config', 'error');
    } finally {
      setLoading(false);
    }
  }, [guildId, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      await api.post(`/guilds/${guildId}/leveling`, config);
      if (toast) toast('Leveling settings saved and cached successfully!', 'success');
    } catch (err) {
      if (toast) toast(err.response?.data?.error || 'Failed to save leveling settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleAddReward = async (e) => {
    e.preventDefault();
    const lvl = parseInt(newLevel, 10);
    if (!lvl || lvl <= 0 || !newRoleId) {
      if (toast) toast('Please provide a valid level and select a role', 'error');
      return;
    }

    setAddingReward(true);
    try {
      await api.post(`/guilds/${guildId}/leveling/rewards`, { level: lvl, role_id: newRoleId });
      setRewards(prev => [...prev.filter(r => r.level !== lvl), { level: lvl, role_id: newRoleId }].sort((a, b) => a.level - b.level));
      setNewLevel('');
      setNewRoleId('');
      if (toast) toast(`Role reward added for Level ${lvl}!`, 'success');
    } catch (err) {
      if (toast) toast(err.response?.data?.error || 'Failed to add role reward', 'error');
    } finally {
      setAddingReward(false);
    }
  };

  const handleDeleteReward = async (level) => {
    try {
      await api.delete(`/guilds/${guildId}/leveling/rewards/${level}`);
      setRewards(prev => prev.filter(r => r.level !== level));
      if (toast) toast(`Removed Level ${level} role reward`, 'success');
    } catch (err) {
      if (toast) toast('Failed to delete reward', 'error');
    }
  };

  const toggleBlacklistChannel = (channelId) => {
    const strId = String(channelId);
    setConfig(prev => {
      const list = prev.channel_blacklist || [];
      const next = list.includes(strId)
        ? list.filter(id => id !== strId)
        : [...list, strId];
      return { ...prev, channel_blacklist: next };
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leveling & XP System"
        description="Configure text and voice activity progression, multipliers, role rewards, and rank card themes."
        icon={Trophy}
        badge="Engagement Engine"
        actions={
          <Button variant="primary" icon={Save} onClick={handleSaveConfig} loading={saving}>
            Save Changes
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Card 1: Core System & Multipliers */}
        <Card>
          <CardHeader>
            <CardTitle icon={Sliders}>XP Multiplier & Progression</CardTitle>
            <CardDescription>Adjust XP accumulation rate across chat messages.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Toggle
              checked={Boolean(config.enabled)}
              onChange={val => setConfig({ ...config, enabled: val ? 1 : 0 })}
              label="Enable Leveling System"
              description="Members earn XP from sending messages in eligible channels"
            />

            <div className="pt-4 border-t border-border space-y-2">
              <div className="flex items-center justify-between">
                <label className="form-label mb-0!">XP Rate Multiplier</label>
                <span className="text-sm font-bold text-primary px-2 py-0.5 rounded bg-primary/10 border border-primary/20">
                  {config.xp_multiplier}x XP
                </span>
              </div>
              <input
                type="range"
                min="0.5"
                max="5.0"
                step="0.1"
                value={config.xp_multiplier}
                onChange={e => setConfig({ ...config, xp_multiplier: parseFloat(e.target.value) || 1.0 })}
                className="w-full accent-primary cursor-pointer"
              />
              <div className="flex justify-between text-[11px] text-muted">
                <span>0.5x (Slow)</span>
                <span>1.0x (Standard)</span>
                <span>2.5x (Boosted)</span>
                <span>5.0x (Hyper)</span>
              </div>
            </div>

            <div className="pt-4 border-t border-border">
              <Toggle
                checked={Boolean(config.stack_rewards)}
                onChange={val => setConfig({ ...config, stack_rewards: val ? 1 : 0 })}
                label="Stackable Role Rewards"
                description="Keep lower-level reward roles when higher ranks are unlocked"
              />
            </div>
          </CardContent>
        </Card>

        {/* Card 2: Rank Card Theme & Level Up Announcements */}
        <Card>
          <CardHeader>
            <CardTitle icon={ImageIcon}>Rank Card & Level Announcements</CardTitle>
            <CardDescription>Customize the background image and destination for alerts.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="form-group">
              <label className="form-label">Rank Card Background Image URL</label>
              <input
                type="text"
                className="form-input"
                placeholder="https://example.com/banner.png"
                value={config.card_background_url || ''}
                onChange={e => setConfig({ ...config, card_background_url: e.target.value })}
              />
            </div>

            {config.card_background_url && (
              <div className="relative rounded-lg overflow-hidden border border-border h-28 bg-surface-card flex items-center justify-center">
                <img
                  src={config.card_background_url}
                  alt="Rank Banner Preview"
                  className="w-full h-full object-cover"
                  onError={e => { e.target.style.display = 'none'; }}
                />
                <div className="absolute inset-0 bg-black/40 flex items-center justify-center text-xs font-semibold text-white">
                  Rank Card Banner Preview
                </div>
              </div>
            )}

            <div className="form-group">
              <label className="form-label">Level Up Alert Channel</label>
              <ChannelSelect
                value={config.announce_channel_id}
                onChange={chId => setConfig({ ...config, announce_channel_id: chId })}
                channels={channels}
                allowedTypes={['text', 'news']}
                placeholder="Select announcement channel (or post in current channel)"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Custom Level Up Message</label>
              <input
                type="text"
                className="form-input"
                placeholder="Congratulations {user}, you reached Level {level}!"
                value={config.announce_message || ''}
                onChange={e => setConfig({ ...config, announce_message: e.target.value })}
              />
              <span className="text-[11px] text-muted">Placeholders: <code>{'{user}'}</code>, <code>{'{level}'}</code></span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Card 3: Role Rewards Management */}
      <Card>
        <CardHeader>
          <CardTitle icon={Shield}>Level Milestone Role Rewards</CardTitle>
          <CardDescription>Assign Discord roles automatically when members hit specific level milestones.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <form onSubmit={handleAddReward} className="flex flex-wrap items-end gap-3 p-4 bg-surface-hover/20 rounded-lg border border-border">
            <div className="w-32">
              <label className="form-label text-xs">Target Level</label>
              <input
                type="number"
                min="1"
                max="999"
                className="form-input"
                placeholder="e.g. 5"
                value={newLevel}
                onChange={e => setNewLevel(e.target.value)}
              />
            </div>

            <div className="flex-1 min-w-[260px]">
              <label className="form-label text-xs">Reward Role</label>
              <RoleSelect
                value={newRoleId}
                onChange={setNewRoleId}
                roles={roles}
                manageableOnly={true}
                placeholder="Select role to grant..."
              />
            </div>

            <Button type="submit" variant="primary" icon={Plus} loading={addingReward}>
              Add Milestone Reward
            </Button>
          </form>

          {rewards.length === 0 ? (
            <div className="py-6 text-center text-muted text-sm border border-dashed border-border rounded-lg">
              No milestone rewards configured yet. Add one above!
            </div>
          ) : (
            <div className="overflow-x-auto border border-border rounded-lg">
              <table className="w-full text-left text-sm">
                <thead className="bg-surface-card text-muted text-xs uppercase border-b border-border">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Level</th>
                    <th className="px-4 py-3 font-semibold">Assigned Role</th>
                    <th className="px-4 py-3 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rewards.map(r => {
                    const matchedRole = roles.find(rl => String(rl.id) === String(r.role_id));
                    return (
                      <tr key={r.level} className="hover:bg-surface-hover/30 transition">
                        <td className="px-4 py-3 font-bold text-primary">
                          Level {r.level}
                        </td>
                        <td className="px-4 py-3">
                          {matchedRole ? (
                            <div className="flex items-center gap-2">
                              <span
                                className="w-2.5 h-2.5 rounded-full"
                                style={{ backgroundColor: matchedRole.color || '#99aab5' }}
                              />
                              <span className="font-medium text-main">{matchedRole.name}</span>
                            </div>
                          ) : (
                            <span className="text-muted text-xs">Unknown Role ({r.role_id})</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => handleDeleteReward(r.level)}
                            className="btn btn-ghost btn-sm text-danger hover:bg-danger/10"
                            title="Delete reward"
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Card 4: Channel Blacklist Grid */}
      <Card>
        <CardHeader>
          <CardTitle icon={Ban}>XP Channel Blacklist Grid</CardTitle>
          <CardDescription>Messages sent in checked channels will not award XP.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 max-h-72 overflow-y-auto p-1">
            {channels
              .filter(c => c.type === 'text' || c.type === 'news')
              .map(ch => {
                const isBlacklisted = (config.channel_blacklist || []).includes(String(ch.id));
                return (
                  <button
                    key={ch.id}
                    type="button"
                    onClick={() => toggleBlacklistChannel(ch.id)}
                    className={`flex items-center justify-between p-2.5 rounded-lg border text-left transition ${
                      isBlacklisted
                        ? 'border-danger/40 bg-danger/10 text-danger'
                        : 'border-border bg-surface-card hover:bg-surface-hover text-main'
                    }`}
                  >
                    <span className="text-xs font-medium truncate">#{ch.name}</span>
                    {isBlacklisted && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-danger/20">BLOCKED</span>}
                  </button>
                );
              })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default Leveling;
