import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Loader } from './Loader';
import { useBotName } from '../BotContext';
import { useDiscordLogin } from '../useDiscordLogin';
import { Menu, X, ArrowRight, Loader2 } from 'lucide-react';

// Update this if you swap the logo later — used in the nav bar and footer.
export const LOGO_URL = '/logo.png';

const NAV_LINKS = [
  { to: '/', label: 'Home' },
  { to: '/#features', label: 'Features' },
  { to: '/commands', label: 'Commands' },
  { to: '/devnews', label: 'Dev News' },
  { to: '/support', label: 'Support' },
  { to: '/status', label: 'Status' },
  { to: '/docs', label: 'Docs' },
];

export function SiteNav({ user }) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const botName = useBotName();
  const brand = (botName || 'Bot').trim();
  const { login, loading } = useDiscordLogin();

  useEffect(() => { setOpen(false); }, [location.pathname]);

  // Only ONE link should ever be "active" at a time:
  //  - '/'            -> active on the home page with no #hash
  //  - '/#features'   -> active on the home page ONLY when that hash is set
  //  - real routes     -> active when the path matches (or is a sub-path)
  const isActive = (to) => {
    const [path, hash] = to.split('#');
    if (hash) return location.pathname === '/' && location.hash === `#${hash}`;
    if (path === '/') return location.pathname === '/' && !location.hash;
    return location.pathname === path || location.pathname.startsWith(`${path}/`);
  };

  return (
    <header className="site-nav">
      <Link to="/" className="site-nav-brand">
        <img src={LOGO_URL} alt={brand} />
        <span>{brand}</span>
      </Link>

      <nav className="site-nav-links">
        {NAV_LINKS.map(l => (
          <Link key={l.to} to={l.to} className={`site-nav-link ${isActive(l.to) ? 'active' : ''}`}>{l.label}</Link>
        ))}
      </nav>

      <div className="site-nav-actions">
        {user ? (
          <Link to="/dashboard" className="site-btn site-btn-primary">
            <span>Dashboard</span>
            <ArrowRight size={15} />
          </Link>
        ) : (
          <button type="button" onClick={login} disabled={loading} className="site-btn site-btn-primary">
            {loading ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
            <span>{loading ? 'Connecting…' : 'Dashboard'}</span>
          </button>
        )}
        {user && (
          <div className="site-user-chip">
            {user.avatar ? <img src={user.avatar} alt={user.username} /> : <span className="fallback">{user.username?.charAt(0) || 'U'}</span>}
            <span>{user.username}</span>
          </div>
        )}
        <button type="button" className="site-mobile-toggle" onClick={() => setOpen(o => !o)} aria-label="Toggle menu">
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      <div className={`site-mobile-menu ${open ? 'open' : ''}`}>
        {NAV_LINKS.map(l => (
          <Link key={l.to} to={l.to} className={`site-nav-link ${isActive(l.to) ? 'active' : ''}`}>{l.label}</Link>
        ))}
      </div>
    </header>
  );
}

export function SiteFooter() {
  const botName = useBotName();
  const brand = (botName || 'Bot').trim();
  return (
    <footer className="site-footer">
      <div className="container site-footer-inner">
        <div className="site-footer-brand">
          <img src={LOGO_URL} alt={brand} />
          <span>{brand}</span>
        </div>
        <div className="site-footer-links">
          <Link to="/#features">Features</Link>
          <Link to="/commands">Commands</Link>
          <Link to="/support">Support</Link>
          <Link to="/status">Status</Link>
          <Link to="/docs">Docs</Link>
        </div>
        <div className="site-footer-copy">&copy; {new Date().getFullYear()} {brand}. All rights reserved.</div>
      </div>
    </footer>
  );
}

export function SitePage({ user, children }) {
  return (
    <div className="site">
      <SiteNav user={user} />
      {children}
      <SiteFooter />
    </div>
  );
}
