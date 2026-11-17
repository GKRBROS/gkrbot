import { useBotName } from '../BotContext';
import { SitePage } from '../components/SiteLayout';
import { ExternalLink, FileText, CheckCircle2, AlertTriangle, ShieldAlert } from 'lucide-react';

export function Terms({ user }) {
  const botName = useBotName();
  const brand = (botName || 'GKR Bot').trim();

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64, paddingBottom: 80 }}>
        <div className="container" style={{ maxWidth: 860, margin: '0 auto' }}>
          
          <div style={{ marginBottom: 32 }}>
            <div className="site-eyebrow" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <FileText size={14} /> Legal Agreement
            </div>
            <h1 style={{ fontSize: 36, fontWeight: 800, marginTop: 8, marginBottom: 12 }}>Terms of Service</h1>
            <p style={{ color: 'var(--text-sub)', fontSize: 15 }}>
              Effective Date: November 17, 2026 • Official repository mirror:{' '}
              <a
                href="https://github.com/GKRBROS/gkrbot/blob/main/Terms%20of%20Service"
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
              1. Acceptance of Terms
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 24 }}>
              By inviting, authorizing, or using {brand} (&quot;the Bot&quot;) or accessing this dashboard, you confirm that you have read, understood, and agree to be bound by these Terms of Service, as well as Discord&apos;s{' '}
              <a href="https://discord.com/terms" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>
                Terms of Service
              </a>{' '}
              and{' '}
              <a href="https://discord.com/guidelines" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>
                Community Guidelines
              </a>.
            </p>

            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: 'var(--text)' }}>
              2. User Obligations &amp; Usage Rules
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 16 }}>
              You agree not to use the Bot for any of the following prohibited activities:
            </p>
            <ul style={{ color: 'var(--text-sub)', paddingLeft: 24, marginBottom: 24 }}>
              <li>Engaging in server raids, mass spamming, harassment, or malicious automation campaigns.</li>
              <li>Attempting to bypass access controls, exploit software vulnerabilities, or flood bot APIs.</li>
              <li>Distributing malicious links, spyware, trojans, or illicit content through the Bot&apos;s utilities.</li>
              <li>Violating any applicable local, national, or international regulations.</li>
            </ul>

            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: 'var(--text)' }}>
              3. Service Availability &amp; Modifications
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 24 }}>
              The Bot is provided on an &quot;as is&quot; and &quot;as available&quot; basis without warranties of any kind. We reserve the right to modify, suspend, or discontinue any feature, command, or service at any time with or without prior notice.
            </p>

            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: 'var(--text)' }}>
              4. Termination &amp; Blacklist
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 24 }}>
              We reserve the right to immediately terminate access or blacklist any guild or user found violating these Terms or engaging in disruptive behavior against our infrastructure or community.
            </p>

            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: 'var(--text)' }}>
              5. Limitation of Liability
            </h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 0 }}>
              Under no circumstances shall the operators or developers of {brand} be held liable for any direct, indirect, incidental, or consequential damages resulting from the use or inability to use the Bot or its services.
            </p>
          </div>

          <div style={{ marginTop: 24, textAlign: 'center' }}>
            <a
              href="https://github.com/GKRBROS/gkrbot/blob/main/Terms%20of%20Service"
              target="_blank"
              rel="noreferrer"
              className="site-btn site-btn-ghost"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <span>View Terms of Service on GitHub</span> <ExternalLink size={14} />
            </a>
          </div>

        </div>
      </section>
    </SitePage>
  );
}

export default Terms;
