import { useEffect, useState } from 'react';
import api from '../api';
import { useBotName } from '../BotContext';
import { SitePage } from '../components/SiteLayout';
import { Sparkles, ExternalLink, Newspaper } from 'lucide-react';

function formatDate(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

function isVideoUrl(url) {
  return /\.(mp4|webm)$/i.test(url || '');
}

export function DevNews({ user }) {
  const botName = useBotName();
  const brand = (botName || 'Bot').trim();
  const [entries, setEntries] = useState(null); // null = loading

  useEffect(() => {
    api.get('/public/devnews').then(res => setEntries(res.data.entries || [])).catch(() => setEntries([]));
  }, []);

  return (
    <SitePage user={user}>
      <section className="site-hero" style={{ padding: '72px 0 40px' }}>
        <div className="container">
          <span className="site-hero-badge"><span className="dot" /> Changelog</span>
          <h1 style={{ marginTop: 18 }}>Dev News</h1>
          <p className="lead">New features, fixes, and everything else we've shipped for {brand}, as it happens.</p>
        </div>
      </section>

      <section className="site-section" style={{ paddingTop: 0 }}>
        <div className="container" style={{ maxWidth: 760 }}>
          {entries === null ? (
            <div className="site-empty">Loading updates…</div>
          ) : entries.length === 0 ? (
            <div className="site-empty">
              <Newspaper size={22} style={{ marginBottom: 10, opacity: 0.5 }} />
              <div>No updates posted yet — check back soon.</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              {entries.map((e) => (
                <article key={e.id} className="site-card" style={{ padding: 0, overflow: 'hidden' }}>
                  {e.media_url && (
                    isVideoUrl(e.media_url) ? (
                      <video src={e.media_url} autoPlay loop muted playsInline style={{ width: '100%', maxHeight: 360, objectFit: 'cover', display: 'block' }} />
                    ) : (
                      <img src={e.media_url} alt={e.title} style={{ width: '100%', maxHeight: 360, objectFit: 'cover', display: 'block' }} loading="lazy" />
                    )
                  )}
                  <div style={{ padding: 22 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <Sparkles size={14} color="var(--accent)" />
                      <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>{formatDate(e.created_at)}</span>
                    </div>
                    <h3 style={{ fontSize: 19, fontWeight: 800, marginBottom: 8 }}>{e.title}</h3>
                    {e.body && <p style={{ color: 'var(--text-sub)', fontSize: 14.5, lineHeight: 1.6, whiteSpace: 'pre-line', marginBottom: e.link_url ? 14 : 0 }}>{e.body}</p>}
                    {e.link_url && (
                      <a href={e.link_url} target="_blank" rel="noreferrer" className="site-btn site-btn-ghost" style={{ display: 'inline-flex' }}>
                        <span>Learn more</span> <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
    </SitePage>
  );
}

export default DevNews;
