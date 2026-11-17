import { useBotName } from '../BotContext';
import { SitePage } from '../components/SiteLayout';
import { ExternalLink, ShieldCheck, Lock, EyeOff, Server, Trash2 } from 'lucide-react';

export function Privacy({ user }) {
  const botName = useBotName();
  const brand = (botName || 'GKR Bot').trim();

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64, paddingBottom: 80 }}>
        <div className="container" style={{ maxWidth: 860, margin: '0 auto' }}>
          
          <div style={{ marginBottom: 32 }}>
            <div className="site-eyebrow" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <ShieldCheck size={14} /> Legal &amp; Transparency
            </div>
            <h1 style={{ fontSize: 36, fontWeight: 800, marginTop: 8, marginBottom: 12 }}>Privacy Policy</h1>
            <p style={{ color: 'var(--text-sub)', fontSize: 15 }}>
              Effective Date: November 17, 2026 • Official repository mirror:{' '}
              <a
                href="https://github.com/GKRBROS/gkrbot/blob/main/Privacy%20Policy"
                target="_blank"
                rel="noreferrer"
                style={{ color: 'var(--accent)', textDecoration: 'underline', display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                GitHub Source <ExternalLink size={13} />
              </a>
            </p>
          </div>

          <div className="site-card" style={{ padding: '32px 28px', lineHeight: 1.7, fontSize: 15 }}>
            <h2 style={{ fontSize: 20, fontWeight: 700, marginTop: 0, marginBottom: 12, color: 'var(--text)' }}>
              1. Information We Collect
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 16 }}>
              {brand} (&quot;the Bot&quot;) only collects the minimum data necessary to provide moderation, auto-defense, leveling progression, and utility features:
            </p>
            <ul style={{ color: 'var(--text-sub)', paddingLeft: 24, marginBottom: 24 }}>
              <li><strong>Discord Identifiers:</strong> Guild IDs, User IDs, and Channel IDs to associate server settings, autoroles, and ticket configurations.</li>
              <li><strong>Leveling Progression Data:</strong> User XP counts, current level rank, and role reward associations.</li>
              <li><strong>Volatile Telemetry:</strong> Anonymized operational metrics (command counts, bot latency, uptime) used exclusively for performance monitoring.</li>
            </ul>

            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: 'var(--text)' }}>
              2. Data We DO NOT Collect or Store
            </h2>
            <ul style={{ color: 'var(--text-sub)', paddingLeft: 24, marginBottom: 24 }}>
              <li><strong>Chat Messages:</strong> Messages are processed transiently in volatile memory for spam filtering, phishing detection, and XP calculation. Message text is never stored in persistent databases.</li>
              <li><strong>Personal Information:</strong> We never collect real names, physical addresses, email addresses, phone numbers, or passwords.</li>
              <li><strong>No Data Brokering:</strong> We never sell, rent, or trade any user or guild information to third parties or data brokers.</li>
            </ul>

            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: 'var(--text)' }}>
              3. Data Storage &amp; Security
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 24 }}>
              All configuration databases (SQLite) are stored in secure environments with strictly limited internal access. We implement standard encryption and access barriers to safeguard your settings.
            </p>

            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: 'var(--text)' }}>
              4. User Rights &amp; Data Deletion
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 16 }}>
              Server administrators and members retain full ownership of their data:
            </p>
            <ul style={{ color: 'var(--text-sub)', paddingLeft: 24, marginBottom: 24 }}>
              <li><strong>Server Removal:</strong> Removing {brand} from a Discord server ceases all data collection for that guild.</li>
              <li><strong>Right to Deletion:</strong> You may request permanent deletion of all associated data at any time by contacting our support team or opening a ticket on our official Discord server.</li>
            </ul>

            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: 'var(--text)' }}>
              5. Third-Party Integrations
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 0 }}>
              Optional AI chat features interface securely with upstream providers (such as Groq or Google Gemini) solely to produce text responses. No user message data is stored or repurposed for external machine learning training.
            </p>
          </div>

          <div style={{ marginTop: 24, textAlign: 'center' }}>
            <a
              href="https://github.com/GKRBROS/gkrbot/blob/main/Privacy%20Policy"
              target="_blank"
              rel="noreferrer"
              className="site-btn site-btn-ghost"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <span>View Privacy Policy on GitHub</span> <ExternalLink size={14} />
            </a>
          </div>

        </div>
      </section>
    </SitePage>
  );
}

export default Privacy;
