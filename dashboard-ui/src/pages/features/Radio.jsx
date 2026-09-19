import { useEffect, useState, useRef } from 'react';
import { useParams } from 'react-router-dom';
import {
  Radio as RadioIcon,
  Play,
  Pause,
  Square,
  Volume2,
  VolumeX,
  Volume1,
  Wifi,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  RadioReceiver,
  Headphones,
  Signal
} from 'lucide-react';
import api from '../../api';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import Toggle from '../../components/Toggle';

function groupByCategory(stations = []) {
  const groups = {};
  for (const s of stations) {
    if (!groups[s.category]) groups[s.category] = [];
    groups[s.category].push(s);
  }
  return groups;
}

function Radio() {
  const { guildId } = useParams();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionPending, setActionPending] = useState(false);
  const [localVolume, setLocalVolume] = useState(100);
  const volumeDebounce = useRef(null);
  const isDragging = useRef(false);

  const fetchState = async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/radio`);
      setState(res.data);
      setError('');
      if (!isDragging.current) setLocalVolume(res.data.volume ?? 100);
    } catch (err) {
      if (err.response?.status !== 404) setError('Failed to load radio state.');
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 4000);
    return () => clearInterval(interval);
  }, [guildId]);

  const control = async (action, extra = {}) => {
    setActionPending(true);
    try {
      await api.post(`/guilds/${guildId}/radio/control`, { action, ...extra });
      await fetchState();
    } catch (err) {
      alert(err.response?.data?.error || 'Action failed');
    }
    setActionPending(false);
  };

  const handleVolumeChange = (val) => {
    isDragging.current = true;
    setLocalVolume(val);
    if (volumeDebounce.current) clearTimeout(volumeDebounce.current);
    volumeDebounce.current = setTimeout(() => {
      isDragging.current = false;
      control('set_volume', { volume: val });
    }, 400);
  };

  if (loading) {
    return (
      <div className="flex flex-col gap-6 animate-fade-in">
        <div className="skeleton" style={{ height: '72px' }} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="skeleton" style={{ height: '380px' }} />
          <div className="skeleton" style={{ height: '380px' }} />
        </div>
      </div>
    );
  }

  const stations = state?.stations ?? [];
  const stationGroups = groupByCategory(stations);
  const isActive = state?.active;
  const isPaused = state?.paused;
  const is247 = state?.mode_247;
  const currentStationKey = state?.station_key;
  const currentStation = stations.find((s) => s.key === currentStationKey);

  const getVolumeIcon = () => {
    if (localVolume === 0) return VolumeX;
    if (localVolume < 50) return Volume1;
    return Volume2;
  };
  const VolIcon = getVolumeIcon();

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <PageHeader
        icon={RadioIcon}
        title="Radio Station"
        subtitle="24/7 ultra-low CPU radio streaming — select stations and control playback directly from your dashboard."
        badge={
          isActive ? (
            <Badge variant={isPaused ? 'warning' : 'success'} dot>
              {isPaused ? 'Paused' : 'Streaming Live'}
            </Badge>
          ) : (
            <Badge variant="muted" dot>Offline</Badge>
          )
        }
      />

      {error && (
        <div className="p-4 rounded-xl bg-danger/10 border border-danger/30 text-danger text-sm flex items-center gap-3">
          <AlertCircle size={18} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Player & Controls (5 cols) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <Card className="p-6 flex flex-col gap-6">
            {/* Station Hero Banner */}
            <div
              className={`rounded-2xl p-6 text-center relative overflow-hidden transition-all duration-500 flex flex-col items-center justify-center min-h-[220px] ${
                isActive
                  ? 'bg-gradient-to-br from-primary/90 via-indigo-600/80 to-cyan-600/70 shadow-lg shadow-primary/20 text-white'
                  : 'bg-card-sub border border-border text-muted'
              }`}
            >
              {/* Radio Wave Effects */}
              {isActive && !isPaused && (
                <div className="absolute inset-0 pointer-events-none opacity-20">
                  {[...Array(3)].map((_, i) => (
                    <div
                      key={i}
                      className="absolute bottom-[-10px] left-1/2 -translate-x-1/2 rounded-full border-2 border-white"
                      style={{
                        width: `${100 + i * 50}px`,
                        height: `${100 + i * 50}px`,
                        animation: `radioWave 2.4s cubic-bezier(0.25, 0.8, 0.25, 1) ${i * 0.5}s infinite`
                      }}
                    />
                  ))}
                </div>
              )}

              <div className="text-5xl mb-3 relative drop-shadow-md">
                {currentStation?.emoji ?? '📻'}
              </div>
              <h2 className="text-xl font-bold tracking-tight relative text-white">
                {isActive ? (currentStation?.name ?? 'Unknown Station') : 'No Station Playing'}
              </h2>
              <p className="text-xs mt-1.5 opacity-85 relative max-w-xs text-center line-clamp-2">
                {isActive
                  ? currentStation?.desc ?? ''
                  : 'Select a radio station from the library to begin broadcasting.'}
              </p>

              {/* Status pill */}
              <div className="mt-4 px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-2 bg-black/30 backdrop-blur-md text-white border border-white/10 relative">
                <span
                  className={`w-2 h-2 rounded-full ${
                    isActive
                      ? isPaused
                        ? 'bg-amber-400'
                        : 'bg-emerald-400 shadow-[0_0_8px_#34d399] animate-pulse'
                      : 'bg-neutral-400'
                  }`}
                />
                <span>
                  {isActive ? (isPaused ? 'Playback Paused' : 'Live on Air') : 'Broadcaster Idle'}
                </span>
              </div>
            </div>

            {/* Playback Controls */}
            <div className="flex items-center justify-center gap-4 py-2">
              <Button
                variant={isPaused ? 'primary' : 'secondary'}
                size="lg"
                className="rounded-full w-14 h-14 p-0 shadow-sm"
                onClick={() => control(isPaused ? 'resume' : 'pause')}
                disabled={!isActive || actionPending}
                title={isPaused ? 'Resume Playback' : 'Pause Playback'}
              >
                {isPaused ? <Play size={22} className="ml-0.5" /> : <Pause size={22} />}
              </Button>

              <Button
                variant="danger"
                size="lg"
                className="rounded-full w-14 h-14 p-0 shadow-sm"
                onClick={() => control('stop')}
                disabled={!isActive || actionPending}
                title="Stop and Disconnect"
              >
                <Square size={20} />
              </Button>
            </div>

            {/* Volume Control */}
            <div className="space-y-2 pt-2 border-t border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium text-main">
                  <VolIcon size={16} className="text-muted" />
                  <span>Stream Volume</span>
                </div>
                <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-primary/10 text-primary">
                  {localVolume}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="200"
                value={localVolume}
                onChange={(e) => handleVolumeChange(Number(e.target.value))}
                className="w-full h-1.5 bg-border rounded-lg appearance-none cursor-pointer accent-primary"
              />
            </div>

            {/* 24/7 Mode Switch */}
            <div className="p-4 rounded-xl bg-card-sub border border-border flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-main flex items-center gap-2">
                  <Signal size={16} className="text-primary" />
                  <span>24/7 Continuous Mode</span>
                </div>
                <div className="text-xs text-muted mt-0.5">
                  Bot stays in voice channel and auto-reconnects on reboot
                </div>
              </div>
              <Toggle
                checked={Boolean(is247)}
                disabled={actionPending}
                onChange={() => control('toggle_247')}
              />
            </div>

            {/* Connected Channel Info */}
            {isActive && state?.voice_channel_name && (
              <div className="p-3.5 rounded-xl bg-primary/5 border border-primary/20 flex items-center gap-3">
                <Headphones size={20} className="text-primary shrink-0" />
                <div className="overflow-hidden">
                  <div className="text-xs text-muted">Transmitting in</div>
                  <div className="text-sm font-bold text-main truncate">
                    {state.voice_channel_name}
                  </div>
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* Right: Station Library (7 cols) */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          <Card className="p-6 flex flex-col flex-1">
            <CardHeader className="p-0 pb-4 mb-2 border-b border-border">
              <CardTitle icon={RadioReceiver}>Station Library</CardTitle>
            </CardHeader>

            <div className="flex flex-col gap-6 overflow-y-auto max-h-[640px] pr-1">
              {Object.entries(stationGroups).map(([category, categoryStations]) => (
                <div key={category} className="space-y-2.5">
                  <div className="text-xs font-bold uppercase tracking-wider text-muted px-1">
                    {category}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {categoryStations.map((station) => {
                      const isSelected = station.key === currentStationKey && isActive;
                      return (
                        <div
                          key={station.key}
                          role="button"
                          tabIndex={0}
                          onClick={() =>
                            !actionPending && control('set_station', { station_key: station.key })
                          }
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              control('set_station', { station_key: station.key });
                            }
                          }}
                          className={`p-3.5 rounded-xl border flex items-center gap-3 cursor-pointer transition-all duration-150 ${
                            isSelected
                              ? 'bg-primary/10 border-primary shadow-sm shadow-primary/10'
                              : 'bg-card-sub/60 hover:bg-card-sub border-border hover:border-border-hover'
                          } ${actionPending ? 'opacity-60 pointer-events-none' : ''}`}
                        >
                          <span className="text-2xl shrink-0 drop-shadow-sm">
                            {station.emoji}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-semibold truncate text-main">
                              {station.name}
                            </div>
                            <div className="text-xs text-muted truncate mt-0.5">
                              {station.desc}
                            </div>
                          </div>
                          {isSelected && (
                            <Badge variant={isPaused ? 'warning' : 'success'} size="sm" dot>
                              {isPaused ? 'PAUSED' : 'LIVE'}
                            </Badge>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              {stations.length === 0 && (
                <div className="text-center text-muted py-12">
                  <RadioIcon size={32} className="mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No radio stations available</p>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      <style>{`
        @keyframes radioWave {
          0% { transform: translateX(-50%) scale(0.3); opacity: 1; }
          100% { transform: translateX(-50%) scale(1.15); opacity: 0; }
        }
      `}</style>
    </div>
  );
}

export default Radio;
