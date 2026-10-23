import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { BarChart3, Plus, Trash2, CheckCircle2, AlertCircle, Users, Bot, UserCheck, Shield } from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Skeleton from '../../components/Skeleton';
import Badge from '../../components/Badge';
import { useToast } from '../../components/ToastContext';

export default function ServerStats() {
  const { guildId } = useParams();
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');
  const [statsData, setStatsData] = useState({ enabled: false, config: {} });

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/server-stats`);
      setStatsData(res.data);
      setError('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load server stats configuration');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSetup = async () => {
    setActing(true);
    setError('');
    try {
      await api.post(`/guilds/${guildId}/server-stats/setup`, {});
      toast('Server stats channels created successfully!', 'success');
      fetchData();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to setup stats channels';
      setError(msg);
      toast(msg, 'error');
    } finally {
      setActing(false);
    }
  };

  const handleRemove = async () => {
    if (!window.confirm('Are you sure you want to remove the server stats channels?')) return;
    setActing(true);
    setError('');
    try {
      await api.post(`/guilds/${guildId}/server-stats/remove`, {});
      toast('Server stats channels removed.', 'info');
      fetchData();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to remove stats channels';
      setError(msg);
      toast(msg, 'error');
    } finally {
      setActing(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <Skeleton height="80px" />
        <Skeleton height="300px" />
      </div>
    );
  }

  const { enabled, config } = statsData;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader
        icon={BarChart3}
        title="Server Stats Channels"
        subtitle="Display live server statistics (total members, humans, and bots) via locked voice channels that auto-update."
      />

      {error && (
        <div className="flex items-center justify-between p-4 rounded-xl bg-red-500/10 border border-red-500/25 text-red-400 text-sm">
          <div className="flex items-center gap-3">
            <AlertCircle size={18} className="shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError('')} className="text-red-400 hover:text-red-300">✕</button>
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 border border-indigo-500/20">
                <BarChart3 size={20} />
              </div>
              <div>
                <CardTitle>Voice Counter Status</CardTitle>
                <CardDescription>Automated 10-minute synchronized counters visible in your channel list.</CardDescription>
              </div>
            </div>
            <Badge variant={enabled ? 'success' : 'default'}>
              {enabled ? 'Active & Synchronizing' : 'Not Configured'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-400 shrink-0">
                <Users size={24} />
              </div>
              <div>
                <div className="text-xs text-[var(--text-muted)] font-medium">Channel 1</div>
                <div className="text-sm font-semibold text-[var(--text-main)]">👥 Total Members</div>
                <div className="text-xs text-[var(--text-muted)] mt-0.5">
                  {enabled && config?.total_channel_id ? `ID: ${config.total_channel_id}` : 'Inactive'}
                </div>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-400 shrink-0">
                <UserCheck size={24} />
              </div>
              <div>
                <div className="text-xs text-[var(--text-muted)] font-medium">Channel 2</div>
                <div className="text-sm font-semibold text-[var(--text-main)]">🧑 Humans</div>
                <div className="text-xs text-[var(--text-muted)] mt-0.5">
                  {enabled && config?.humans_channel_id ? `ID: ${config.humans_channel_id}` : 'Inactive'}
                </div>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-400 shrink-0">
                <Bot size={24} />
              </div>
              <div>
                <div className="text-xs text-[var(--text-muted)] font-medium">Channel 3</div>
                <div className="text-sm font-semibold text-[var(--text-main)]">🤖 Bots</div>
                <div className="text-xs text-[var(--text-muted)] mt-0.5">
                  {enabled && config?.bots_channel_id ? `ID: ${config.bots_channel_id}` : 'Inactive'}
                </div>
              </div>
            </div>
          </div>

          <div className="pt-2 flex items-center gap-4">
            {!enabled ? (
              <Button
                variant="primary"
                icon={Plus}
                loading={acting}
                onClick={handleSetup}
              >
                Create Stats Channels
              </Button>
            ) : (
              <Button
                variant="danger"
                icon={Trash2}
                loading={acting}
                onClick={handleRemove}
              >
                Remove Stats Channels
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
