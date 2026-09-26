import { useState } from 'react';
import { useBotName } from '../BotContext';
import { SitePage } from '../components/SiteLayout';

const SECTIONS = [
  { id: 'getting-started', label: 'Getting Started' },
  { id: 'dashboard', label: 'Dashboard Basics' },
  { id: 'welcome-cards', label: 'Welcome Cards' },
  { id: 'tickets', label: 'Ticket System' },
  { id: 'security', label: 'Security & Moderation' },
  { id: 'sync', label: 'Server Sync' },
  { id: 'permissions', label: 'Permissions' },
  { id: 'faq', label: 'FAQ' },
];

export function Docs({ user }) {
  const botName = useBotName();
  const brand = (botName || 'Bot').trim();
  const [active, setActive] = useState('getting-started');

  const scrollTo = (id) => {
    setActive(id);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64 }}>
        <div className="container site-docs">
          <nav className="site-docs-nav">
            {SECTIONS.map(s => (
              <button
                key={s.id}
                type="button"
                onClick={() => scrollTo(s.id)}
                className={`site-docs-link ${active === s.id ? 'active' : ''}`}
                style={{ background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer', font: 'inherit' }}
              >
                {s.label}
              </button>
            ))}
          </nav>

          <div className="site-docs-content">
            <h2 id="getting-started">Getting Started</h2>
            <p>
              Invite {brand} to your server using the &quot;Add to Discord&quot; button on the home page, then head to
              the <a href="/dashboard" style={{ color: 'var(--accent)' }}>Dashboard</a> and sign in with your Discord
              account. You&apos;ll need <strong>Administrator</strong> or <strong>Manage Server</strong> permissions
              to configure a server.
            </p>
            <p>Once signed in, pick your server from the server list and every feature is configured from there — no commands required for setup.</p>

            <h2 id="dashboard">Dashboard Basics</h2>
            <p>The dashboard is organized by feature: Welcome &amp; Leave, Tickets, Security, Moderation, and so on. Each page saves instantly, and most changes take effect immediately without restarting the bot.</p>
            <p>Use the <strong>Auto-Sync</strong> toggle in the top bar to mirror your configuration changes to every other server the bot manages for you — handy if you run several communities with the same setup.</p>

            <h2 id="welcome-cards">Welcome Cards</h2>
            <p>Choose from multiple card styles (Legacy Neon, Minimalist Glass, Ticket Pass, Cinematic Poster), toggle which elements are drawn (avatar, text, server icon), and set a custom background image or animated GIF.</p>
            <p>Available placeholders for your welcome and leave messages:</p>
            <pre>{'{user}      -> mentions the member (@Name)\n{username}  -> the member\'s display name\n{server}    -> your server\'s name\n{count}     -> the new member count'}</pre>

            <h2 id="tickets">Ticket System</h2>
            <p>Create ticket categories from the dashboard, each with its own support role and welcome message. Members open tickets from a panel message you post with a single click, and staff can claim, close, and export transcripts.</p>

            <h2 id="security">Security &amp; Moderation</h2>
            <p>Anti-raid and anti-nuke protection watch for mass-join waves, mass channel/role deletion, and other abuse patterns, automatically locking down and notifying your staff. Moderation includes mutes, warnings, staff role permissions, and full mod-action logs.</p>

            <h2 id="sync">Server Sync</h2>
            <p>Server Sync copies configuration (welcome cards, tickets, security rules, and more) from one server to another, or keeps them mirrored automatically with Auto-Sync. Useful for bot networks or multi-community setups.</p>

            <h2 id="permissions">Permissions</h2>
            <ul>
              <li><strong>Dashboard access</strong> requires Administrator or Manage Server on the target Discord server.</li>
              <li><strong>The bot itself</strong> needs Administrator (or the specific permissions each feature uses) to function correctly — grant this when inviting it.</li>
              <li>Ticket staff and moderation roles are configured per-server from the dashboard, independent of Discord's own role permissions.</li>
            </ul>

            <h2 id="faq">FAQ</h2>
            <p><strong>The dashboard shows &quot;server offline&quot; — what do I do?</strong> Make sure the bot is running and online in your server; the dashboard reads live data from the bot process.</p>
            <p><strong>Can I use this on multiple servers?</strong> Yes — invite the bot to as many servers as you like and configure each independently, or use Server Sync to mirror settings between them.</p>
            <p><strong>Something's broken or missing.</strong> Please reach out on our <a href="/support" style={{ color: 'var(--accent)' }}>Support page</a> and we'll take a look.</p>
          </div>
        </div>
      </section>
    </SitePage>
  );
}

export default Docs;
