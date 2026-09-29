import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { SitePage } from '../components/SiteLayout';
import {
  FileText,
  Search,
  RefreshCw,
  User,
  Shield,
  Clock,
  ExternalLink,
  Filter,
  CheckCircle,
  LogIn,
  Music,
  Radio,
  Ticket,
  Sliders,
  AlertTriangle
} from 'lucide-react';
import { Loader, Spinner } from '../components/Loader';
import '../admin-panel.css';

function timeAgo(ts) {
  if (!ts) return '';
  const s = Math.floor(Date.now() / 1000) - ts;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function formatDate(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

const CATEGORIES = [
  { id: 'all', label: 'All Events' },
  { id: 'auth', label: 'Sign-ins & Logins' },
  { id: 'welcome', label: 'Welcome & Leave' },
  { id: 'tickets', label: 'Tickets' },
  { id: 'music', label: 'Music Controls' },
  { id: 'radio', label: 'Radio Controls' },
  { id: 'security', label: 'Security & Anti-Spam' },
  { id: 'custom_commands', label: 'Custom Commands' },
  { id: 'devnews', label: 'Dev News' },
  { id: 'blacklist', label: 'Blacklist' },
  { id: 'banner', label: 'Bot Profile' },
];

export function Weblog({ user }) {
  const [checking, setChecking] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    api.get('/admin/whoami')
      .then(res => setIsAdmin(!!res.data?.is_admin))
      .catch(() => setIsAdmin(false))
      .finally(() => setChecking(false));
  }, []);

  const loadEvents = async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (selectedCategory && selectedCategory !== 'all') {
        params.append('category', selectedCategory);
      }
      if (searchTerm.trim()) {
        params.append('search', searchTerm.trim());
      }
      params.append('limit', '200');

      const res = await api.get(`/admin/weblog?${params.toString()}`);
      setEvents(res.data.events || []);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to fetch weblog entries.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      loadEvents();
    }
  }, [isAdmin, selectedCategory]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadEvents();
  };

  if (checking) {
    return <Loader label="Verifying access…" />;
  }

  if (!isAdmin) {
    return (
      <SitePage user={user}>
        <section className="site-section" style={{ paddingTop: 90, textAlign: 'center' }}>
          <div className="container" style={{ maxWidth: 460 }}>
            <Shield size={40} color="var(--danger)" style={{ marginBottom: 14 }} />
            <h2 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8 }}>Access Denied</h2>
            <p style={{ color: 'var(--text-sub)' }}>
              This audit log is restricted to bot staff and administrators.
            </p>
          </div>
        </section>
      </SitePage>
    );
  }

  const getCategoryIcon = (cat) => {
    switch (cat) {
      case 'auth': return <LogIn size={15} color="#57F287" />;
      case 'music': return <Music size={15} color="#9B59B6" />;
      case 'radio': return <Radio size={15} color="#3498DB" />;
      case 'tickets': return <Ticket size={15} color="#F1C40F" />;
      case 'security': return <Shield size={15} color="#E74C3C" />;
      default: return <Sliders size={15} color="#5865F2" />;
    }
  };

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64 }}>
        <div className="container" style={{ maxWidth: 1100 }}>
          {/* Header */}
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '16px', marginBottom: '24px' }}>
            <div>
              <div className="site-eyebrow">Real-Time Audit System</div>
              <h2 style={{ fontSize: '28px', fontWeight: 800, margin: '4px 0 6px' }}>Website Action Weblog</h2>
              <p style={{ color: 'var(--text-sub)', margin: 0, fontSize: '14px' }}>
                Complete live log of user sign-ins, feature usage, configuration changes, and dashboard interactions.
              </p>
            </div>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={loadEvents}
                disabled={loading}
                className="site-btn site-btn-ghost"
                style={{ padding: '8px 14px' }}
                title="Refresh log"
              >
                <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
                <span>Refresh</span>
              </button>
              <Link to="/admin" className="site-btn site-btn-secondary" style={{ padding: '8px 14px' }}>
                <span>Back to Admin</span>
              </Link>
            </div>
          </div>

          {/* Controls: Search and Categories */}
          <div className="site-card" style={{ padding: '16px 20px', marginBottom: '20px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center', justifyContent: 'space-between' }}>
              <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px', flex: '1 1 320px' }}>
                <div style={{ position: 'relative', flex: 1 }}>
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Search by username, user ID, server name, or action..."
                    style={{
                      width: '100%',
                      padding: '9px 12px 9px 34px',
                      borderRadius: '8px',
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      color: 'var(--text-main)',
                      fontSize: '13.5px',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                  />
                  <Search size={15} color="var(--text-muted)" style={{ position: 'absolute', left: '11px', top: '50%', transform: 'translateY(-50%)' }} />
                </div>
                <button type="submit" className="site-btn site-btn-primary" style={{ padding: '8px 16px' }}>
                  Search
                </button>
              </form>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflowX: 'auto', paddingBottom: '2px' }}>
                <Filter size={15} color="var(--text-muted)" />
                <span style={{ fontSize: '13px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>Category:</span>
                <select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: '8px',
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-main)',
                    fontSize: '13px',
                    outline: 'none'
                  }}
                >
                  {CATEGORIES.map(c => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {error && (
            <div className="site-alert site-alert-error" style={{ marginBottom: '20px' }}>
              {error}
            </div>
          )}

          {/* Event Stream */}
          <div className="site-card" style={{ padding: '0', overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-main)' }}>
                Activity Stream
              </div>
              <span className="admin-card-count">{events.length} records</span>
            </div>

            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                <Spinner size={16} /> Loading audit records...
              </div>
            ) : events.length === 0 ? (
              <div style={{ padding: '48px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
                No audit events recorded yet matching this filter.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {events.map((ev) => (
                  <div
                    key={ev.id}
                    style={{
                      padding: '14px 20px',
                      borderBottom: '1px solid var(--border)',
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'flex-start',
                      justifyContent: 'space-between',
                      gap: '12px',
                      transition: 'background 120ms ease'
                    }}
                  >
                    <div style={{ display: 'flex', gap: '14px', flex: '1 1 400px' }}>
                      <div
                        style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '8px',
                          background: 'rgba(255,255,255,0.05)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0
                        }}
                      >
                        {getCategoryIcon(ev.category)}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-main)' }}>
                            {ev.action}
                          </span>
                          <span
                            style={{
                              fontSize: '11px',
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              background: 'rgba(88, 101, 242, 0.15)',
                              color: 'var(--primary)'
                            }}
                          >
                            {ev.category}
                          </span>
                        </div>
                        {ev.details && (
                          <div style={{ fontSize: '13px', color: 'var(--text-sub)', marginTop: '2px' }}>
                            {ev.details}
                          </div>
                        )}
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '4px' }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <User size={12} /> By: <strong style={{ color: 'var(--text-main)' }}>{ev.actor_name || ev.actor_id || 'Unknown'}</strong>
                          </span>
                          {ev.guild_name && (
                            <>
                              <span>·</span>
                              <span>Server: <strong style={{ color: 'var(--text-main)' }}>{ev.guild_name}</strong></span>
                            </>
                          )}
                          {ev.actor_id && (
                            <>
                              <span>·</span>
                              <span>ID: <code>{ev.actor_id}</code></span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }} title={formatDate(ev.timestamp)}>
                        {timeAgo(ev.timestamp)}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                        {formatDate(ev.timestamp)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </SitePage>
  );
}

export default Weblog;
