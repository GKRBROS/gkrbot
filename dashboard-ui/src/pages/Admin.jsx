import { useEffect, useState } from 'react';
import api from '../api';
import { SitePage } from '../components/SiteLayout';
import {
  ShieldAlert, ImageIcon, Loader2, Ticket, ExternalLink,
  Newspaper, Trash2, Send, Ban, FileText, Settings, Users,
  Activity, ChevronRight, AlertCircle
} from 'lucide-react';
import { Loader, Spinner } from '../components/Loader';
import { Link } from 'react-router-dom';
import '../admin-panel.css';

function timeAgo(ts) {
  if (!ts) return '';
  const s = Math.floor(Date.now() / 1000) - ts;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function SectionHeader({ icon: Icon, title, subtitle }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
      <div style={{
        width: 36, height: 36, borderRadius: 10,
        background: 'rgba(88,101,242,0.12)', border: '1px solid rgba(88,101,242,0.2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={18} color="#818cf8" />
      </div>
      <div>
        <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-main)' }}>{title}</div>
        {subtitle && <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 1 }}>{subtitle}</div>}
      </div>
    </div>
  );
}

export function Admin({ user }) {
  const [checking, setChecking] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  const [bannerUrl, setBannerUrl] = useState('');
  const [bannerStatus, setBannerStatus] = useState('idle');
  const [bannerError, setBannerError] = useState('');

  const [tickets, setTickets] = useState(null);
  const [ticketsError, setTicketsError] = useState('');

  const [news, setNews] = useState(null);
  const [newsTitle, setNewsTitle] = useState('');
  const [newsBody, setNewsBody] = useState('');
  const [newsMedia, setNewsMedia] = useState('');
  const [newsLink, setNewsLink] = useState('');
  const [newsError, setNewsError] = useState('');
  const [newsStatus, setNewsStatus] = useState('idle');

  useEffect(() => {
    api.get('/admin/whoami')
      .then(res => setIsAdmin(!!res.data?.is_admin))
      .catch(() => setIsAdmin(false))
      .finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    api.get('/admin/tickets')
      .then(res => setTickets(res.data.tickets || []))
      .catch(err => setTicketsError(err.response?.data?.error || 'Could not load tickets.'));
  }, [isAdmin]);

  const loadNews = () => {
    api.get('/public/devnews').then(res => setNews(res.data.entries || [])).catch(() => setNews([]));
  };
  useEffect(() => { if (isAdmin) loadNews(); }, [isAdmin]);

  const handleNewsSubmit = async (e) => {
    e.preventDefault();
    setNewsError('');
    if (newsTitle.trim().length < 3) return setNewsError('Title must be at least 3 characters.');
    setNewsStatus('saving');
    try {
      await api.post('/admin/devnews', {
        title: newsTitle.trim(), body: newsBody.trim(),
        media_url: newsMedia.trim(), link_url: newsLink.trim(),
      });
      setNewsTitle(''); setNewsBody(''); setNewsMedia(''); setNewsLink('');
      loadNews();
    } catch (err) {
      setNewsError(err.response?.data?.error || 'Failed to publish.');
    } finally {
      setNewsStatus('idle');
    }
  };

  const handleNewsDelete = async (id) => {
    try {
      await api.delete(`/admin/devnews/${id}`);
      setNews(prev => (prev || []).filter(n => n.id !== id));
    } catch (err) {
      setNewsError(err.response?.data?.error || 'Failed to delete.');
    }
  };

  const handleBannerSubmit = async (e) => {
    e.preventDefault();
    setBannerError('');
    if (!/^https?:\/\//i.test(bannerUrl.trim())) {
      setBannerError('Enter a direct image URL.');
      return;
    }
    setBannerStatus('saving');
    try {
      await api.post('/admin/bot-banner', { url: bannerUrl.trim() });
      setBannerStatus('success');
    } catch (err) {
      setBannerStatus('error');
      setBannerError(err.response?.data?.error || 'Failed to update banner.');
    }
  };

  if (checking) return <Loader label="Checking access…" />;

  if (!isAdmin) {
    return (
      <SitePage user={user}>
        <section className="site-section" style={{ paddingTop: 90, textAlign: 'center' }}>
          <div className="container" style={{ maxWidth: 460 }}>
            <ShieldAlert size={40} color="var(--danger)" style={{ marginBottom: 14 }} />
            <h2 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8 }}>Access Denied</h2>
            <p style={{ color: 'var(--text-sub)' }}>
              {user ? "This page is restricted to the bot's owner/admins." : 'Please sign in with an authorized account.'}
            </p>
          </div>
        </section>
      </SitePage>
    );
  }

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64 }}>
        <div className="container admin-shell">

          {/* ── Page Header ── */}
          <div className="admin-page-header">
            <div>
              <div className="site-eyebrow">Owner Only</div>
              <h2 style={{ margin: '4px 0 6px' }}>Admin Panel</h2>
              <p style={{ color: 'var(--text-sub)', margin: 0, fontSize: 14 }}>
                Manage bot content, settings, and monitor incoming support tickets.
              </p>
            </div>

            {/* Quick Nav Links */}
            <div className="admin-quick-links">
              <Link to="/admin/blacklist" className="admin-quick-link">
                <Ban size={16} />
                <span>Blacklist</span>
                <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </Link>
              <Link to="/admin/weblog" className="admin-quick-link">
                <FileText size={16} />
                <span>Weblog</span>
                <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </Link>
            </div>
          </div>

          {/* ── Stats Bar ── */}
          <div className="admin-stats-bar">
            <div className="admin-stat-card">
              <div className="admin-stat-value">{tickets === null ? '—' : tickets.length}</div>
              <div className="admin-stat-label">Open Tickets</div>
            </div>
            <div className="admin-stat-card">
              <div className="admin-stat-value">{news === null ? '—' : news.length}</div>
              <div className="admin-stat-label">Published Posts</div>
            </div>
            <div className="admin-stat-card">
              <div className="admin-stat-value">{news && news[0] ? timeAgo(news[0].created_at) : '—'}</div>
              <div className="admin-stat-label">Last Update</div>
            </div>
            <div className="admin-stat-card">
              <div className="admin-stat-value" style={{ color: '#34d399' }}>Online</div>
              <div className="admin-stat-label">Bot Status</div>
            </div>
          </div>

          {/* ── Main Grid ── */}
          <div className="admin-main-grid">

            {/* Left Column: News Composer + Published Feed */}
            <div className="admin-col-left">

              {/* Section: Content Management */}
              <div className="site-card admin-section-card">
                <SectionHeader icon={Newspaper} title="Post Dev News Update" subtitle="Published instantly to the public Dev News page" />

                <form onSubmit={handleNewsSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div className="site-field">
                    <label>Title</label>
                    <input
                      type="text"
                      value={newsTitle}
                      onChange={e => setNewsTitle(e.target.value)}
                      placeholder="e.g. New: Animated welcome cards"
                      maxLength={100}
                    />
                  </div>
                  <div className="site-field">
                    <label>Description</label>
                    <textarea
                      value={newsBody}
                      onChange={e => setNewsBody(e.target.value)}
                      placeholder="What changed and why it matters..."
                      maxLength={1000}
                      rows={4}
                    />
                  </div>
                  <div className="admin-field-row">
                    <div className="site-field">
                      <label>Image / GIF URL (optional)</label>
                      <input type="text" value={newsMedia} onChange={e => setNewsMedia(e.target.value)} placeholder="https://example.com/preview.gif" />
                    </div>
                    <div className="site-field">
                      <label>Link URL (optional)</label>
                      <input type="text" value={newsLink} onChange={e => setNewsLink(e.target.value)} placeholder="https://example.com/docs/feature" />
                    </div>
                  </div>

                  {newsMedia.trim() && /^https?:\/\//i.test(newsMedia.trim()) && (
                    <img src={newsMedia.trim()} alt="Preview" className="site-banner-preview" style={{ aspectRatio: '16/9' }} onError={e => { e.currentTarget.style.opacity = 0.2; }} />
                  )}

                  {newsError && (
                    <div className="site-alert site-alert-error" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <AlertCircle size={14} /> {newsError}
                    </div>
                  )}

                  <button type="submit" className="site-btn site-btn-primary" disabled={newsStatus === 'saving'} style={{ justifyContent: 'center' }}>
                    {newsStatus === 'saving' ? 'Publishing…' : <><Send size={15} /> <span>Publish Update</span></>}
                  </button>
                </form>

                {/* Published feed */}
                {news && news.length > 0 && (
                  <div style={{ marginTop: 20 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: 10 }}>
                      Published ({news.length})
                    </div>
                    <div className="admin-news-feed">
                      {news.map(n => (
                        <div key={n.id} className="admin-news-item">
                          {n.media_url ? (
                            <img src={n.media_url} alt="" className="admin-news-thumb" onError={e => { e.currentTarget.style.visibility = 'hidden'; }} />
                          ) : (
                            <div className="admin-news-thumb" />
                          )}
                          <div className="admin-news-item-body">
                            <div className="admin-news-item-title">{n.title}</div>
                            {n.body && <div className="admin-news-item-desc">{n.body}</div>}
                            <div className="admin-news-item-meta">{timeAgo(n.created_at)}</div>
                          </div>
                          <button type="button" onClick={() => handleNewsDelete(n.id)} className="site-btn site-btn-ghost" style={{ padding: '6px 10px', alignSelf: 'flex-start' }} title="Delete">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Right Column: Bot Settings + Tickets */}
            <div className="admin-col-right">

              {/* Section: Bot Settings */}
              <div className="site-card admin-section-card">
                <SectionHeader icon={Settings} title="Bot Settings" subtitle="Global bot configuration" />

                <div style={{ fontSize: 13, color: 'var(--text-sub)', marginBottom: 14, background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.15)', borderRadius: 8, padding: '10px 14px' }}>
                  ⚠️ Banner changes are <strong>global</strong> — Discord limits frequency. Wait ~10 min between changes.
                </div>

                <form onSubmit={handleBannerSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div className="site-field">
                    <label>Bot Profile Banner URL</label>
                    <input
                      type="text"
                      value={bannerUrl}
                      onChange={e => { setBannerUrl(e.target.value); setBannerStatus('idle'); }}
                      placeholder="https://example.com/banner.png"
                    />
                  </div>
                  {bannerUrl.trim() && /^https?:\/\//i.test(bannerUrl.trim()) && (
                    <img src={bannerUrl.trim()} alt="Banner preview" className="site-banner-preview" onError={e => { e.currentTarget.style.opacity = 0.2; }} />
                  )}
                  {bannerError && <div className="site-alert site-alert-error">{bannerError}</div>}
                  {bannerStatus === 'success' && <div className="site-alert site-alert-success">Banner updated! May take a moment to appear.</div>}
                  <button type="submit" className="site-btn site-btn-primary" disabled={bannerStatus === 'saving'} style={{ justifyContent: 'center' }}>
                    {bannerStatus === 'saving' ? 'Updating…' : <><ImageIcon size={15} /> Update Banner</>}
                  </button>
                </form>
              </div>

              {/* Section: Moderation Tools */}
              <div className="site-card admin-section-card">
                <SectionHeader icon={ShieldAlert} title="Moderation Tools" subtitle="Server blacklist and action logs" />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <Link to="/admin/blacklist" className="admin-tool-link">
                    <Ban size={16} style={{ color: '#f87171' }} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-main)' }}>Blacklist Management</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Block servers and users from using the bot</div>
                    </div>
                    <ChevronRight size={16} style={{ marginLeft: 'auto', color: 'var(--text-muted)' }} />
                  </Link>
                  <Link to="/admin/weblog" className="admin-tool-link">
                    <Activity size={16} style={{ color: '#818cf8' }} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-main)' }}>Action Weblog</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>View all admin actions and system events</div>
                    </div>
                    <ChevronRight size={16} style={{ marginLeft: 'auto', color: 'var(--text-muted)' }} />
                  </Link>
                </div>
              </div>

              {/* Section: Support Tickets */}
              <div className="site-card admin-section-card" style={{ flex: 1 }}>
                <SectionHeader icon={Ticket} title="Recent Support Tickets" subtitle={tickets !== null ? `${tickets.length} open` : 'Loading…'} />

                {ticketsError ? (
                  <p style={{ color: 'var(--danger)', fontSize: 13 }}>{ticketsError}</p>
                ) : tickets === null ? (
                  <p style={{ color: 'var(--text-muted)', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Spinner size={13} /> Loading tickets…
                  </p>
                ) : tickets.length === 0 ? (
                  <div className="admin-empty">No tickets yet — new submissions appear here instantly.</div>
                ) : (
                  <div className="admin-ticket-list">
                    {tickets.map(t => (
                      <div key={t.id} className="admin-ticket-row">
                        <span className="admin-ticket-chip">{t.category || 'General'}</span>
                        <div className="admin-ticket-body">
                          <div className="admin-ticket-subject">{t.subject}</div>
                          <div className="admin-ticket-meta">
                            <span>{t.user_id ? `User ${t.user_id}` : (t.guest || 'Guest')}</span>
                            <span>·</span>
                            <span>{timeAgo(t.ts)}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

            </div>
          </div>

        </div>
      </section>
    </SitePage>
  );
}

export default Admin;