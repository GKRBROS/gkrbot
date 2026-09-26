import { useEffect, useState } from 'react';
import api from '../api';
import { SitePage } from '../components/SiteLayout';
import { ShieldAlert, ImageIcon, Loader2, Ticket, ExternalLink, Newspaper, Trash2, Send } from 'lucide-react';
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

export function Admin({ user }) {
  const [checking, setChecking] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  const [bannerUrl, setBannerUrl] = useState('');
  const [bannerStatus, setBannerStatus] = useState('idle'); // idle | saving | success | error
  const [bannerError, setBannerError] = useState('');

  const [tickets, setTickets] = useState(null);
  const [ticketsError, setTicketsError] = useState('');

  const [news, setNews] = useState(null);
  const [newsTitle, setNewsTitle] = useState('');
  const [newsBody, setNewsBody] = useState('');
  const [newsMedia, setNewsMedia] = useState('');
  const [newsLink, setNewsLink] = useState('');
  const [newsError, setNewsError] = useState('');
  const [newsStatus, setNewsStatus] = useState('idle'); // idle | saving

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
    if (newsTitle.trim().length < 3) return setNewsError('Please add a title (at least 3 characters).');
    setNewsStatus('saving');
    try {
      await api.post('/admin/devnews', {
        title: newsTitle.trim(), body: newsBody.trim(), media_url: newsMedia.trim(), link_url: newsLink.trim(),
      });
      setNewsTitle(''); setNewsBody(''); setNewsMedia(''); setNewsLink('');
      loadNews();
    } catch (err) {
      setNewsError(err.response?.data?.error || 'Failed to publish that update.');
    } finally {
      setNewsStatus('idle');
    }
  };

  const handleNewsDelete = async (id) => {
    try {
      await api.delete(`/admin/devnews/${id}`);
      setNews(prev => (prev || []).filter(n => n.id !== id));
    } catch (err) {
      setNewsError(err.response?.data?.error || 'Failed to delete that entry.');
    }
  };

  const handleBannerSubmit = async (e) => {
    e.preventDefault();
    setBannerError('');
    if (!/^https?:\/\//i.test(bannerUrl.trim())) {
      setBannerError('Please enter a direct link to an image.');
      return;
    }
    setBannerStatus('saving');
    try {
      await api.post('/admin/bot-banner', { url: bannerUrl.trim() });
      setBannerStatus('success');
    } catch (err) {
      setBannerStatus('error');
      setBannerError(err.response?.data?.error || 'Failed to update the banner.');
    }
  };

  if (checking) {
    return <Loader label="Checking access…" />;
  }

  if (!isAdmin) {
    return (
      <SitePage user={user}>
        <section className="site-section" style={{ paddingTop: 90, textAlign: 'center' }}>
          <div className="container" style={{ maxWidth: 460 }}>
            <ShieldAlert size={40} color="var(--danger)" style={{ marginBottom: 14 }} />
            <h2 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8 }}>Access Denied</h2>
            <p style={{ color: 'var(--text-sub)' }}>
              {user
                ? "This page is restricted to the bot's owner/admins."
                : 'Please sign in with an authorized account to view this page.'}
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
          <div className="admin-head">
            <div className="site-section-head" style={{ marginBottom: 0 }}>
              <div className="site-eyebrow">Owner only</div>
              <h2>Admin Panel</h2>
            </div>
            <div className="admin-stats">
              <div className="admin-stat">
                <b>{tickets === null ? '—' : tickets.length}</b>
                <span>Open tickets</span>
              </div>
              <div className="admin-stat">
                <b>{news === null ? '—' : news.length}</b>
                <span>Dev news posts</span>
              </div>
              <div className="admin-stat">
                <b>{news && news[0] ? timeAgo(news[0].created_at) : '—'}</b>
                <span>Last update</span>
              </div>
            </div>
          </div>

          <div className="admin-bento">
            {/* Primary column: composing news is the main reason to be on this page */}
            <div className="admin-col admin-col--news">
              <div className="site-card admin-card admin-card--news">
                <div className="admin-card-top">
                  <div className="admin-card-top-left">
                    <div className="site-card-icon"><Newspaper size={20} /></div>
                    <h3 style={{ margin: 0 }}>Post a Dev News Update</h3>
                  </div>
                  {news !== null && <span className="admin-card-count">{news.length} published</span>}
                </div>
                <p style={{ marginBottom: 14, color: 'var(--text-sub)' }}>Shows up on the public Dev News page immediately.</p>
                <form onSubmit={handleNewsSubmit}>
                  <div className="site-field">
                    <label>Title</label>
                    <input type="text" value={newsTitle} onChange={e => setNewsTitle(e.target.value)} placeholder="New: Animated welcome cards" maxLength={100} />
                  </div>
                  <div className="site-field">
                    <label>Description</label>
                    <textarea value={newsBody} onChange={e => setNewsBody(e.target.value)} placeholder="What changed and why it matters..." maxLength={1000} />
                  </div>
                  <div className="admin-field-row">
                    <div className="site-field">
                      <label>Image or GIF URL (optional)</label>
                      <input type="text" value={newsMedia} onChange={e => setNewsMedia(e.target.value)} placeholder="https://example.com/preview.gif" />
                    </div>
                    <div className="site-field">
                      <label>Link URL (optional)</label>
                      <input type="text" value={newsLink} onChange={e => setNewsLink(e.target.value)} placeholder="https://example.com/docs/feature" />
                    </div>
                  </div>
                  {newsMedia.trim() && /^https?:\/\//i.test(newsMedia.trim()) && (
                    <img src={newsMedia.trim()} alt="Preview" className="site-banner-preview" style={{ aspectRatio: '16 / 9' }} onError={(e) => { e.currentTarget.style.opacity = 0.2; }} />
                  )}
                  {newsError && <div className="site-alert site-alert-error" style={{ marginTop: 14 }}>{newsError}</div>}
                  <button type="submit" className="site-btn site-btn-primary" disabled={newsStatus === 'saving'} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}>
                    {newsStatus === 'saving' ? 'Publishing…' : (<><Send size={15} /> <span>Publish Update</span></>)}
                  </button>
                </form>

                {news && news.length > 0 && (
                  <div className="admin-news-feed">
                    {news.map(n => (
                      <div key={n.id} className="admin-news-item">
                        {n.media_url ? (
                          <img src={n.media_url} alt="" className="admin-news-thumb" onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }} />
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
                )}
              </div>
            </div>

            {/* Side column: rare banner task on top, live ticket feed filling the rest */}
            <div className="admin-col admin-col--side">
              <div className="site-card admin-card admin-card--banner">
                <div className="admin-card-top">
                  <div className="admin-card-top-left">
                    <div className="site-card-icon"><ImageIcon size={20} /></div>
                    <h3 style={{ margin: 0 }}>Change Bot Banner</h3>
                  </div>
                </div>
                <div className="site-admin-warning" style={{ marginTop: 10 }}>
                  This changes the bot's <strong>global</strong> profile banner (Discord does not support a
                  different banner per server). Discord also limits how often it can change —
                  if this fails right after a recent change, wait ~10 minutes and try again.
                </div>
                <form onSubmit={handleBannerSubmit}>
                  <div className="site-field">
                    <label>Image URL</label>
                    <input
                      type="text" value={bannerUrl} onChange={e => { setBannerUrl(e.target.value); setBannerStatus('idle'); }}
                      placeholder="https://example.com/banner.png"
                    />
                  </div>
                  {bannerUrl.trim() && /^https?:\/\//i.test(bannerUrl.trim()) && (
                    <img src={bannerUrl.trim()} alt="Banner preview" className="site-banner-preview" onError={(e) => { e.currentTarget.style.opacity = 0.2; }} />
                  )}
                  {bannerError && <div className="site-alert site-alert-error" style={{ marginTop: 14 }}>{bannerError}</div>}
                  {bannerStatus === 'success' && <div className="site-alert site-alert-success" style={{ marginTop: 14 }}>Banner updated! It may take a minute to appear on Discord.</div>}
                  <button type="submit" className="site-btn site-btn-primary" disabled={bannerStatus === 'saving'} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}>
                    {bannerStatus === 'saving' ? 'Updating…' : 'Update Banner'}
                  </button>
                </form>
              </div>

              <div className="site-card admin-card admin-card--tickets" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div className="admin-card-top">
                  <div className="admin-card-top-left">
                    <div className="site-card-icon"><Ticket size={20} /></div>
                    <h3 style={{ margin: 0 }}>Recent Website Tickets</h3>
                  </div>
                  {tickets !== null && <span className="admin-card-count">{tickets.length}</span>}
                </div>
                {ticketsError ? (
                  <p style={{ color: 'var(--danger)', marginTop: 10 }}>{ticketsError}</p>
                ) : tickets === null ? (
                  <p style={{ color: 'var(--text-muted)', marginTop: 10 }}><Spinner size={13} /> Loading tickets…</p>
                ) : tickets.length === 0 ? (
                  <div className="admin-empty">No tickets yet — new submissions will show up here instantly.</div>
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

export default Admin; import { useEffect, useState } from 'react';
import api from '../api';
import { SitePage } from '../components/SiteLayout';
import { ShieldAlert, ImageIcon, Loader2, Ticket, ExternalLink, Newspaper, Trash2, Send } from 'lucide-react';
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

export function Admin({ user }) {
  const [checking, setChecking] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  const [bannerUrl, setBannerUrl] = useState('');
  const [bannerStatus, setBannerStatus] = useState('idle'); // idle | saving | success | error
  const [bannerError, setBannerError] = useState('');

  const [tickets, setTickets] = useState(null);
  const [ticketsError, setTicketsError] = useState('');

  const [news, setNews] = useState(null);
  const [newsTitle, setNewsTitle] = useState('');
  const [newsBody, setNewsBody] = useState('');
  const [newsMedia, setNewsMedia] = useState('');
  const [newsLink, setNewsLink] = useState('');
  const [newsError, setNewsError] = useState('');
  const [newsStatus, setNewsStatus] = useState('idle'); // idle | saving

  useEffect(() => {
    api.get('/admin/whoami')
      .then(res => setIsAdmin(!!res.data?.is_admin))
      .catch(() => setIsAdmin(false))
      .finally(() => setChecking(false));
  }, []);

  // Poll only the tickets list, on its own timer, so a new website ticket
  // shows up here without the admin ever refreshing the page. Every other
  // section (banner form, dev news) is left untouched by this.
  const TICKETS_POLL_MS = 15000;
  useEffect(() => {
    if (!isAdmin) return undefined;
    let cancelled = false;

    const loadTickets = () => {
      api.get('/admin/tickets')
        .then(res => {
          if (cancelled) return;
          setTickets(res.data.tickets || []);
          setTicketsError('');
        })
        .catch(err => {
          if (cancelled) return;
          // Keep showing the last known list on a transient failure instead
          // of flashing an empty state every 15 seconds.
          setTicketsError(err.response?.data?.error || 'Could not load tickets.');
        });
    };

    loadTickets();
    const interval = setInterval(loadTickets, TICKETS_POLL_MS);
    return () => { cancelled = true; clearInterval(interval); };
  }, [isAdmin]);

  const loadNews = () => {
    api.get('/public/devnews').then(res => setNews(res.data.entries || [])).catch(() => setNews([]));
  };
  useEffect(() => { if (isAdmin) loadNews(); }, [isAdmin]);

  const handleNewsSubmit = async (e) => {
    e.preventDefault();
    setNewsError('');
    if (newsTitle.trim().length < 3) return setNewsError('Please add a title (at least 3 characters).');
    setNewsStatus('saving');
    try {
      await api.post('/admin/devnews', {
        title: newsTitle.trim(), body: newsBody.trim(), media_url: newsMedia.trim(), link_url: newsLink.trim(),
      });
      setNewsTitle(''); setNewsBody(''); setNewsMedia(''); setNewsLink('');
      loadNews();
    } catch (err) {
      setNewsError(err.response?.data?.error || 'Failed to publish that update.');
    } finally {
      setNewsStatus('idle');
    }
  };

  const handleNewsDelete = async (id) => {
    try {
      await api.delete(`/admin/devnews/${id}`);
      setNews(prev => (prev || []).filter(n => n.id !== id));
    } catch (err) {
      setNewsError(err.response?.data?.error || 'Failed to delete that entry.');
    }
  };

  const handleBannerSubmit = async (e) => {
    e.preventDefault();
    setBannerError('');
    if (!/^https?:\/\//i.test(bannerUrl.trim())) {
      setBannerError('Please enter a direct link to an image.');
      return;
    }
    setBannerStatus('saving');
    try {
      await api.post('/admin/bot-banner', { url: bannerUrl.trim() });
      setBannerStatus('success');
    } catch (err) {
      setBannerStatus('error');
      setBannerError(err.response?.data?.error || 'Failed to update the banner.');
    }
  };

  if (checking) {
    return <Loader label="Checking access…" />;
  }

  if (!isAdmin) {
    return (
      <SitePage user={user}>
        <section className="site-section" style={{ paddingTop: 90, textAlign: 'center' }}>
          <div className="container" style={{ maxWidth: 460 }}>
            <ShieldAlert size={40} color="var(--danger)" style={{ marginBottom: 14 }} />
            <h2 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8 }}>Access Denied</h2>
            <p style={{ color: 'var(--text-sub)' }}>
              {user
                ? "This page is restricted to the bot's owner/admins."
                : 'Please sign in with an authorized account to view this page.'}
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
          <div className="admin-head">
            <div className="site-section-head" style={{ marginBottom: 0 }}>
              <div className="site-eyebrow">Owner only</div>
              <h2>Admin Panel</h2>
            </div>
            <div className="admin-stats">
              <div className="admin-stat">
                <b>{tickets === null ? '—' : tickets.length}</b>
                <span>Open tickets</span>
              </div>
              <div className="admin-stat">
                <b>{news === null ? '—' : news.length}</b>
                <span>Dev news posts</span>
              </div>
              <div className="admin-stat">
                <b>{news && news[0] ? timeAgo(news[0].created_at) : '—'}</b>
                <span>Last update</span>
              </div>
            </div>
          </div>

          <div className="admin-bento">
            {/* Primary column: composing news is the main reason to be on this page */}
            <div className="admin-col admin-col--news">
              <div className="site-card admin-card admin-card--news">
                <div className="admin-card-top">
                  <div className="admin-card-top-left">
                    <div className="site-card-icon"><Newspaper size={20} /></div>
                    <h3 style={{ margin: 0 }}>Post a Dev News Update</h3>
                  </div>
                  {news !== null && <span className="admin-card-count">{news.length} published</span>}
                </div>
                <p style={{ marginBottom: 14, color: 'var(--text-sub)' }}>Shows up on the public Dev News page immediately.</p>
                <form onSubmit={handleNewsSubmit}>
                  <div className="site-field">
                    <label>Title</label>
                    <input type="text" value={newsTitle} onChange={e => setNewsTitle(e.target.value)} placeholder="New: Animated welcome cards" maxLength={100} />
                  </div>
                  <div className="site-field">
                    <label>Description</label>
                    <textarea value={newsBody} onChange={e => setNewsBody(e.target.value)} placeholder="What changed and why it matters..." maxLength={1000} />
                  </div>
                  <div className="admin-field-row">
                    <div className="site-field">
                      <label>Image or GIF URL (optional)</label>
                      <input type="text" value={newsMedia} onChange={e => setNewsMedia(e.target.value)} placeholder="https://example.com/preview.gif" />
                    </div>
                    <div className="site-field">
                      <label>Link URL (optional)</label>
                      <input type="text" value={newsLink} onChange={e => setNewsLink(e.target.value)} placeholder="https://example.com/docs/feature" />
                    </div>
                  </div>
                  {newsMedia.trim() && /^https?:\/\//i.test(newsMedia.trim()) && (
                    <img src={newsMedia.trim()} alt="Preview" className="site-banner-preview" style={{ aspectRatio: '16 / 9' }} onError={(e) => { e.currentTarget.style.opacity = 0.2; }} />
                  )}
                  {newsError && <div className="site-alert site-alert-error" style={{ marginTop: 14 }}>{newsError}</div>}
                  <button type="submit" className="site-btn site-btn-primary" disabled={newsStatus === 'saving'} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}>
                    {newsStatus === 'saving' ? 'Publishing…' : (<><Send size={15} /> <span>Publish Update</span></>)}
                  </button>
                </form>

                {news && news.length > 0 && (
                  <div className="admin-news-feed">
                    {news.map(n => (
                      <div key={n.id} className="admin-news-item">
                        {n.media_url ? (
                          <img src={n.media_url} alt="" className="admin-news-thumb" onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }} />
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
                )}
              </div>
            </div>

            {/* Side column: rare banner task on top, live ticket feed filling the rest */}
            <div className="admin-col admin-col--side">
              <div className="site-card admin-card admin-card--banner">
                <div className="admin-card-top">
                  <div className="admin-card-top-left">
                    <div className="site-card-icon"><ImageIcon size={20} /></div>
                    <h3 style={{ margin: 0 }}>Change Bot Banner</h3>
                  </div>
                </div>
                <div className="site-admin-warning" style={{ marginTop: 10 }}>
                  This changes the bot's <strong>global</strong> profile banner (Discord does not support a
                  different banner per server). Discord also limits how often it can change —
                  if this fails right after a recent change, wait ~10 minutes and try again.
                </div>
                <form onSubmit={handleBannerSubmit}>
                  <div className="site-field">
                    <label>Image URL</label>
                    <input
                      type="text" value={bannerUrl} onChange={e => { setBannerUrl(e.target.value); setBannerStatus('idle'); }}
                      placeholder="https://example.com/banner.png"
                    />
                  </div>
                  {bannerUrl.trim() && /^https?:\/\//i.test(bannerUrl.trim()) && (
                    <img src={bannerUrl.trim()} alt="Banner preview" className="site-banner-preview" onError={(e) => { e.currentTarget.style.opacity = 0.2; }} />
                  )}
                  {bannerError && <div className="site-alert site-alert-error" style={{ marginTop: 14 }}>{bannerError}</div>}
                  {bannerStatus === 'success' && <div className="site-alert site-alert-success" style={{ marginTop: 14 }}>Banner updated! It may take a minute to appear on Discord.</div>}
                  <button type="submit" className="site-btn site-btn-primary" disabled={bannerStatus === 'saving'} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}>
                    {bannerStatus === 'saving' ? 'Updating…' : 'Update Banner'}
                  </button>
                </form>
              </div>

              <div className="site-card admin-card admin-card--tickets" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div className="admin-card-top">
                  <div className="admin-card-top-left">
                    <div className="site-card-icon"><Ticket size={20} /></div>
                    <h3 style={{ margin: 0 }}>Recent Website Tickets</h3>
                  </div>
                  {tickets !== null && <span className="admin-card-count">{tickets.length}</span>}
                </div>
                {ticketsError ? (
                  <p style={{ color: 'var(--danger)', marginTop: 10 }}>{ticketsError}</p>
                ) : tickets === null ? (
                  <p style={{ color: 'var(--text-muted)', marginTop: 10 }}><Spinner size={13} /> Loading tickets…</p>
                ) : tickets.length === 0 ? (
                  <div className="admin-empty">No tickets yet — new submissions will show up here instantly.</div>
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