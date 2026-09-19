import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

function Polls() {
  const { guildId } = useParams();
  const [polls, setPolls] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Creation modal
  const [showModal, setShowModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [question, setQuestion] = useState('');
  const [channelId, setChannelId] = useState('');
  const [options, setOptions] = useState(['', '']);
  const [multiChoice, setMultiChoice] = useState(false);
  const [anonymous, setAnonymous] = useState(false);
  const [durationMinutes, setDurationMinutes] = useState(0);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [pollsRes, chRes] = await Promise.all([
        api.get(`/guilds/${guildId}/polls`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      setPolls(pollsRes.data.polls || []);
      setChannels(chRes.data.channels || []);
      setError('');
    } catch (err) {
      console.error('Failed to fetch polls', err);
      setError(err.response?.data?.error || 'Failed to fetch polls');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const handleAddOption = () => {
    if (options.length < 10) setOptions([...options, '']);
  };

  const handleRemoveOption = (index) => {
    if (options.length > 2) {
      setOptions(options.filter((_, i) => i !== index));
    }
  };

  const handleOptionChange = (val, index) => {
    const next = [...options];
    next[index] = val;
    setOptions(next);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    const cleanOptions = options.map(o => o.trim()).filter(Boolean);
    if (!question.trim() || !channelId || cleanOptions.length < 2) {
      setError('Please provide a question, target channel, and at least 2 non-empty options.');
      return;
    }
    setSubmitting(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/polls`, {
        question: question.trim(),
        channel_id: channelId,
        options: cleanOptions,
        multi_choice: multiChoice,
        anonymous,
        duration_minutes: durationMinutes,
      });
      setSuccess('📊 Poll published to Discord successfully!');
      setShowModal(false);
      setQuestion('');
      setOptions(['', '']);
      setMultiChoice(false);
      setAnonymous(false);
      setDurationMinutes(0);
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create poll');
    } finally {
      setSubmitting(false);
    }
  };

  const handleClosePoll = async (messageId) => {
    if (!window.confirm('Close this poll and publish final results?')) return;
    try {
      await api.post(`/guilds/${guildId}/polls/${messageId}/close`);
      setSuccess('Poll closed and results locked!');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to close poll');
    }
  };

  const channelOptions = channels.map(c => ({ value: c.id, label: `#${c.name}` }));

  const activePolls = polls.filter(p => !p.ended);
  const endedPolls = polls.filter(p => p.ended);

  return (
    <div className="feature-page">
      <div className="feature-header">
        <div>
          <h1 className="feature-title">📊 Interactive Polls</h1>
          <p className="feature-desc">Live community voting with graphical progress bars, anonymous options & auto-close timers.</p>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + Create Poll
        </button>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span>{error}</span>
          <button className="btn-secondary" onClick={() => setError('')} style={{ padding: '2px 8px' }}>✕</button>
        </div>
      )}

      {success && (
        <div className="alert alert-success" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span>{success}</span>
          <button className="btn-secondary" onClick={() => setSuccess('')} style={{ padding: '2px 8px' }}>✕</button>
        </div>
      )}

      {/* Active Polls */}
      <div style={{ marginBottom: '32px' }}>
        <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: 'var(--text-main)' }}>
          Active Polls ({activePolls.length})
        </h3>

        {activePolls.length === 0 ? (
          <div className="dashboard-card" style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: '32px', marginBottom: '8px' }}>📊</div>
            <div>No active polls running. Create a poll to gather community feedback!</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
            {activePolls.map(p => {
              const ch = channels.find(c => c.id === p.channel_id);
              const totalVotes = p.total_votes || 0;
              return (
                <div key={p.message_id} className="dashboard-card" style={{ padding: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                    <span className="badge badge-success">Live Voting</span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      #{ch ? ch.name : p.channel_id}
                    </span>
                  </div>

                  <h4 style={{ fontSize: '17px', fontWeight: '700', margin: '0 0 16px', color: 'var(--text-main)' }}>
                    {p.question}
                  </h4>

                  {/* Options Progress Bars */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '20px' }}>
                    {p.options.map(opt => {
                      const count = p.distribution ? (p.distribution[opt] || 0) : 0;
                      const pct = totalVotes > 0 ? Math.round((count / totalVotes) * 100) : 0;
                      return (
                        <div key={opt}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '4px' }}>
                            <span style={{ fontWeight: '500' }}>{opt}</span>
                            <span style={{ color: 'var(--text-muted)' }}>{count} ({pct}%)</span>
                          </div>
                          <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', overflow: 'hidden' }}>
                            <div style={{ width: `${pct}%`, height: '100%', background: 'var(--primary)', borderRadius: '4px', transition: 'width 0.3s' }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '14px' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {totalVotes} total vote(s) {p.multi_choice ? '• Multiple' : '• Single'} {p.anonymous ? '• Anon' : ''}
                    </div>
                    <button className="btn-danger" onClick={() => handleClosePoll(p.message_id)} style={{ padding: '6px 14px', fontSize: '12px' }}>
                      Close Poll
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Finished Polls */}
      <div>
        <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: 'var(--text-main)' }}>
          Poll History ({endedPolls.length})
        </h3>

        {endedPolls.length === 0 ? (
          <div className="dashboard-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            No past closed polls.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
            {endedPolls.map(p => (
              <div key={p.message_id} className="dashboard-card" style={{ padding: '16px', opacity: 0.85 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span className="badge badge-muted" style={{ fontSize: '11px' }}>Concluded</span>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{p.total_votes || 0} votes</span>
                </div>
                <h5 style={{ margin: '0 0 10px', fontSize: '15px', color: 'var(--text-main)' }}>{p.question}</h5>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Options: {p.options.join(', ')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '540px' }}>
            <h3 style={{ marginTop: 0 }}>Create New Interactive Poll</h3>
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group">
                <label className="form-label">Poll Question / Topic</label>
                <input
                  type="text"
                  className="form-input"
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  placeholder="e.g. Which game should we play this weekend?"
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Destination Discord Channel</label>
                <Select
                  value={channelId}
                  onChange={setChannelId}
                  options={channelOptions}
                  placeholder="Select channel..."
                  searchable
                />
              </div>

              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Choices / Options (2 - 10)</span>
                  {options.length < 10 && (
                    <button type="button" onClick={handleAddOption} style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', fontSize: '12px', fontWeight: '600' }}>
                      + Add Option
                    </button>
                  )}
                </label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {options.map((opt, i) => (
                    <div key={i} style={{ display: 'flex', gap: '8px' }}>
                      <input
                        type="text"
                        className="form-input"
                        value={opt}
                        onChange={e => handleOptionChange(e.target.value, i)}
                        placeholder={`Option ${i + 1}`}
                        required
                      />
                      {options.length > 2 && (
                        <button type="button" className="btn-secondary" onClick={() => handleRemoveOption(i)} style={{ padding: '0 12px' }}>
                          ✕
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px' }}>
                  <input
                    type="checkbox"
                    checked={multiChoice}
                    onChange={e => setMultiChoice(e.target.checked)}
                  />
                  <span>Allow Multiple Choices</span>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px' }}>
                  <input
                    type="checkbox"
                    checked={anonymous}
                    onChange={e => setAnonymous(e.target.checked)}
                  />
                  <span>Anonymous Voting</span>
                </label>
              </div>

              <div className="form-group">
                <label className="form-label">Auto-Close Timer (Minutes, 0 = Never)</label>
                <input
                  type="number"
                  className="form-input"
                  min={0}
                  value={durationMinutes}
                  onChange={e => setDurationMinutes(Number(e.target.value))}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Publishing...' : '📊 Publish Poll'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Polls;
