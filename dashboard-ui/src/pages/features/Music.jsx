import { useEffect, useState, useRef } from 'react';
import { useToast } from '../../components/ToastContext';
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
  ListMusic,
  Headphones,
  Search,
  Plus,
  Loader2,
  AlertCircle,
  PhoneOff
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import Skeleton from '../../components/Skeleton';

function Music() {
  const { guildId } = useParams();
  const toast = useToast();
  const [playerInfo, setPlayerInfo] = useState(null);
  const [voiceChannels, setVoiceChannels] = useState([]);
  const [selectedChannelId, setSelectedChannelId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const [searchFeedback, setSearchFeedback] = useState('');

  const fetchMusic = async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/music`);
      setPlayerInfo(res.data);
      if (res.data?.voice_channel_id) {
        setSelectedChannelId(res.data.voice_channel_id);
      }
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

  useEffect(() => {
    api.get(`/guilds/${guildId}/voice-channels`)
      .then(res => {
        const vcs = res.data.channels || res.data || [];
        setVoiceChannels(vcs);
        if (vcs.length > 0 && !selectedChannelId) {
          setSelectedChannelId(vcs[0].id);
        }
      })
      .catch(() => {});
  }, [guildId]);

  const controlAction = async (action, extra = {}) => {
    setActionPending(true);
    try {
      await api.post(`/guilds/${guildId}/music/control`, { action, ...extra });
      await fetchMusic();
    } catch (err) {
      toast(err.response?.data?.error || 'Action failed', 'error');
    } finally {
      setActionPending(false);
    }
  };

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchFeedback('');
    try {
      const res = await api.get(`/guilds/${guildId}/music/search?q=${encodeURIComponent(searchQuery.trim())}`);
      setSearchResults(res.data.results || []);
      if (!res.data.results || res.data.results.length === 0) {
        setSearchFeedback('No tracks found for that search.');
      }
    } catch (err) {
      setSearchFeedback(err.response?.data?.error || 'Failed to search tracks.');
    } finally {
      setSearching(false);
    }
  };

  const handlePlayOrQueue = async (trackUriOrQuery) => {
    if (!selectedChannelId && (!playerInfo || !playerInfo.connected)) {
      toast('Please select a voice channel first.', 'warning');
      return;
    }
    setActionPending(true);
    try {
      await api.post(`/guilds/${guildId}/music/control`, {
        action: 'play',
        query: trackUriOrQuery,
        voice_channel_id: selectedChannelId
      });
      setSearchFeedback('Track added to playback!');
      setTimeout(() => setSearchFeedback(''), 4000);
      setSearchResults([]);
      setSearchQuery('');
      await fetchMusic();
    } catch (err) {
      toast(err.response?.data?.error || 'Failed to play track.', 'error');
    } finally {
      setActionPending(false);
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

  const isPlaying = playerInfo?.is_playing;
  const current = playerInfo?.current;
  const queue = playerInfo?.queue || [];
  const volume = playerInfo?.volume ?? 100;
  const paused = playerInfo?.paused;
  const loop_mode = playerInfo?.loop_mode;
  const progressPercent = current?.length > 0 ? (current.position / current.length) * 100 : 0;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Music2}
        title="Music Player & Controller"
        subtitle="Search tracks, queue songs, and connect the bot to any voice channel directly from the web."
        badge={
          isPlaying ? (
            <Badge variant={paused ? 'warning' : 'success'} dot>
              {paused ? 'Paused' : 'Playing Live'}
            </Badge>
          ) : playerInfo?.connected ? (
            <Badge variant="primary" dot>Connected (Idle)</Badge>
          ) : (
            <Badge variant="muted" dot>Offline</Badge>
          )
        }
      />

      {error && (
        <div style={{ padding: '12px 16px', borderRadius: 'var(--radius-md)', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.25)', color: '#f87171', fontSize: '13.5px' }}>
          {error}
        </div>
      )}

      {/* Channel Connection & Live Search Bar */}
      <Card>
        <CardContent style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center', justifyContent: 'space-between' }}>
            {/* Voice Channel Picker */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: '1 1 300px' }}>
              <Headphones size={18} color="var(--primary)" />
              <span style={{ fontSize: '13.5px', fontWeight: 600, color: 'var(--text-main)', whiteSpace: 'nowrap' }}>
                Voice Channel:
              </span>
              <select
                value={selectedChannelId}
                onChange={(e) => setSelectedChannelId(e.target.value)}
                style={{
                  flex: 1,
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-main)',
                  fontSize: '13px',
                  outline: 'none',
                }}
              >
                <option value="">Select voice channel...</option>
                {voiceChannels.map((vc) => (
                  <option key={vc.id} value={vc.id}>
                    🔊 {vc.name}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant={playerInfo?.connected ? 'secondary' : 'primary'}
                disabled={!selectedChannelId || actionPending}
                onClick={() => controlAction('connect', { voice_channel_id: selectedChannelId })}
              >
                {playerInfo?.connected ? 'Move' : 'Connect'}
              </Button>
              {playerInfo?.connected && (
                <Button
                  size="sm"
                  variant="danger"
                  disabled={actionPending}
                  icon={PhoneOff}
                  onClick={() => controlAction('disconnect')}
                >
                  Disconnect
                </Button>
              )}
            </div>

            {/* Status info */}
            {playerInfo?.voice_channel_name && (
              <Badge variant="primary" size="sm">
                Connected to #{playerInfo.voice_channel_name}
              </Badge>
            )}
          </div>

          {/* Search Box */}
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: '10px' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search song title, artist, YouTube URL, Spotify link..."
                style={{
                  width: '100%',
                  padding: '10px 14px 10px 38px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-main)',
                  fontSize: '13.5px',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
              <Search size={16} color="var(--text-muted)" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }} />
            </div>
            <Button type="submit" variant="primary" disabled={searching || !searchQuery.trim()}>
              {searching ? <Loader2 size={16} className="animate-spin" /> : 'Search'}
            </Button>
          </form>

          {searchFeedback && (
            <div style={{ fontSize: '13px', color: searchFeedback.includes('added') ? 'var(--success)' : 'var(--text-muted)' }}>
              {searchFeedback}
            </div>
          )}

          {/* Search Results Dropdown List */}
          {searchResults.length > 0 && (
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              maxHeight: '280px',
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              padding: '8px'
            }}>
              <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', padding: '4px 8px' }}>
                Search Results ({searchResults.length})
              </div>
              {searchResults.map((res, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    background: 'var(--bg-main)',
                    border: '1px solid var(--border)',
                    gap: '12px'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
                    {res.thumbnail ? (
                      <img src={res.thumbnail} alt="" style={{ width: '40px', height: '40px', borderRadius: '4px', objectFit: 'cover' }} />
                    ) : (
                      <div style={{ width: '40px', height: '40px', borderRadius: '4px', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Music2 size={18} color="var(--text-muted)" />
                      </div>
                    )}
                    <div style={{ overflow: 'hidden' }}>
                      <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {res.title}
                      </div>
                      <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                        {res.author} {res.length ? `· ${formatTime(res.length)}` : ''}
                      </div>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={actionPending}
                    icon={Plus}
                    onClick={() => handlePlayOrQueue(res.uri || res.title)}
                  >
                    {isPlaying ? 'Queue' : 'Play'}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Main Player Display */}
      {isPlaying && current ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))', gap: '24px' }}>
          {/* Now Playing */}
          <Card>
            <CardContent style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Thumbnail */}
              <div style={{
                width: '100%',
                aspectRatio: '16/9',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                position: 'relative',
                overflow: 'hidden',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                {current.thumbnail ? (
                  <img
                    src={current.thumbnail}
                    alt={current.title}
                    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={e => { e.currentTarget.style.display = 'none'; }}
                  />
                ) : (
                  <Music2 size={48} color="var(--text-muted)" />
                )}
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
                    onChange={(e) => controlAction('volume', { volume: e.target.value })}
                    style={{ width: '80px', accentColor: 'var(--primary)', cursor: 'pointer' }}
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
                  <ListMusic size={17} color="var(--primary)" /> Up Next in Queue
                </h3>
                <Badge variant="primary" size="sm">{queue.length} tracks</Badge>
              </div>

              <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '380px' }}>
                {queue.length === 0 ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-muted)', paddingTop: '48px', fontSize: '13px' }}>
                    Queue is empty — search songs above to add to queue
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
      ) : (
        <Card>
          <CardContent style={{ padding: '48px 24px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '14px' }}>
            <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: 'rgba(88, 101, 242, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Music2 size={32} color="var(--primary)" />
            </div>
            <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--text-main)' }}>
              No Music Playing Right Now
            </h3>
            <p style={{ margin: 0, fontSize: '14px', color: 'var(--text-muted)', maxWidth: '440px' }}>
              Select a voice channel above and search for any song or playlist, or type a track name above to start broadcasting instantly from the dashboard.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default Music;
