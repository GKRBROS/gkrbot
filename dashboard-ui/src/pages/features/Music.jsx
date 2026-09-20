import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Music2,
  SkipBack,
  SkipForward,
  Play,
  Pause,
  Square,
  Repeat,
  Volume2,
  Clock,
  ListMusic
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function Music() {
  const { guildId } = useParams();
  const [playerInfo, setPlayerInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchMusic = async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/music`);
      setPlayerInfo(res.data);
      setError('');
    } catch (err) {
      if (err.response?.status === 404) {
        setPlayerInfo(null);
      } else {
        setError('Failed to load music player state.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMusic();
    const interval = setInterval(fetchMusic, 3000);
    return () => clearInterval(interval);
  }, [guildId]);

  const controlAction = async (action) => {
    try {
      await api.post(`/guilds/${guildId}/music/control`, { action });
      fetchMusic();
    } catch (err) {
      alert(err.response?.data?.error || 'Action failed');
    }
  };

  const formatTime = (ms) => {
    if (!ms) return '0:00';
    const totalSeconds = Math.floor(ms / 1000);
    const m = Math.floor(totalSeconds / 60);
    const s = Math.floor(totalSeconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <Skeleton height="400px" />
          <Skeleton height="400px" />
        </div>
      </div>
    );
  }

  if (!playerInfo || !playerInfo.is_playing) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <PageHeader
          icon={Music2}
          title="Music Player"
          subtitle="Control the bot's live audio playback directly from the dashboard in real-time."
        />
        <EmptyState
          icon={Music2}
          title="Nothing Playing Right Now"
          description="Join a voice channel and use the /play command to start the music session. The player will appear here."
        />
      </div>
    );
  }

  const { current, queue, volume, paused, loop_mode } = playerInfo;
  const progressPercent = current.length > 0 ? (current.position / current.length) * 100 : 0;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Music2}
        title="Music Player"
        subtitle="Live playback controller — polls every 3 seconds for real-time state."
      />

      {error && (
        <div style={{ padding: '12px 16px', borderRadius: 'var(--radius-md)', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.25)', color: '#f87171', fontSize: '13.5px' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))', gap: '24px' }}>
        {/* Now Playing */}
        <Card>
          <CardContent style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Thumbnail */}
            <div style={{
              width: '100%',
              aspectRatio: '16/9',
              borderRadius: 'var(--radius-md)',
              backgroundImage: `url(${current.thumbnail || ''})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              background: current.thumbnail ? undefined : 'var(--bg-surface)',
              border: '1px solid var(--border)',
              position: 'relative',
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              {!current.thumbnail && <Music2 size={48} color="var(--text-muted)" />}
              {paused && (
                <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Pause size={48} color="white" />
                </div>
              )}
            </div>

            {/* Track info */}
            <div>
              <h3 style={{ margin: '0 0 4px', fontSize: '17px', fontWeight: 700, color: 'var(--text-main)', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                {current.title}
              </h3>
              <p style={{ margin: 0, fontSize: '13.5px', color: 'var(--text-muted)' }}>{current.author}</p>
            </div>

            {/* Progress bar */}
            <div>
              <div style={{ height: '4px', borderRadius: '2px', background: 'var(--bg-surface)', border: '1px solid var(--border)', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${progressPercent}%`, background: 'var(--primary)', transition: 'width 1s linear', borderRadius: '2px' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Clock size={11} />{formatTime(current.position)}</span>
                <span>{formatTime(current.length)}</span>
              </div>
            </div>

            {/* Controls */}
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '12px' }}>
              <Button variant="ghost" size="sm" icon={SkipBack} onClick={() => controlAction('previous')} title="Previous" />
              <button
                onClick={() => controlAction(paused ? 'resume' : 'pause')}
                style={{
                  width: '48px', height: '48px', borderRadius: '50%',
                  background: 'var(--primary)', border: 'none',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: 'white', transition: 'opacity 150ms ease',
                }}
                title={paused ? 'Resume' : 'Pause'}
              >
                {paused ? <Play size={22} fill="white" /> : <Pause size={22} fill="white" />}
              </button>
              <Button variant="ghost" size="sm" icon={SkipForward} onClick={() => controlAction('skip')} title="Skip" />
              <Button variant="ghost" size="sm" icon={Square} onClick={() => controlAction('stop')} title="Stop" />
            </div>

            {/* Volume & Loop */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '12px', borderTop: '1px solid var(--border)' }}>
              <button
                onClick={() => controlAction('loop')}
                style={{
                  background: loop_mode ? 'rgba(88, 101, 242, 0.15)' : 'transparent',
                  border: `1px solid ${loop_mode ? 'rgba(88, 101, 242, 0.4)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius-sm)',
                  padding: '6px 12px',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  color: loop_mode ? 'var(--primary)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <Repeat size={14} />
                Loop: {loop_mode || 'Off'}
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '13px' }}>
                <Volume2 size={16} />
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={volume}
                  readOnly
                  style={{ width: '80px', accentColor: 'var(--primary)' }}
                />
                <span style={{ fontSize: '12px', minWidth: '28px' }}>{volume}%</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Queue */}
        <Card>
          <CardContent style={{ padding: '20px', display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ListMusic size={17} color="var(--primary)" /> Up Next
              </h3>
              <Badge variant="primary" size="sm">{queue.length} tracks</Badge>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {queue.length === 0 ? (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', paddingTop: '48px', fontSize: '13px' }}>
                  Queue is empty — queue more tracks with /play
                </div>
              ) : (
                queue.map((track, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '10px 12px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)', width: '18px', textAlign: 'right', flexShrink: 0 }}>{idx + 1}</span>
                    <div style={{ flex: 1, overflow: 'hidden' }}>
                      <div style={{ fontSize: '13.5px', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-main)' }}>{track.title}</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{track.author}</div>
                    </div>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)', flexShrink: 0 }}>{formatTime(track.length)}</span>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default Music;
