import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../../api';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/Card';
import { Badge } from '../../components/Badge';
import { Button } from '../../components/Button';
import { Skeleton } from '../../components/Skeleton';
import {
  Server,
  Users,
  Hash,
  Shield,
  Activity,
  ArrowUpRight,
  UserPlus,
  Ticket,
  Tv,
  FileText,
  Gift,
  BarChart3,
  Sparkles,
  ScrollText,
  Cake,
  Trophy,
  ShieldAlert,
  Radio,
  Bot,
  Coins,
  Mic,
  RefreshCw,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';

export function Overview() {
  const { guildId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchOverview = async () => {
    try {
      setLoading(true);
      const res = await api.get(`/guilds/${guildId}/overview`);
      setData(res.data);
      setError('');
    } catch (err) {
      console.error('Failed to load overview', err);
      setError(err.response?.data?.error || 'Failed to load server overview.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, [guildId]);

  if (loading) {
    return (
      <div className="flex flex-col gap-6 animate-fade-in">
        <div className="card p-6">
          <div className="flex items-center gap-5">
            <Skeleton width="72px" height="72px" rounded="lg" />
            <div className="flex-1">
              <Skeleton width="220px" height="26px" style={{ marginBottom: '10px' }} />
              <Skeleton width="140px" height="16px" />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="card p-4">
              <Skeleton width="80px" height="14px" style={{ marginBottom: '8px' }} />
              <Skeleton width="50px" height="24px" />
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="card p-5">
              <Skeleton width="120px" height="18px" style={{ marginBottom: '8px' }} />
              <Skeleton width="100%" height="36px" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card p-8 text-center max-w-lg mx-auto">
        <div className="w-12 h-12 rounded-full bg-danger/10 text-danger flex items-center justify-center mx-auto mb-4">
          <AlertCircle size={24} />
        </div>
        <h3 className="text-lg font-semibold text-main mb-2">Failed to Load Server Overview</h3>
        <p className="text-sm text-muted mb-6">{error || 'Could not connect to the bot API.'}</p>
        <Button variant="primary" onClick={fetchOverview}>
          Try Again
        </Button>
      </div>
    );
  }

  const { guild, bot, features } = data;

  const featureCards = [
    { title: 'Welcome & Leave', icon: UserPlus, path: 'welcome', active: features.welcome, desc: 'Aesthetic welcome cards, member/bot auto-roles & departure alerts' },
    { title: 'Tickets System', icon: Ticket, path: 'tickets', active: features.tickets, count: features.tickets_count, desc: 'Multi-category ticket hubs, modal questions & transcripts' },
    { title: 'Stream Alerts', icon: Tv, path: 'stream-alerts', active: features.stream_alerts, count: features.stream_alerts_count, desc: 'Twitch, YouTube & Kick live announcement webhooks' },
    { title: 'Registration & Forms', icon: FileText, path: 'registration', active: features.registration, count: features.registration_count, desc: 'Interactive server applications, reviewer logs & role rewards' },
    { title: 'Giveaways', icon: Gift, path: 'giveaways', active: features.giveaways, count: features.active_giveaways_count, desc: 'Button-based giveaways with automatic winner picking' },
    { title: 'Polls System', icon: BarChart3, path: 'polls', active: features.polls, count: features.active_polls_count, desc: 'Community voting polls with live progress visualizers' },
    { title: 'Self Roles', icon: Sparkles, path: 'self-roles', active: features.self_roles, count: features.self_roles_count, desc: 'Interactive role selector menus and buttons' },
    { title: 'Server Audit Logs', icon: ScrollText, path: 'server-logs', active: true, desc: 'Granular channel routing for member, voice & moderation logs' },
    { title: 'Birthdays', icon: Cake, path: 'birthdays', active: features.birthdays, count: features.birthdays_count, desc: 'Automated celebratory birthday shoutouts & custom roles' },
    { title: 'Leaderboards & XP', icon: Trophy, path: 'leaderboard', active: true, desc: 'Voice activity minutes, message XP and economy rankings' },
    { title: 'Security & Anti-Nuke', icon: ShieldAlert, path: 'security', active: features.security, desc: 'Anti-spam defense, invite link protection & rate limiting' },
    { title: '24/7 Radio Station', icon: Radio, path: 'radio', active: features.radio, desc: 'Zero-lag uninterrupted background music and lofi radio' },
    { title: 'AI System Studio', icon: Bot, path: 'ai', active: features.ai, desc: 'Multi-persona autonomous chat, knowledge learning & lore' },
    { title: 'Economy & Shop', icon: Coins, path: 'economy', active: true, desc: 'Server currency, custom shop items & bank balances' },
    { title: 'Temporary Voice', icon: Mic, path: 'temp-vc', active: true, desc: 'Dynamic join-to-create disposable voice channels' },
    { title: 'Role Synchronization', icon: RefreshCw, path: 'role-sync', active: true, desc: 'Real-time cross-guild role mirrors and backfills' },
  ];

  const configuredCount = featureCards.filter(f => f.active).length;
  const progressPct = Math.round((configuredCount / featureCards.length) * 100);

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      {/* Hero Server Banner */}
      <div className="card p-6 bg-surface border-border">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          {/* Server Identity */}
          <div className="flex items-center gap-5 min-w-0">
            {guild.icon ? (
              <img
                src={guild.icon}
                alt={guild.name}
                className="w-16 h-16 rounded-xl object-cover border border-border shrink-0"
              />
            ) : (
              <div className="w-16 h-16 rounded-xl bg-hover border border-border flex items-center justify-center text-xl font-bold text-sub shrink-0">
                {guild.name.slice(0, 2).toUpperCase()}
              </div>
            )}

            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <h2 className="text-xl font-bold text-main truncate">{guild.name}</h2>
                <Badge variant="neutral" size="sm">ID: {guild.id}</Badge>
              </div>
              <p className="text-xs text-muted">
                Bot managed via {bot.name} • Connected to Discord Gateway
              </p>
            </div>
          </div>

          {/* Bot Status & Ping Pill */}
          <div className="flex items-center gap-4 shrink-0">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card border border-border text-xs">
              <span className="w-2 h-2 rounded-full bg-success inline-block shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
              <span className="text-sub font-medium">{bot.name} Online</span>
              <span className="text-muted border-l border-border pl-2 font-mono">
                {bot.latency_ms}ms
              </span>
            </div>
          </div>
        </div>

        {/* Real Statistics Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-border">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center text-muted">
              <Users size={18} />
            </div>
            <div>
              <div className="text-lg font-bold text-main">{guild.member_count.toLocaleString()}</div>
              <div className="text-xs text-muted">Members</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center text-muted">
              <Hash size={18} />
            </div>
            <div>
              <div className="text-lg font-bold text-main">{guild.channel_count}</div>
              <div className="text-xs text-muted">Channels</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center text-muted">
              <Shield size={18} />
            </div>
            <div>
              <div className="text-lg font-bold text-main">{guild.role_count}</div>
              <div className="text-xs text-muted">Server Roles</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center text-primary">
              <CheckCircle2 size={18} />
            </div>
            <div>
              <div className="text-lg font-bold text-main">
                {configuredCount} / {featureCards.length}
              </div>
              <div className="text-xs text-muted">Features Active ({progressPct}%)</div>
            </div>
          </div>
        </div>
      </div>

      {/* Feature Configuration Grid */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-main">Server Features</h3>
          <span className="text-xs text-muted">
            Select a module to manage its settings
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {featureCards.map((feat) => {
            const FeatIcon = feat.icon;
            return (
              <Link
                key={feat.path}
                to={`/dashboard/${guildId}/${feat.path}`}
                className="card card-hover p-4.5 flex flex-col justify-between group no-underline text-inherit"
              >
                <div>
                  <div className="flex items-start justify-between gap-3 mb-2.5">
                    <div className="w-9 h-9 rounded-lg bg-surface border border-border flex items-center justify-center text-muted group-hover:text-primary group-hover:border-primary/40 transition-colors">
                      <FeatIcon size={18} />
                    </div>

                    <div className="flex items-center gap-1.5">
                      {feat.count !== undefined && feat.count > 0 && (
                        <Badge variant="neutral" size="sm">
                          {feat.count}
                        </Badge>
                      )}
                      <Badge variant={feat.active ? 'success' : 'neutral'} size="sm" dot>
                        {feat.active ? 'Active' : 'Setup'}
                      </Badge>
                    </div>
                  </div>

                  <h4 className="text-sm font-semibold text-main mb-1 group-hover:text-primary transition-colors flex items-center justify-between">
                    <span>{feat.title}</span>
                    <ArrowUpRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity text-muted" />
                  </h4>
                  <p className="text-xs text-muted line-clamp-2 leading-relaxed">
                    {feat.desc}
                  </p>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default Overview;
