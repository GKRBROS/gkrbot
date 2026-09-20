import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Megaphone,
  Volume2,
  Mic,
  Send,
  Folder,
  Globe,
  Radio,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import Skeleton from '../../components/Skeleton';

export default function VoiceAnnounce() {
  const { guildId } = useParams();

  const [voiceChannels, setVoiceChannels] = useState([]);
  const [categories, setCategories] = useState([]);
  const [voices, setVoices] = useState([]);
  const [loading, setLoading] = useState(true);

  // Form
  const [targetType, setTargetType] = useState('channel'); // 'channel' | 'category'
  const [targetId, setTargetId] = useState('');
  const [message, setMessage] = useState('');
  const [language, setLanguage] = useState('en');
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fetchVoiceData = useCallback(async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/voice-announce`);
      setVoiceChannels(res.data.voice_channels || []);
      setCategories(res.data.categories || []);
      setVoices(res.data.voices || []);
      setError('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load voice channel data');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchVoiceData();
  }, [fetchVoiceData]);

  const handleSpeak = async (e) => {
    e.preventDefault();
    if (!targetId || !message.trim()) {
      setError('Please select a target voice channel or category and enter an announcement message.');
      return;
    }

    setSpeaking(true);
    setError('');
    setSuccess('');

    try {
      const res = await api.post(`/guilds/${guildId}/voice-announce`, {
        target_type: targetType,
        target_id: targetId,
        message: message.trim(),
        language,
      });

      if (targetType === 'category') {
        setSuccess(`Announced in ${res.data.announced_channels} active voice channel(s)!`);
      } else {
        setSuccess(`Broadcasted voice announcement in #${res.data.announced_channel || 'voice channel'}!`);
      }
      setMessage('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to broadcast voice announcement');
    } finally {
      setSpeaking(false);
    }
  };

  const channelOptions = voiceChannels.map(vc => ({
    value: vc.id,
    label: `🔊 ${vc.name} (${vc.members_count || 0} members)`
  }));

  const categoryOptions = categories.map(cat => ({
    value: cat.id,
    label: `📁 ${cat.name} (${cat.voice_count || 0} voice channels)`
  }));

  const voiceOptions = voices.length > 0 ? voices.map(v => ({
    value: v.id || v.code,
    label: `${v.name} (${v.lang || v.id})`
  })) : [
    { value: 'en', label: 'English (US - Jenny Neural)' },
    { value: 'en-GB', label: 'English (UK - Sonia Neural)' },
    { value: 'ms', label: 'Malay (Malaysia - Osman Neural)' },
    { value: 'zh', label: 'Chinese (Mandarin - Xiaoxiao Neural)' },
    { value: 'ja', label: 'Japanese (Nanami Neural)' },
  ];

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="320px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Megaphone}
        title="Voice Channel Announcer"
        subtitle="Broadcast natural neural text-to-speech spoken announcements directly into active voice channels or whole voice categories."
      />

      {error && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.25)',
          color: '#f87171',
          fontSize: '13.5px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertCircle size={17} />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError('')}
            style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '16px' }}
          >
            ✕
          </button>
        </div>
      )}

      {success && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(16, 185, 129, 0.1)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          color: '#34d399',
          fontSize: '13.5px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <CheckCircle2 size={17} />
            <span>{success}</span>
          </div>
          <button
            onClick={() => setSuccess('')}
            style={{ background: 'transparent', border: 'none', color: '#34d399', cursor: 'pointer', fontSize: '16px' }}
          >
            ✕
          </button>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))', gap: '24px' }}>
        {/* Left: Announcement Dispatcher */}
        <Card>
          <CardHeader>
            <CardTitle>Broadcast Voice Message</CardTitle>
            <CardDescription>
              The bot connects instantly, speaks the announcement in crystal-clear audio, and gracefully disconnects.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSpeak} style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '8px' }}>
                  Target Scope
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <button
                    type="button"
                    onClick={() => { setTargetType('channel'); setTargetId(''); }}
                    style={{
                      padding: '12px',
                      borderRadius: 'var(--radius-md)',
                      border: targetType === 'channel' ? '1.5px solid var(--primary)' : '1px solid var(--border)',
                      background: targetType === 'channel' ? 'rgba(88, 101, 242, 0.1)' : 'var(--bg-surface)',
                      color: targetType === 'channel' ? 'var(--text-main)' : 'var(--text-muted)',
                      fontWeight: 600,
                      fontSize: '13.5px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                      cursor: 'pointer'
                    }}
                  >
                    <Volume2 size={16} /> Single Channel
                  </button>

                  <button
                    type="button"
                    onClick={() => { setTargetType('category'); setTargetId(''); }}
                    style={{
                      padding: '12px',
                      borderRadius: 'var(--radius-md)',
                      border: targetType === 'category' ? '1.5px solid var(--primary)' : '1px solid var(--border)',
                      background: targetType === 'category' ? 'rgba(88, 101, 242, 0.1)' : 'var(--bg-surface)',
                      color: targetType === 'category' ? 'var(--text-main)' : 'var(--text-muted)',
                      fontWeight: 600,
                      fontSize: '13.5px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                      cursor: 'pointer'
                    }}
                  >
                    <Folder size={16} /> Whole Category
                  </button>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  {targetType === 'channel' ? 'Target Voice Channel' : 'Target Voice Category'}
                </label>
                <Select
                  value={targetId}
                  onChange={setTargetId}
                  options={targetType === 'channel' ? channelOptions : categoryOptions}
                  placeholder={targetType === 'channel' ? 'Select voice channel...' : 'Select voice category...'}
                  searchable
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Neural Voice Accent
                </label>
                <Select
                  value={language}
                  onChange={setLanguage}
                  options={voiceOptions}
                  placeholder="Select voice language..."
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Announcement Speech Text
                </label>
                <textarea
                  className="form-input"
                  rows={4}
                  value={message}
                  onChange={e => setMessage(e.target.value)}
                  placeholder="e.g. Attention server members: Community game night starts in 10 minutes in General Voice!"
                  required
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
                <Button
                  type="submit"
                  variant="primary"
                  icon={Send}
                  loading={speaking}
                  disabled={!targetId || !message.trim()}
                >
                  Broadcast to Voice
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Right: Active Voice Channels Overview */}
        <div>
          <Card>
            <CardHeader>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <CardTitle>Voice Channels Activity</CardTitle>
                <Badge variant="primary" size="sm">{voiceChannels.length} Channels</Badge>
              </div>
              <CardDescription>Live voice rooms detected in this server.</CardDescription>
            </CardHeader>
            <CardContent>
              {voiceChannels.length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                  No voice channels found on this server.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {voiceChannels.map(vc => (
                    <div
                      key={vc.id}
                      style={{
                        padding: '10px 14px',
                        borderRadius: 'var(--radius-sm)',
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Volume2 size={16} color="var(--primary)" />
                        <span style={{ fontWeight: 500, fontSize: '13.5px', color: 'var(--text-main)' }}>
                          {vc.name}
                        </span>
                      </div>
                      <Badge variant={vc.members_count > 0 ? 'success' : 'neutral'} size="sm">
                        {vc.members_count || 0} listening
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
