import { useEffect, useState } from 'react';
import api from '../api';
import { useBotName } from '../BotContext';
import { SitePage } from '../components/SiteLayout';
import { Activity, Server, Users, Terminal as TerminalIcon, Timer, RefreshCw } from 'lucide-react';

function formatUptime(seconds) {
  if (seconds == null) return '—';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts = [];
  if (d) parts.push(`${d}d`);
  if (h || d) parts.push(`${h}h`);
  parts.push(`${m}m`);
  return parts.join(' ');
}

export function Status({ user }) {
  const botName = useBotName();
  const brand = (botName || 'Bot').trim();
  const [stats, setStats] = useState(null);       // null = no data yet; object once the API responds
  const [apiError, setApiError] = useState(false); // true = the API call itself failed (wrong URL, CORS, backend down...)
  const [refreshing, setRefreshing] = useState(false);
  const [lastChecked, setLastChecked] = useState(null);

  // A failed request (network error, 404, CORS, wrong VITE_API_URL, backend
  // down) is a DIFFERENT situation from "the bot successfully reported it is
  // offline" -- the backend responding with `online: false` is a normal,
  // successful API call. Only a thrown/caught error means the API itself is
  // unreachable.
  const load = () => {
    setRefreshing(true);
    api.get('/public/stats')
      .then(res => {
        setStats(res.data);
        setApiError(false);
      })
      .catch(() => {
        setApiError(true);
      })
      .finally(() => {
        setLastChecked(new Date());
        setRefreshing(false);
      });
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t); // single interval, always cleaned up -- no leaks on unmount/re-nav
  }, []);

  const checking = stats === null && !apiError;
  const online = !apiError && stats && stats.online;

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64 }}>
        <div className="container" style={{ maxWidth: 760 }}>
          <div className="site-section-head">
            <div className="site-eyebrow">Live status</div>
            <h2>{brand} System Status</h2>
          </div>

          <div className={`site-status-banner ${checking ? '' : online ? '' : 'offline'}`}>
            <span className="big-dot" />
            <div>
              <h3>
                {checking
                  ? 'Checking status…'
                  : apiError
                    ? 'Unable to reach status service'
                    : online
                      ? 'All systems operational'
                      : 'Bot appears to be offline'}
              </h3>
              <p>
                {apiError && 'The dashboard API could not be reached — this is a connection problem, not necessarily the bot itself. '}
                {lastChecked ? `Last checked ${lastChecked.toLocaleTimeString()}` : 'Checking...'} · Auto-refreshes every 30s
              </p>
            </div>
          </div>

          <div className="site-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
            <div className="site-card">
              <div className="site-card-icon"><Server size={20} /></div>
              <h3>Servers</h3>
              <p style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-main)' }}>{apiError ? '—' : stats ? stats.servers : '—'}</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><Users size={20} /></div>
              <h3>Members</h3>
              <p style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-main)' }}>{apiError ? '—' : stats ? stats.members?.toLocaleString() : '—'}</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><TerminalIcon size={20} /></div>
              <h3>Commands loaded</h3>
              <p style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-main)' }}>{apiError ? '—' : stats ? stats.commands : '—'}</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><Activity size={20} /></div>
              <h3>Latency</h3>
              <p style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-main)' }}>{!apiError && stats && stats.latency_ms != null ? `${stats.latency_ms}ms` : '—'}</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><Timer size={20} /></div>
              <h3>Uptime</h3>
              <p style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-main)' }}>{apiError ? '—' : stats ? formatUptime(stats.uptime_seconds) : '—'}</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><RefreshCw size={20} /></div>
              <h3>Refresh now</h3>
              <button type="button" className="site-btn site-btn-ghost" style={{ marginTop: 6 }} onClick={load} disabled={refreshing}>
                {refreshing ? 'Checking…' : 'Check again'}
              </button>
            </div>
          </div>
        </div>
      </section>
    </SitePage>
  );
}

export default Status;
