import { useEffect, useState } from 'react';
import api from '../api';
import { SitePage } from '../components/SiteLayout';
import {
  ShieldAlert, ImageIcon, Loader2, Ticket, ExternalLink,
  Newspaper, Trash2, Send, Ban, FileText, Settings, Users,
  Activity, ChevronRight, AlertCircle, Megaphone
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

  // Announcement sender
  const [guilds, setGuilds] = useState(null);
  const [annGuild, setAnnGuild] = useState('');
  const [annChannel, setAnnChannel] = useState('');
  const [annTitle, setAnnTitle] = useState('');
  const [annBody, setAnnBody] = useState('');
  const [annColor, setAnnColor] = useState('#8A2BE2');
  const [annPing, setAnnPing] = useState('none');
  const [annStatus, setAnnStatus] = useState('idle');
  const [annError, setAnnError] = useState('');
  const [annSuccess, setAnnSuccess] = useState('');

  // Status message for Owner Status Channel
  const [statusMsg, setStatusMsg] = useState('');
  const [statusMsgActive, setStatusMsgActive] = useState(true);
  const [statusMsgStatus, setStatusMsgStatus] = useState('idle');
  const [statusMsgError, setStatusMsgError] = useState('');
  const [statusMsgSuccess, setStatusMsgSuccess] = useState('');

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
    api.get('/admin/channels')
      .then(res => setGuilds(res.data.guilds || []))
      .catch(() => setGuilds([]));
    api.get('/admin/status-message')
      .then(res => {
        setStatusMsg(res.data?.message || '');
        setStatusMsgActive(res.data?.active ?? true);
      })
      .catch(() => {});
  }, [isAdmin]);

  const loadNews = () => {
    api.get('/public/devnews').then(res => setNews(res.data.entries || [])).catch(() => setNews([]));
  };
  useEffect(() => { if (isAdmin) loadNews(); }, [isAdmin]);

  const handleAnnSubmit = async (e) => {
    e.preventDefault();
    setAnnError(''); setAnnSuccess('');
    if (!annChannel) return setAnnError('Select a channel.');
    if (!annBody.trim()) return setAnnError('Message body is required.');
    setAnnStatus('sending');
    try {
      await api.post('/admin/send-announcement', {
        channel_id: annChannel,
        title: annTitle.trim(),
        body: annBody.trim(),
        color: annColor,
        ping: annPing,
      });
      setAnnSuccess('Announcement sent! ✅');
      setAnnTitle(''); setAnnBody('');
    } catch (err) {
      setAnnError(err.response?.data?.error || 'Failed to send.');
    } finally {
      setAnnStatus('idle');
    }
  };

  const selectedGuildChannels = guilds?.find(g => g.id === annGuild)?.channels || [];

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

  const handleStatusMsgSubmit = async (e) => {
    e.preventDefault();
    setStatusMsgError('');
    setStatusMsgSuccess('');
    setStatusMsgStatus('saving');
    try {
      await api.post('/admin/status-message', { message: statusMsg.trim(), active: statusMsgActive });
      setStatusMsgStatus('success');
      setStatusMsgSuccess('Status notice saved and pushed to Discord status channel!');
      setTimeout(() => setStatusMsgSuccess(''), 4000);
    } catch (err) {
      setStatusMsgStatus('error');
      setStatusMsgError(err.response?.data?.error || 'Failed to update status notice.');
    }
  };

  const handleStatusMsgClear = async () => {
    setStatusMsgError('');
    setStatusMsgSuccess('');
    setStatusMsgStatus('saving');
    try {
      await api.post('/admin/status-message', { message: '', active: false });
      setStatusMsg('');
      setStatusMsgStatus('idle');
      setStatusMsgSuccess('Status notice cleared!');
      setTimeout(() => setStatusMsgSuccess(''), 4000);
    } catch (err) {
      setStatusMsgStatus('error');
      setStatusMsgError(err.response?.data?.error || 'Failed to clear status notice.');
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

            {/* Announcement Sender — full width */}
            <div style={{ gridColumn: '1 / -1' }}>
              <div className="site-card admin-section-card">
                <SectionHeader icon={Megaphone} title="Send Discord Announcement" subtitle="Compose and send an embed to any server channel — uses the existing announcement system" />

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, alignItems: 'start' }}>

                  {/* ── Left: Form ── */}
                  <form onSubmit={handleAnnSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

                    <div className="admin-field-row">
                      <div className="site-field">
                        <label>Server</label>
                        <select value={annGuild} onChange={e => { setAnnGuild(e.target.value); setAnnChannel(''); }}>
                          <option value="">— Select server —</option>
                          {(guilds || []).map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                        </select>
                      </div>
                      <div className="site-field">
                        <label>Channel</label>
                        <select value={annChannel} onChange={e => setAnnChannel(e.target.value)} disabled={!annGuild}>
                          <option value="">— Select channel —</option>
                          {selectedGuildChannels.map(c => <option key={c.id} value={c.id}>#{c.name}</option>)}
                        </select>
                      </div>
                    </div>

                    <div className="site-field">
                      <label>Title (optional)</label>
                      <input type="text" value={annTitle} onChange={e => setAnnTitle(e.target.value)}
                        placeholder="e.g. Music system maintenance" maxLength={256} />
                    </div>

                    <div className="site-field">
                      <label>Message Body</label>
                      <textarea value={annBody} onChange={e => setAnnBody(e.target.value)}
                        placeholder="Your announcement here. Supports Discord markdown." rows={5} maxLength={4000} />
                    </div>

                    <div className="site-field">
                      <label>Ping</label>
                      <select value={annPing} onChange={e => setAnnPing(e.target.value)}>
                        <option value="none">No Ping</option>
                        <option value="everyone">@everyone</option>
                        <option value="here">@here</option>
                      </select>
                    </div>

                    {/* Color picker */}
                    <div className="site-field">
                      <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        Embed Sidebar Color
                        <span style={{ width: 20, height: 20, borderRadius: 5, background: annColor, border: '2px solid rgba(255,255,255,0.2)', display: 'inline-block', boxShadow: `0 0 8px ${annColor}55` }} />
                        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>{annColor}</span>
                      </label>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
                        {['#8A2BE2','#5865F2','#57F287','#FEE75C','#ED4245','#EB459E','#FF7F50','#00BFFF','#FFFFFF','#23272A'].map(c => (
                          <button key={c} type="button" onClick={() => setAnnColor(c)}
                            title={c}
                            style={{
                              width: 28, height: 28, borderRadius: 7, background: c,
                              border: annColor === c ? '2px solid white' : '2px solid rgba(255,255,255,0.1)',
                              cursor: 'pointer', padding: 0,
                              boxShadow: annColor === c ? `0 0 10px ${c}99` : 'none',
                              transition: 'all 0.15s',
                            }} />
                        ))}
                        <input type="color" value={annColor} onChange={e => setAnnColor(e.target.value)}
                          title="Pick custom color"
                          style={{ width: 28, height: 28, borderRadius: 7, border: '2px solid rgba(255,255,255,0.15)', padding: 2, cursor: 'pointer', background: 'rgba(255,255,255,0.05)' }} />
                      </div>
                    </div>

                    {annError && <div className="site-alert site-alert-error" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><AlertCircle size={14} />{annError}</div>}
                    {annSuccess && <div className="site-alert site-alert-success">{annSuccess}</div>}

                    <button type="submit" className="site-btn site-btn-primary" disabled={annStatus === 'sending'} style={{ justifyContent: 'center' }}>
                      {annStatus === 'sending' ? 'Sending…' : <><Send size={15} /><span>Send Announcement</span></>}
                    </button>
                  </form>

                  {/* ── Right: Discord Embed Preview ── */}
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: 10 }}>
                      Live Preview
                    </div>
                    {/* Discord dark background mock */}
                    <div style={{ background: '#313338', borderRadius: 10, padding: '16px 14px', fontFamily: '"gg sans","Noto Sans",sans-serif' }}>
                      {/* Bot row */}
                      <div style={{ display: 'flex', gap: 10, marginBottom: 2 }}>
                        <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'linear-gradient(135deg,#7c5be2,#5865F2)', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>
                          🤖
                        </div>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                            <span style={{ fontWeight: 700, fontSize: 14, color: '#00b0f4' }}>GKR Bot</span>
                            <span style={{ background: '#5865F2', color: 'white', fontSize: 9, fontWeight: 700, padding: '1px 4px', borderRadius: 3, letterSpacing: '0.02em' }}>BOT</span>
                            <span style={{ fontSize: 11, color: '#87888c' }}>Today at {new Date().toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'})}</span>
                          </div>
                          {annPing !== 'none' && (
                            <div style={{ fontSize: 13, color: '#c9cdfb', background: 'rgba(88,101,242,0.15)', display: 'inline-block', padding: '0 4px', borderRadius: 3, marginBottom: 4 }}>
                              {annPing === 'everyone' ? '@everyone' : '@here'}
                            </div>
                          )}
                          {/* Embed */}
                          <div style={{
                            display: 'flex', background: '#2b2d31', borderRadius: '0 4px 4px 4px',
                            borderLeft: `4px solid ${annColor}`, marginTop: 4, overflow: 'hidden',
                            boxShadow: `inset 0 0 0 1px rgba(255,255,255,0.04)`,
                            transition: 'border-color 0.2s',
                          }}>
                            <div style={{ padding: '12px 16px 12px 12px', maxWidth: 420 }}>
                              {(annTitle || !annBody) && (
                                <div style={{ fontWeight: 700, fontSize: 14, color: '#f2f3f5', marginBottom: annBody ? 6 : 0 }}>
                                  📢  {annTitle || 'Announcement Title'}
                                </div>
                              )}
                              <div style={{ fontSize: 13, color: '#dbdee1', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                                {annBody || <span style={{ color: '#87888c', fontStyle: 'italic' }}>Your message will appear here…</span>}
                              </div>
                              <div style={{ marginTop: 8, fontSize: 11, color: '#87888c', display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span style={{ width: 14, height: 14, borderRadius: '50%', background: '#5865F2', display: 'inline-block' }} />
                                GKR Bot — Official Announcement · {new Date().toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, textAlign: 'center' }}>
                      Sidebar color: <code style={{ color: annColor }}>{annColor}</code> — updates live
                    </div>
                  </div>

                </div>
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

              {/* Section: Live Status Notice (Owner Channel) */}
              <div className="site-card admin-section-card">
                <SectionHeader icon={Activity} title="Live Bot Status Notice" subtitle="Shown on the owner status channel embed" />
                <form onSubmit={handleStatusMsgSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div className="site-field">
                    <label>Custom Status Notice / Announcement</label>
                    <textarea
                      value={statusMsg}
                      onChange={e => setStatusMsg(e.target.value)}
                      placeholder="e.g. Bot under scheduled maintenance from 2 PM to 3 PM..."
                      rows={3}
                    />
                  </div>
                  {statusMsgError && <div className="site-alert site-alert-error">{statusMsgError}</div>}
                  {statusMsgSuccess && <div className="site-alert site-alert-success">{statusMsgSuccess}</div>}
                  <div style={{ display: 'flex', gap: 10 }}>
                    <button type="submit" className="site-btn site-btn-primary" disabled={statusMsgStatus === 'saving'} style={{ flex: 1, justifyContent: 'center' }}>
                      {statusMsgStatus === 'saving' ? 'Saving…' : <><Send size={15} /> Save & Push</>}
                    </button>
                    {statusMsg && (
                      <button type="button" onClick={handleStatusMsgClear} className="site-btn site-btn-outline" disabled={statusMsgStatus === 'saving'}>
                        Clear
                      </button>
                    )}
                  </div>
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