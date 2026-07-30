import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';

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
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchMusic();
    const interval = setInterval(fetchMusic, 3000); // Poll every 3 seconds for live updates
    return () => clearInterval(interval);
  }, [guildId]);

  const controlAction = async (action) => {
    try {
      await api.post(`/guilds/${guildId}/music/control`, { action });
      fetchMusic(); // refresh immediately
    } catch (err) {
      alert(err.response?.data?.error || 'Action failed');
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '350px', marginBottom: '24px' }}></div>
      </div>
    );
  }

  if (!playerInfo || !playerInfo.is_playing) {
    return (
      <div className="animate-fade-in">
        <div className="page-header">
          <h1 className="page-title">🎵 Music Player</h1>
          <p className="page-subtitle">Control the bot's audio playback directly from the dashboard.</p>
        </div>
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">🎧</div>
          <h3 className="empty-state-title">Nothing playing</h3>
          <p className="empty-state-desc">Join a voice channel and use the play command to start the party.</p>
        </div>
      </div>
    );
  }

  const { current, queue, volume, paused, loop_mode } = playerInfo;
  
  // Calculate progress percentage
  const progressPercent = current.length > 0 ? (current.position / current.length) * 100 : 0;

  const formatTime = (ms) => {
    if (!ms) return "0:00";
    const totalSeconds = Math.floor(ms / 1000);
    const m = Math.floor(totalSeconds / 60);
    const s = Math.floor(totalSeconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">🎵 Music Player</h1>
        <p className="page-subtitle">Live playback control</p>
      </div>

      <div className="grid-2">
        {/* Now Playing Card */}
        <div className="glass-panel flex flex-col" style={{ padding: '24px' }}>
          <div style={{
            width: '100%', aspectRatio: '16/9', borderRadius: '12px', marginBottom: '20px',
            backgroundImage: `url(${current.thumbnail || 'https://images.unsplash.com/photo-1614149162883-504ce4d13909?q=80&w=600'})`,
            backgroundSize: 'cover', backgroundPosition: 'center',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)', position: 'relative'
          }}>
            {paused && (
              <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '48px' }}>
                ⏸️
              </div>
            )}
          </div>
          
          <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '8px', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {current.title}
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginBottom: '20px' }}>{current.author}</p>

          <div style={{ marginBottom: '24px' }}>
            <div className="music-progress-bar">
              <div className="music-progress-fill" style={{ width: `${progressPercent}%` }}></div>
            </div>
            <div className="flex justify-between mt-2" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              <span>{formatTime(current.position)}</span>
              <span>{formatTime(current.length)}</span>
            </div>
          </div>

          <div className="flex justify-center gap-4 mt-auto">
            <button className="btn btn-icon btn-ghost" title="Previous" onClick={() => controlAction('previous')}>⏮️</button>
            <button className="btn btn-icon btn-primary" style={{ width: '48px', height: '48px', borderRadius: '50%', fontSize: '20px' }} onClick={() => controlAction(paused ? 'resume' : 'pause')}>
              {paused ? '▶️' : '⏸️'}
            </button>
            <button className="btn btn-icon btn-ghost" title="Skip" onClick={() => controlAction('skip')}>⏭️</button>
            <button className="btn btn-icon btn-ghost" title="Stop" onClick={() => controlAction('stop')}>⏹️</button>
          </div>
        </div>

        {/* Up Next / Queue */}
        <div className="glass-panel flex flex-col" style={{ padding: '24px' }}>
          <div className="flex justify-between items-center" style={{ marginBottom: '16px' }}>
            <h3 style={{ fontSize: '18px', margin: 0 }}>Up Next</h3>
            <span className="badge badge-primary">{queue.length} tracks</span>
          </div>
          
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {queue.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '40px' }}>
                Queue is empty
              </div>
            ) : (
              queue.map((track, idx) => (
                <div key={idx} className="queue-item">
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', width: '20px' }}>{idx + 1}</div>
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ fontSize: '14px', fontWeight: '500', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{track.title}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-sub)' }}>{track.author}</div>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{formatTime(track.length)}</div>
                </div>
              ))
            )}
          </div>
          
          <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div className="flex items-center gap-2">
              <button className={`btn btn-sm ${loop_mode ? 'btn-primary' : 'btn-ghost'}`} onClick={() => controlAction('loop')}>
                🔁 Loop: {loop_mode || 'Off'}
              </button>
            </div>
            <div className="flex items-center gap-2">
              <span style={{ fontSize: '14px' }}>🔈</span>
              <input type="range" min="0" max="100" value={volume} readOnly style={{ width: '80px', accentColor: 'var(--primary)' }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Music;
