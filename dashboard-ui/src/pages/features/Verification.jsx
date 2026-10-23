import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { BadgeCheck, CheckCircle2, AlertCircle, Send, ExternalLink, ShieldCheck } from 'lucide-react';
import api from '../../api';
import RoleSelect from '../../components/RoleSelect';
import ChannelSelect from '../../components/ChannelSelect';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Skeleton from '../../components/Skeleton';
import { useToast } from '../../components/ToastContext';

export default function Verification() {
  const { guildId } = useParams();
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [config, setConfig] = useState({ verified_role_id: '', log_channel_id: '', min_account_days: 0 });
  const [savedRole, setSavedRole] = useState('');

  const [panelChannel, setPanelChannel] = useState('');
  const [panelTitle, setPanelTitle] = useState('');
  const [panelDesc, setPanelDesc] = useState('');
  const [posting, setPosting] = useState(false);
  const [posted, setPosted] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/verification`);
      const cfg = res.data.config || {};
      setConfig(cfg);
      setSavedRole(cfg.verified_role_id || '');
      setError('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load verification settings');
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
      await api.post(`/guilds/${guildId}/verification`, config);
      setSavedRole(config.verified_role_id || '');
      toast('Verification rules saved!', 'success');
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to save verification settings';
      setError(msg);
      toast(msg, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handlePost = async () => {
    setError('');
    setPosted(null);
    if (!panelChannel) {
      setError('Please choose a channel to send the verification embed.');
      return;
    }
    setPosting(true);
    try {
      const res = await api.post(`/guilds/${guildId}/verification/panel`, {
        channel_id: panelChannel,
        title: panelTitle.trim(),
        description: panelDesc.trim(),
      });
      setPosted(res.data.message_url || true);
      toast('Verification panel published to Discord!', 'success');
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to post verification panel';
      setError(msg);
      toast(msg, 'error');
    } finally {
      setPosting(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <Skeleton height="80px" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton height="340px" />
          <Skeleton height="340px" />
        </div>
      </div>
    );
  }

  const unsavedRoleChange = (config.verified_role_id || '') !== savedRole;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader
        icon={BadgeCheck}
        title="Member Verification"
        subtitle="Gate server entry behind an interactive Discord button panel that grants member roles and blocks alt accounts."
        actions={
          <Button variant="primary" size="sm" icon={CheckCircle2} loading={saving} onClick={handleSave}>
            Save Rules
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
        {/* Verification Rules Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-400 border border-emerald-500/20">
                <ShieldCheck size={20} />
              </div>
              <div>
                <CardTitle>Verification Criteria</CardTitle>
                <CardDescription>Role awarded upon verification and account age checks.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Verified Member Role
              </label>
              <RoleSelect
                guildId={guildId}
                value={config.verified_role_id || ''}
                onChange={v => setConfig(prev => ({ ...prev, verified_role_id: v }))}
                placeholder="Select role to assign upon verification..."
              />
              <p className="text-xs text-[var(--text-muted)]">
                Role must be below the bot's highest role and cannot have Administrator.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Minimum Account Age (Days)
              </label>
              <input
                type="number"
                min="0"
                max="365"
                className="w-full bg-[var(--bg-surface)] border border-[var(--border)] rounded-xl px-4 py-2.5 text-sm text-[var(--text-main)] focus:outline-none focus:border-[var(--primary)] transition-colors"
                value={config.min_account_days}
                onChange={e => setConfig(prev => ({ ...prev, min_account_days: parseInt(e.target.value, 10) || 0 }))}
              />
              <p className="text-xs text-[var(--text-muted)]">
                Accounts created more recently than this will be rejected. 0 disables this check.
              </p>
            </div>

            <div className="space-y-1.5 pt-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Verification Audit Channel
              </label>
              <ChannelSelect
                guildId={guildId}
                value={config.log_channel_id || ''}
                onChange={v => setConfig(prev => ({ ...prev, log_channel_id: v }))}
                placeholder="Select a verification log channel..."
                allowedTypes={['text', 'news']}
              />
              <p className="text-xs text-[var(--text-muted)]">
                Records timestamps and user IDs for every verified member.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Panel Dispatcher Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 border border-indigo-500/20">
                <Send size={20} />
              </div>
              <div>
                <CardTitle>Deploy Verification Panel</CardTitle>
                <CardDescription>Post the interactive Discord message with the verification button.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            {(!savedRole || unsavedRoleChange) && (
              <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs leading-relaxed">
                {!savedRole
                  ? 'Please select and save a verified role first before deploying the panel.'
                  : 'You have unsaved role changes. Save rules first so the panel uses the new role.'}
              </div>
            )}

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Target Channel
              </label>
              <ChannelSelect
                guildId={guildId}
                value={panelChannel}
                onChange={setPanelChannel}
                placeholder="Choose channel for verification message..."
                allowedTypes={['text', 'news']}
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Embed Title
              </label>
              <input
                type="text"
                className="w-full bg-[var(--bg-surface)] border border-[var(--border)] rounded-xl px-4 py-2.5 text-sm text-[var(--text-main)] focus:outline-none focus:border-[var(--primary)] transition-colors"
                value={panelTitle}
                maxLength={100}
                placeholder="✅  Member Verification"
                onChange={e => setPanelTitle(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Embed Description
              </label>
              <textarea
                className="w-full bg-[var(--bg-surface)] border border-[var(--border)] rounded-xl px-4 py-2.5 text-sm text-[var(--text-main)] focus:outline-none focus:border-[var(--primary)] transition-colors resize-y"
                rows={3}
                maxLength={1500}
                value={panelDesc}
                placeholder="Welcome! Click the button below to verify and access channels."
                onChange={e => setPanelDesc(e.target.value)}
              />
            </div>

            <div className="flex items-center gap-4 pt-2 flex-wrap">
              <Button
                variant="primary"
                size="sm"
                icon={Send}
                loading={posting}
                onClick={handlePost}
                disabled={!savedRole || unsavedRoleChange}
              >
                Send Panel Message
              </Button>
              {posted && (
                <span className="inline-flex items-center gap-1.5 text-emerald-400 text-xs font-semibold">
                  <CheckCircle2 size={16} /> Dispatched!
                  {typeof posted === 'string' && (
                    <a
                      href={posted}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline ml-1"
                    >
                      Jump to Message <ExternalLink size={12} />
                    </a>
                  )}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
