import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  BarChart2,
  Plus,
  Trash2,
  Lock,
  CheckCircle2,
  AlertCircle,
  Hash,
  Users,
  CheckSquare,
  Clock,
  Vote
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Toggle from '../../components/Toggle';
import Badge from '../../components/Badge';
import Modal from '../../components/Modal';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

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
      setError('Please provide a poll question, target channel, and at least 2 non-empty choices.');
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
      setSuccess('Poll deployed to Discord channel successfully!');
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
    if (!window.confirm('Close this poll and publish final results in Discord?')) return;
    try {
      await api.post(`/guilds/${guildId}/polls/${messageId}/close`);
      setSuccess('Poll closed and final vote tally locked!');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to close poll');
    }
  };

  const channelOptions = channels.map(c => ({ value: c.id, label: `#${c.name}` }));

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="240px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={BarChart2}
        title="Interactive Polls"
        subtitle="Publish interactive single or multi-choice community polls with live Discord button voting and real-time tallies."
        actions={
          <Button
            variant="primary"
            size="sm"
            icon={Plus}
            onClick={() => setShowModal(true)}
          >
            Create Poll
          </Button>
        }
      />

      {error && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.25)',
          color: '#f87171',
          fontSize: '13.5px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertCircle size={17} />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError('')}
            style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '16px' }}
          >
            ✕
          </button>
        </div>
      )}

      {success && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          background: 'rgba(16, 185, 129, 0.1)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          color: '#34d399',
          fontSize: '13.5px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <CheckCircle2 size={17} />
            <span>{success}</span>
          </div>
          <button
            onClick={() => setSuccess('')}
            style={{ background: 'transparent', border: 'none', color: '#34d399', cursor: 'pointer', fontSize: '16px' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Polls Grid */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Active & Past Polls
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Track member participation rates and manage live votes.
            </p>
          </div>
          <Badge variant="primary" size="sm">{polls.length} Total Polls</Badge>
        </div>

        {polls.length === 0 ? (
          <EmptyState
            icon={BarChart2}
            title="No Polls Conducted"
            description="Engage your community by asking questions with customizable response options and live tallies."
            actionLabel="Create First Poll"
            onAction={() => setShowModal(true)}
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
            {polls.map(poll => {
              const ch = channels.find(c => String(c.id) === String(poll.channel_id));
              const totalVotes = poll.total_votes || (poll.options ? poll.options.reduce((acc, curr) => acc + (curr.votes || 0), 0) : 0);
              const isClosed = poll.closed;

              return (
                <Card key={poll.message_id || poll.id} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <CardContent style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                      <div style={{ flex: 1, paddingRight: '10px' }}>
                        <h4 style={{ margin: 0, fontSize: '15.5px', fontWeight: 700, color: 'var(--text-main)', lineHeight: 1.35 }}>
                          {poll.question}
                        </h4>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '12px', marginTop: '4px' }}>
                          <Hash size={13} />
                          <span>{ch ? ch.name : poll.channel_id}</span>
                          <span>•</span>
                          <span>{totalVotes} vote(s) cast</span>
                        </div>
                      </div>
                      <Badge variant={isClosed ? 'neutral' : 'success'} dot={!isClosed} size="sm">
                        {isClosed ? 'Closed' : 'Voting Open'}
                      </Badge>
                    </div>

                    {/* Options list with progress bars */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '14px' }}>
                      {poll.options && poll.options.map((opt, i) => {
                        const optVotes = opt.votes || 0;
                        const pct = totalVotes > 0 ? Math.round((optVotes / totalVotes) * 100) : 0;
                        return (
                          <div
                            key={i}
                            style={{
                              padding: '8px 10px',
                              borderRadius: 'var(--radius-sm)',
                              background: 'var(--bg-surface)',
                              border: '1px solid var(--border)',
                              position: 'relative',
                              overflow: 'hidden'
                            }}
                          >
                            <div
                              style={{
                                position: 'absolute',
                                left: 0,
                                top: 0,
                                bottom: 0,
                                width: `${pct}%`,
                                background: 'rgba(88, 101, 242, 0.12)',
                                transition: 'width 300ms ease'
                              }}
                            />
                            <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', fontSize: '12.5px', zIndex: 1 }}>
                              <span style={{ fontWeight: 500, color: 'var(--text-main)' }}>
                                {opt.text || opt}
                              </span>
                              <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>
                                {pct}% ({optVotes})
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>

                  {!isClosed && (
                    <div style={{
                      padding: '12px 20px',
                      borderTop: '1px solid var(--border)',
                      background: 'rgba(255, 255, 255, 0.01)',
                      display: 'flex',
                      justifyContent: 'flex-end'
                    }}>
                      <Button
                        variant="danger"
                        size="sm"
                        icon={Lock}
                        onClick={() => handleClosePoll(poll.message_id || poll.id)}
                      >
                        End Poll & Lock Results
                      </Button>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Creation Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Create New Interactive Poll"
        maxWidth="540px"
      >
        <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Poll Question
            </label>
            <input
              type="text"
              className="form-input"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              placeholder="e.g. Which game should we play this community night?"
              required
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Target Channel
            </label>
            <Select
              value={channelId}
              onChange={setChannelId}
              options={channelOptions}
              placeholder="Select destination channel..."
              searchable
            />
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                Poll Options ({options.length}/10)
              </label>
              {options.length < 10 && (
                <button
                  type="button"
                  onClick={handleAddOption}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--primary)',
                    fontSize: '12.5px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    padding: 0
                  }}
                >
                  + Add Option
                </button>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {options.map((opt, index) => (
                <div key={index} style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <input
                    type="text"
                    className="form-input"
                    value={opt}
                    onChange={e => handleOptionChange(e.target.value, index)}
                    placeholder={`Option ${index + 1}`}
                    required
                  />
                  {options.length > 2 && (
                    <button
                      type="button"
                      onClick={() => handleRemoveOption(index)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#f87171',
                        cursor: 'pointer',
                        padding: '6px'
                      }}
                      title="Remove option"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div style={{
            padding: '14px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px'
          }}>
            <Toggle
              checked={multiChoice}
              onChange={setMultiChoice}
              label="Allow Multiple Selections"
              description="Members can choose more than one option from the list."
            />
            <Toggle
              checked={anonymous}
              onChange={setAnonymous}
              label="Anonymous Voting"
              description="Hide who voted for which option to ensure private responses."
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Auto-Close Duration (Minutes, 0 = Keep Open Until Manually Closed)
            </label>
            <input
              type="number"
              min="0"
              className="form-input"
              value={durationMinutes}
              onChange={e => setDurationMinutes(parseInt(e.target.value, 10) || 0)}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
            <Button type="button" variant="outline" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={submitting}>
              Publish Poll
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default Polls;
