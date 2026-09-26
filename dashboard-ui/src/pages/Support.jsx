import { useState } from 'react';
import api from '../api';
import { useBotName } from '../BotContext';
import { SitePage } from '../components/SiteLayout';
import { LifeBuoy, Send, MessageCircle, Clock, CheckCircle2 } from 'lucide-react';

const CATEGORIES = [
  { id: 'setup', label: '🛠️ Setup help' },
  { id: 'bug', label: '🐞 Bug report' },
  { id: 'feature', label: '💡 Feature request' },
  { id: 'account', label: '👤 Dashboard / login' },
  { id: 'other', label: '💬 Other' },
];

const SUPPORT_SERVER_URL = 'https://discord.gg/kbtwxdfhk9';

export function Support({ user }) {
  const botName = useBotName();
  const brand = (botName || 'Bot').trim();
  const [category, setCategory] = useState('setup');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [name, setName] = useState('');
  const [contact, setContact] = useState('');
  const [website, setWebsite] = useState(''); // honeypot, always left blank by real people
  const [status, setStatus] = useState('idle'); // idle | sending | success | error
  const [error, setError] = useState('');
  const [ticketId, setTicketId] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (subject.trim().length < 4) return setError('Please add a short subject (at least 4 characters).');
    if (message.trim().length < 15) return setError('Please describe the problem in a bit more detail (at least 15 characters).');
    if (!user && name.trim().length < 2) return setError('Please tell us your Discord username or name.');

    setStatus('sending');
    try {
      const res = await api.post('/support/tickets', {
        category, subject: subject.trim(), message: message.trim(),
        name: name.trim(), contact: contact.trim(), website,
      });
      setTicketId(res.data?.ticket_id || '');
      setStatus('success');
      setSubject(''); setMessage(''); setContact('');
    } catch (err) {
      setStatus('error');
      setError(err.response?.data?.error || 'Something went wrong sending your ticket. Please try again.');
    }
  };

  if (status === 'success') {
    return (
      <SitePage user={user}>
        <section className="site-section" style={{ paddingTop: 90, textAlign: 'center' }}>
          <div className="container" style={{ maxWidth: 480 }}>
            <CheckCircle2 size={44} color="var(--success)" style={{ marginBottom: 16 }} />
            <h2 style={{ fontSize: 26, fontWeight: 800, marginBottom: 8 }}>Ticket sent!</h2>
            <p style={{ color: 'var(--text-sub)', marginBottom: 6 }}>
              Our team has been notified in Discord and will get back to you soon.
            </p>
            {ticketId && <p style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', marginBottom: 24 }}>Reference: {ticketId}</p>}
            <button type="button" className="site-btn site-btn-primary" onClick={() => setStatus('idle')}>Send another ticket</button>
          </div>
        </section>
      </SitePage>
    );
  }

  return (
    <SitePage user={user}>
      <section className="site-section" style={{ paddingTop: 64 }}>
        <div className="container">
          <div className="site-section-head">
            <div className="site-eyebrow">We're here to help</div>
            <h2>Contact Support</h2>
            <p>Send us a message and it'll be posted directly to our support team on Discord.</p>
          </div>

          <div className="site-support-grid">
            <form className="site-form" onSubmit={handleSubmit}>
              {error && <div className="site-alert site-alert-error">{error}</div>}

              <div className="site-field">
                <label>What's this about?</label>
                <div className="site-cat-grid">
                  {CATEGORIES.map(c => (
                    <button
                      key={c.id}
                      type="button"
                      className={`site-cat-btn ${category === c.id ? 'active' : ''}`}
                      onClick={() => setCategory(c.id)}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              </div>

              {!user && (
                <div className="site-field">
                  <label>Your name / Discord username</label>
                  <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. yourname#0000" maxLength={60} />
                </div>
              )}

              <div className="site-field">
                <label>Subject</label>
                <input type="text" value={subject} onChange={e => setSubject(e.target.value)} placeholder="Short summary of the issue" maxLength={100} />
              </div>

              <div className="site-field">
                <label>Message</label>
                <textarea value={message} onChange={e => setMessage(e.target.value)} placeholder="Describe what's happening in detail..." maxLength={1500} />
              </div>

              <div className="site-field">
                <label>Contact (optional)</label>
                <input type="text" value={contact} onChange={e => setContact(e.target.value)} placeholder="Email or Discord DM, if you'd like a reply there" maxLength={100} />
              </div>

              {/* Honeypot: hidden from real users, bots tend to fill every field */}
              <input
                type="text" tabIndex={-1} autoComplete="off" className="site-honeypot"
                value={website} onChange={e => setWebsite(e.target.value)} aria-hidden="true"
              />

              <button type="submit" className="site-btn site-btn-primary" disabled={status === 'sending'} style={{ width: '100%', justifyContent: 'center', padding: '13px 0' }}>
                {status === 'sending' ? 'Sending...' : (<><Send size={15} /> <span>Send Ticket</span></>)}
              </button>
            </form>

            <div className="site-support-side">
              <div className="site-card">
                <div className="site-card-icon"><MessageCircle size={20} /></div>
                <h3>Join our Discord</h3>
                <p style={{ marginBottom: 14 }}>Get faster help and chat with our team and community directly.</p>
                <a href={SUPPORT_SERVER_URL} target="_blank" rel="noreferrer" className="site-btn site-btn-ghost" style={{ width: '100%', justifyContent: 'center' }}>
                  <LifeBuoy size={15} /> <span>Support Server</span>
                </a>
              </div>
              <div className="site-card">
                <div className="site-card-icon"><Clock size={20} /></div>
                <h3>Response time</h3>
                <p>Most tickets get a first response within a few hours. Urgent security issues are handled first.</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </SitePage>
  );
}

export default Support;
