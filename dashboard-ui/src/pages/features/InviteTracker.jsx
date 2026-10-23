import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Users, CheckCircle2, AlertCircle, Trophy, UserPlus, UserMinus, ShieldAlert } from 'lucide-react';
import api from '../../api';
import ChannelSelect from '../../components/ChannelSelect';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Skeleton from '../../components/Skeleton';
import EmptyState from '../../components/EmptyState';
import { useToast } from '../../components/ToastContext';

export default function InviteTracker() {
  const { guildId } = useParams();
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [channelId, setChannelId] = useState('');
  const [leaderboard, setLeaderboard] = useState([]);

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/invites`);
      setChannelId(res.data.channel_id || '');
      setLeaderboard(res.data.leaderboard || []);
      setError('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load invite tracker data');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      await api.post(`/guilds/${guildId}/invites`, { channel_id: channelId });
      toast('Invite tracker channel saved!', 'success');
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to save invite tracker settings';
      setError(msg);
      toast(msg, 'error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <Skeleton height="80px" />
        <Skeleton height="200px" />
        <Skeleton height="350px" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader
        icon={Users}
        title="Invite Tracker & Analytics"
        subtitle="Track member invite links, identify who invited new joins, detect fake accounts, and view top inviters."
        actions={
          <Button variant="primary" size="sm" icon={CheckCircle2} loading={saving} onClick={handleSave}>
            Save Channel
          </Button>
        }
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

      {/* Configuration Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 border border-indigo-500/20">
              <UserPlus size={20} />
            </div>
            <div>
              <CardTitle>Invite Notifications Channel</CardTitle>
              <CardDescription>Discord channel where rich join/leave invite cards will be published.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="max-w-xl space-y-2">
            <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
              Log Channel
            </label>
            <ChannelSelect
              guildId={guildId}
              value={channelId}
              onChange={setChannelId}
              placeholder="Select a channel for invite alerts (leave empty to disable)..."
              allowedTypes={['text', 'news']}
            />
            <p className="text-xs text-[var(--text-muted)]">
              When a user joins, an embed with the inviter, code used, account age, and fake detection will post here.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Leaderboard Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-400 border border-amber-500/20">
              <Trophy size={20} />
            </div>
            <div>
              <CardTitle>Top Inviters Leaderboard</CardTitle>
              <CardDescription>Server members ranked by net successful invitations.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {leaderboard.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No Invites Recorded Yet"
              description="Invite data will accumulate here as members invite friends with server links."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--text-muted)]">
                    <th className="py-3 px-4">#</th>
                    <th className="py-3 px-4">Member</th>
                    <th className="py-3 px-4 text-emerald-400">Joins</th>
                    <th className="py-3 px-4 text-rose-400">Leaves</th>
                    <th className="py-3 px-4 text-amber-400">Fakes</th>
                    <th className="py-3 px-4 text-right font-bold text-[var(--primary)]">Net Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {leaderboard.map((item, idx) => (
                    <tr key={item.inviter_id} className="hover:bg-[var(--bg-surface-hover)] transition-colors">
                      <td className="py-3 px-4 font-mono text-xs text-[var(--text-muted)]">
                        {idx + 1}
                      </td>
                      <td className="py-3 px-4 font-medium text-[var(--text-main)]">
                        {item.username}
                      </td>
                      <td className="py-3 px-4 font-mono text-emerald-400">+{item.joins}</td>
                      <td className="py-3 px-4 font-mono text-rose-400">-{item.leaves}</td>
                      <td className="py-3 px-4 font-mono text-amber-400">{item.fakes}</td>
                      <td className="py-3 px-4 text-right font-mono font-bold text-[var(--primary)]">
                        {item.net}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
