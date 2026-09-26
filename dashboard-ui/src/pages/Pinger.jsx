import { useBotName } from '../BotContext';
import { SitePage } from '../components/SiteLayout';
import { Bell, Hash, Users, MessageSquareText, Timer, RefreshCcw } from 'lucide-react';

const COMMANDS = [
  { name: 'pinger channel', desc: 'Set the channel where the repeating ping is posted.' },
  { name: 'pinger addrole', desc: 'Add a role to the ping rotation (up to 10 roles).' },
  { name: 'pinger removerole', desc: 'Remove a role from the rotation.' },
  { name: 'pinger text', desc: 'Set an optional message shown next to the mention. Leave blank to clear it.' },
  { name: 'pinger interval', desc: 'How often to re-ping, in seconds (minimum 30).' },
  { name: 'pinger start', desc: 'Turn the repeating ping on.' },
  { name: 'pinger stop', desc: 'Turn it off and remove the live ping message.' },
  { name: 'pinger status', desc: 'Show the current channel, roles, interval and text.' },
];

export function Pinger({ user }) {
  const botName = useBotName();
  const brand = (botName || 'Bot').trim();

  return (
    <SitePage user={user}>
      <section className="site-hero" style={{ padding: '72px 0 40px' }}>
        <div className="container">
          <span className="site-hero-badge"><span className="dot" /> Always-on role reminders</span>
          <h1 style={{ marginTop: 18 }}>Pinger</h1>
          <p className="lead">
            {brand} keeps a single, always-fresh ping alive in any channel — no pile of old
            mentions cluttering the chat. Every cycle, the last ping is deleted and a new one
            takes its place.
          </p>
        </div>
      </section>

      <section className="site-section" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="site-grid">
            <div className="site-card">
              <div className="site-card-icon"><Hash size={20} /></div>
              <h3>One channel, always clean</h3>
              <p>Pick the channel once — old pings are deleted automatically before the new one is sent.</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><Users size={20} /></div>
              <h3>Multiple roles at once</h3>
              <p>Mention up to 10 roles together in a single rotating ping.</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><MessageSquareText size={20} /></div>
              <h3>Optional custom text</h3>
              <p>Attach a message alongside the mentions — it gets deleted and reposted with every cycle too.</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><Timer size={20} /></div>
              <h3>Your own interval</h3>
              <p>Choose how often it re-pings, from every 30 seconds up to once a day.</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><RefreshCcw size={20} /></div>
              <h3>Start / stop anytime</h3>
              <p>Toggle it on or off with a single command — stopping also removes the live ping.</p>
            </div>
            <div className="site-card">
              <div className="site-card-icon"><Bell size={20} /></div>
              <h3>Manage Server only</h3>
              <p>Every Pinger command requires the Manage Server permission, so members can't touch it.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="site-section">
        <div className="container">
          <div className="site-section-head">
            <div className="site-eyebrow">Setup</div>
            <h2>Commands</h2>
            <p>All commands live under <code>/pinger</code> and require Manage Server permission.</p>
          </div>
          <div className="site-cmd-list">
            {COMMANDS.map((c) => (
              <div key={c.name} className="site-cmd-row">
                <span className="site-cmd-name">/{c.name}</span>
                <span className="site-cmd-desc">{c.desc}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </SitePage>
  );
}

export default Pinger;
