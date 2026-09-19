import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  MessageSquarePlus,
  CheckCircle2,
  XCircle,
  Clock,
  ThumbsUp,
  ThumbsDown,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  Edit3,
  UserCheck
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import Modal from '../../components/Modal';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function Community() {
  const { guildId } = useParams();
  const [activeTab, setActiveTab] = useState('suggestions'); // 'suggestions' | 'verify'
  const [suggestions, setSuggestions] = useState([]);
  const [verifyConfig, setVerifyConfig] = useState({ verified_role_id: '', log_channel_id: '', min_account_days: 0 });
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Review modal
  const [selectedSuggestion, setSelectedSuggestion] = useState(null);
  const [reviewStatus, setReviewStatus] = useState('approved');
  const [staffNote, setStaffNote] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      if (!isRefresh) setLoading(true);
      const [comRes, chRes, roRes] = await Promise.all([
        api.get(`/guilds/${guildId}/community`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/roles`),
      ]);
      setSuggestions(comRes.data.suggestions || []);
      setVerifyConfig(comRes.data.verify_config || {});
      setChannels(chRes.data.channels || []);
      setRoles(roRes.data.roles || []);
      setError('');
    } catch (err) {
      console.error('Failed to load community data', err);
      setError(err.response?.data?.error || 'Failed to load community data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const handleSaveVerify = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/community/verify`, verifyConfig);
      setSuccess('Member gate verification settings saved successfully!');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save verification settings');
    }
  };

  const handleReviewSuggestion = async (e) => {
    e.preventDefault();
    if (!selectedSuggestion) return;
    setSubmittingReview(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/community/suggestions/${selectedSuggestion.id}/status`, {
        status: reviewStatus,
        staff_note: staffNote,
      });
      setSuccess(`Suggestion marked as ${reviewStatus}!`);
      setSelectedSuggestion(null);
      setStaffNote('');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to review suggestion');
    } finally {
      setSubmittingReview(false);
    }
  };

  const channelOptions = [{ value: '', label: 'Disabled (No Channel)' }, ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))];
  const roleOptions = [{ value: '', label: 'None (No Role)' }, ...roles.map(r => ({ value: r.id, label: `@${r.name}` }))];

  const getStatusBadge = (status) => {
    switch (status) {
      case 'approved':
        return <Badge variant="success" dot size="sm">Approved</Badge>;
      case 'denied':
        return <Badge variant="danger" dot size="sm">Denied</Badge>;
      case 'implemented':
        return <Badge variant="primary" dot size="sm">Implemented</Badge>;
      default:
        return <Badge variant="warning" dot size="sm">Under Review</Badge>;
    }
  };

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="50px" />
        <Skeleton height="300px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={MessageSquarePlus}
        title="Community & Suggestions"
        subtitle="Manage member idea submissions, feedback voting, staff review verdicts, and server verification gates."
        actions={
          <Button
            variant="outline"
            size="sm"
            icon={RefreshCw}
            loading={refreshing}
            onClick={() => fetchData(true)}
          >
            Refresh
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

      {/* Tabs Row */}
      <div style={{
        display: 'flex',
        gap: '6px',
        padding: '4px',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        width: 'fit-content'
      }}>
        <button
          onClick={() => setActiveTab('suggestions')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: 'var(--radius-md)',
            border: 'none',
            background: activeTab === 'suggestions' ? 'var(--bg-card)' : 'transparent',
            color: activeTab === 'suggestions' ? 'var(--text-main)' : 'var(--text-muted)',
            fontWeight: activeTab === 'suggestions' ? 600 : 500,
            fontSize: '13.5px',
            cursor: 'pointer',
            transition: 'all 150ms ease',
            boxShadow: activeTab === 'suggestions' ? '0 1px 3px rgba(0, 0, 0, 0.2)' : 'none'
          }}
        >
          <MessageSquarePlus size={16} color={activeTab === 'suggestions' ? 'var(--primary)' : 'currentColor'} />
          <span>Suggestions Review</span>
          <Badge variant={activeTab === 'suggestions' ? 'primary' : 'neutral'} size="sm">
            {suggestions.length}
          </Badge>
        </button>

        <button
          onClick={() => setActiveTab('verify')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: 'var(--radius-md)',
            border: 'none',
            background: activeTab === 'verify' ? 'var(--bg-card)' : 'transparent',
            color: activeTab === 'verify' ? 'var(--text-main)' : 'var(--text-muted)',
            fontWeight: activeTab === 'verify' ? 600 : 500,
            fontSize: '13.5px',
            cursor: 'pointer',
            transition: 'all 150ms ease',
            boxShadow: activeTab === 'verify' ? '0 1px 3px rgba(0, 0, 0, 0.2)' : 'none'
          }}
        >
          <ShieldCheck size={16} color={activeTab === 'verify' ? 'var(--primary)' : 'currentColor'} />
          <span>Member Verification</span>
        </button>
      </div>

      {/* TAB 1: SUGGESTIONS */}
      {activeTab === 'suggestions' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {suggestions.length === 0 ? (
            <EmptyState
              icon={MessageSquarePlus}
              title="No Suggestions Submitted"
              description="Members can use the bot's suggestion command to propose community improvements and vote on ideas."
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {suggestions.map(s => (
                <Card key={s.id} style={{ padding: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
                    <div style={{ flex: 1, minWidth: '280px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                        {getStatusBadge(s.status)}
                        <span style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                          ID #{s.id} • Author: {s.author_id}
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginLeft: 'auto' }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#10b981', fontSize: '12.5px', fontWeight: 600 }}>
                            <ThumbsUp size={14} /> {s.upvotes}
                          </span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#f87171', fontSize: '12.5px', fontWeight: 600 }}>
                            <ThumbsDown size={14} /> {s.downvotes}
                          </span>
                        </div>
                      </div>

                      <div style={{ fontSize: '14.5px', color: 'var(--text-main)', lineHeight: 1.5, marginBottom: s.staff_note ? '10px' : '0' }}>
                        &ldquo;{s.content}&rdquo;
                      </div>

                      {s.staff_note && (
                        <div style={{
                          fontSize: '12.5px',
                          color: 'var(--primary)',
                          background: 'rgba(88, 101, 242, 0.08)',
                          border: '1px solid rgba(88, 101, 242, 0.2)',
                          padding: '6px 12px',
                          borderRadius: 'var(--radius-sm)',
                          display: 'inline-block'
                        }}>
                          <strong>Staff Verdict:</strong> {s.staff_note}
                        </div>
                      )}
                    </div>

                    <div>
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={Edit3}
                        onClick={() => {
                          setSelectedSuggestion(s);
                          setReviewStatus(s.status === 'pending' ? 'approved' : s.status);
                          setStaffNote(s.staff_note || '');
                        }}
                      >
                        Review Idea
                      </Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: VERIFICATION GATE */}
      {activeTab === 'verify' && (
        <div style={{ maxWidth: '640px' }}>
          <Card>
            <CardHeader>
              <CardTitle>Member Verification Gate</CardTitle>
              <CardDescription>
                Screen incoming members before granting access to community chat channels.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveVerify} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Verified Member Role
                  </label>
                  <Select
                    value={verifyConfig.verified_role_id || ''}
                    onChange={val => setVerifyConfig({ ...verifyConfig, verified_role_id: val })}
                    options={roleOptions}
                    placeholder="Select verified role..."
                    searchable
                  />
                  <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                    Assigned immediately once a new member successfully completes verification.
                  </p>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Verification Audit Logs Channel
                  </label>
                  <Select
                    value={verifyConfig.log_channel_id || ''}
                    onChange={val => setVerifyConfig({ ...verifyConfig, log_channel_id: val })}
                    options={channelOptions}
                    placeholder="Select log channel..."
                    searchable
                  />
                  <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                    Channel where pass/fail verification events are logged.
                  </p>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Minimum Discord Account Age (Days)
                  </label>
                  <input
                    type="number"
                    className="form-input"
                    min={0}
                    value={verifyConfig.min_account_days || 0}
                    onChange={e => setVerifyConfig({ ...verifyConfig, min_account_days: Number(e.target.value) })}
                  />
                  <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                    Rejects alt accounts or newly generated spam bots younger than this limit.
                  </p>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-start', marginTop: '6px' }}>
                  <Button type="submit" variant="primary" icon={CheckCircle2}>
                    Save Verification Rules
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Review Suggestion Modal */}
      <Modal
        isOpen={Boolean(selectedSuggestion)}
        onClose={() => setSelectedSuggestion(null)}
        title={selectedSuggestion ? `Review Suggestion #${selectedSuggestion.id}` : 'Review'}
        maxWidth="500px"
      >
        {selectedSuggestion && (
          <form onSubmit={handleReviewSuggestion} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{
              padding: '14px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              fontSize: '13.5px',
              color: 'var(--text-main)',
              lineHeight: 1.45
            }}>
              &ldquo;{selectedSuggestion.content}&rdquo;
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Status Decision
              </label>
              <select
                className="form-input"
                value={reviewStatus}
                onChange={e => setReviewStatus(e.target.value)}
              >
                <option value="pending">Pending (Under Consideration)</option>
                <option value="approved">Approved (Accepted by Staff)</option>
                <option value="denied">Denied (Rejected)</option>
                <option value="implemented">Implemented (Live in Server)</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Staff Note / Reason (Optional)
              </label>
              <textarea
                className="form-input"
                rows={3}
                value={staffNote}
                onChange={e => setStaffNote(e.target.value)}
                placeholder="Give the member context or reasoning..."
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
              <Button type="button" variant="outline" onClick={() => setSelectedSuggestion(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={submittingReview}>
                Save Decision
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}

export default Community;
