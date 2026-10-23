import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { ShieldCheck, Link2, MessageSquareWarning, Siren, UserX, CheckCircle2, AlertCircle, Info, ShieldAlert } from 'lucide-react';
import api from '../../api';
import ChannelSelect from '../../components/ChannelSelect';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import Skeleton from '../../components/Skeleton';
import { useToast } from '../../components/ToastContext';

export default function Protection() {
  const { guildId } = useParams();
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [prot, setProt] = useState({ anti_link: false, anti_spam: false, anti_raid: false, log_channel_id: '' });
  const [hack, setHack] = useState({ enabled: true, log_channel_id: '' });

  const fetchData = useCallback(async () => {
    try {
      const [p, h] = await Promise.all([
        api.get(`/guilds/${guildId}/protection`),
        api.get(`/guilds/${guildId}/anti-hacked`),
      ]);
      setProt(p.data.config || {});
      setHack(h.data.config || {});
      setError('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load protection settings');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSave = async () => {
    setError('');
    setSaving(true);
    try {
      await Promise.all([
        api.post(`/guilds/${guildId}/protection`, prot),
        api.post(`/guilds/${guildId}/anti-hacked`, hack),
      ]);
      toast('Protection settings saved successfully!', 'success');
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to save protection settings';
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
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton height="320px" />
          <Skeleton height="320px" />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader
        icon={ShieldCheck}
        title="Protection Suite"
        subtitle="Anti-link, anti-spam, raid lockdown and hacked-account defence — real-time Discord protection."
        actions={
          <Button variant="primary" size="sm" icon={CheckCircle2} loading={saving} onClick={handleSave}>
            Save Changes
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Server Protection Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 border border-indigo-500/20">
                <ShieldCheck size={20} />
              </div>
              <div>
                <CardTitle>Content & Raid Filters</CardTitle>
                <CardDescription>Members with Manage Messages are exempt from filters.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="p-4 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] hover:border-[var(--border-hover)] transition-colors">
              <Toggle
                checked={!!prot.anti_link}
                onChange={v => setProt(prev => ({ ...prev, anti_link: v }))}
                label="Anti-Link Protection"
                description="Automatically deletes messages with invite links or suspicious URLs."
              />
            </div>

            <div className="p-4 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] hover:border-[var(--border-hover)] transition-colors">
              <Toggle
                checked={!!prot.anti_spam}
                onChange={v => setProt(prev => ({ ...prev, anti_spam: v }))}
                label="Anti-Spam Filter"
                description="Blocks rapid text spam (5 msgs / 3s) and image floods (3 images / 5s) with auto-timeouts."
              />
            </div>

            <div className="p-4 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] hover:border-[var(--border-hover)] transition-colors space-y-3">
              <Toggle
                checked={!!prot.anti_raid}
                onChange={v => setProt(prev => ({ ...prev, anti_raid: v }))}
                label="Anti-Raid Lockdown"
                description="Detects mass joins (10 members in 10s) and automatically strips Send Messages from @everyone."
              />
              {prot.anti_raid && (
                <div className="flex items-start gap-2.5 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs leading-relaxed">
                  <AlertCircle size={15} className="shrink-0 mt-0.5" />
                  <span>After a raid is triggered, restore permissions manually in Discord Server Settings → Roles.</span>
                </div>
              )}
            </div>

            <div className="space-y-1.5 pt-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Protection Alert Channel
              </label>
              <ChannelSelect
                guildId={guildId}
                value={prot.log_channel_id || ''}
                onChange={v => setProt(prev => ({ ...prev, log_channel_id: v }))}
                placeholder="Select an alert channel..."
                allowedTypes={['text', 'news']}
              />
              <p className="text-xs text-[var(--text-muted)]">
                Violations and actions taken will be dispatched to this channel.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Anti-Hacked Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-rose-500/10 flex items-center justify-center text-rose-400 border border-rose-500/20">
                <UserX size={20} />
              </div>
              <div>
                <CardTitle>Anti-Hacked Account Defense</CardTitle>
                <CardDescription>Stops compromised accounts from blasting scam images across channels.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="p-4 rounded-xl bg-[var(--bg-surface)] border border-[var(--border)] hover:border-[var(--border-hover)] transition-colors">
              <Toggle
                checked={!!hack.enabled}
                onChange={v => setHack(prev => ({ ...prev, enabled: v }))}
                label="Enable Anti-Hacked Watchdog"
                description="Detects simultaneous image and ping blasts across multiple channels within 20 seconds."
              />
            </div>

            <div className="flex items-start gap-3 p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs leading-relaxed">
              <Info size={18} className="shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold mb-1">Defense Thresholds:</div>
                Normal members cross-posting in <b>2 channels</b>, or staff members in <b>3 channels</b> within 20s are immediately isolated, spam deleted, high roles stripped, and given a 25-minute timeout.
              </div>
            </div>

            <div className="space-y-1.5 pt-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Incident Report Channel
              </label>
              <ChannelSelect
                guildId={guildId}
                value={hack.log_channel_id || ''}
                onChange={v => setHack(prev => ({ ...prev, log_channel_id: v }))}
                placeholder="Select an incident log channel..."
                allowedTypes={['text', 'news']}
              />
              <p className="text-xs text-[var(--text-muted)]">
                Detailed audit logs with revoked roles and deleted messages will post here.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
