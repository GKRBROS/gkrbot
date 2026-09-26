import { useEffect, useMemo, useState } from 'react';
import api from '../api';
import { SitePage } from '../components/SiteLayout';
import { Search, Terminal } from 'lucide-react';

export function Commands({ user }) {
  const [commands, setCommands] = useState(null); // null = loading, [] = loaded empty
  const [q, setQ] = useState('');
  const [cat, setCat] = useState('all');

  useEffect(() => {
    api.get('/public/commands').then(res => setCommands(res.data.commands || [])).catch(() => setCommands([]));
  }, []);

  const categories = useMemo(() => {
    if (!commands) return [];
    return Array.from(new Set(commands.map(c => c.category))).sort();
  }, [commands]);

  const filtered = useMemo(() => {
    if (!commands) return [];
    const query = q.trim().toLowerCase();
    return commands.filter(c => {
      if (cat !== 'all' && c.category !== cat) return false;
      if (!query) return true;
      return c.name.toLowerCase().includes(query) || (c.description || '').toLowerCase().includes(query);
    });
  }, [commands, q, cat]);

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64 }}>
        <div className="container">
          <div className="site-section-head">
            <div className="site-eyebrow">Slash commands</div>
            <h2>Every command, live from the bot</h2>
            <p>This list is pulled directly from the bot right now — if it's here, it works.</p>
          </div>

          <div className="site-search">
            <Search size={16} color="var(--text-muted)" />
            <input
              type="text"
              placeholder="Search commands..."
              value={q}
              onChange={e => setQ(e.target.value)}
              aria-label="Search commands"
            />
          </div>

          {categories.length > 0 && (
            <div className="site-cmd-tabs">
              <button type="button" className={`site-cmd-tab ${cat === 'all' ? 'active' : ''}`} onClick={() => setCat('all')}>All</button>
              {categories.map(c => (
                <button key={c} type="button" className={`site-cmd-tab ${cat === c ? 'active' : ''}`} onClick={() => setCat(c)}>{c}</button>
              ))}
            </div>
          )}

          {commands === null ? (
            <div className="site-empty">Loading commands…</div>
          ) : filtered.length === 0 ? (
            <div className="site-empty">
              <Terminal size={22} style={{ marginBottom: 10, opacity: 0.5 }} />
              <div>No commands match your search.</div>
            </div>
          ) : (
            <div className="site-cmd-list">
              {filtered.map(c => (
                <div key={c.name} className="site-cmd-row">
                  <span className="site-cmd-name">/{c.name}</span>
                  <span className="site-cmd-desc">{c.description || 'No description provided.'}</span>
                  <span className="site-cmd-cat">{c.category}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </SitePage>
  );
}

export default Commands;