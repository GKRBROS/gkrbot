import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

function Community() {
  const { guildId } = useParams();
  const [activeTab, setActiveTab] = useState('suggestions'); // 'suggestions' | 'verify'
  const [suggestions, setSuggestions] = useState([]);
  const [verifyConfig, setVerifyConfig] = useState({ verified_role_id: '', log_channel_id: '', min_account_days: 0 });
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Review modal
  const [selectedSuggestion, setSelectedSuggestion] = useState(null);
  const [reviewStatus, setReviewStatus] = useState('approved');
  const [staffNote, setStaffNote] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  const fetchData = async () => {
    try {
      setLoading(true);
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
      setSuccess('✅ Member verification settings saved successfully!');
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

  const channelOptions = [{ value: '', label: 'None' }, ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))];
  const roleOptions = [{ value: '', label: 'None' }, ...roles.map(r => ({ value: r.id, label: `@${r.name}` }))];

  const getStatusBadge = (status) => {
    switch (status) {
      case 'approved': return <span className="badge badge-success">Approved</span>;
      case 'denied': return <span className="badge badge-danger">Denied</span>;
      case 'implemented': return <span className="badge badge-primary">Implemented</span>;
      default: return <span className="badge badge-warning">Pending</span>;
    }
  };

  if (loading) {
    return <div className="feature-page" style={{ padding: '40px', textAlign: 'center' }}>Loading Community System...</div>;
  }

  return (
    <div className="feature-page">
      <div className="feature-header">
        <div>
          <h1 className="feature-title">🤝 Community & Suggestions</h1>
          <p className="feature-desc">Member idea suggestion voting, staff approvals & verification gates.</p>
        </div>
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

      {/* Tabs */}
      <div className="tabs-container" style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '24px' }}>
        <button
          className={`tab-btn ${activeTab === 'suggestions' ? 'active' : ''}`}
          onClick={() => setActiveTab('suggestions')}
          style={{
            padding: '10px 18px', border: 'none', background: 'transparent',
            cursor: 'pointer', fontWeight: '600',
            color: activeTab === 'suggestions' ? 'var(--primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'suggestions' ? '2px solid var(--primary)' : 'none'
          }}
        >
          💡 Suggestions Review ({suggestions.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'verify' ? 'active' : ''}`}
          onClick={() => setActiveTab('verify')}
          style={{
            padding: '10px 18px', border: 'none', background: 'transparent',
            cursor: 'pointer', fontWeight: '600',
            color: activeTab === 'verify' ? 'var(--primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'verify' ? '2px solid var(--primary)' : 'none'
          }}
        >
          🛡️ Member Verification
        </button>
      </div>

      {/* SUGGESTIONS TAB */}
      {activeTab === 'suggestions' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '18px' }}>Submitted Ideas & Feedback</h3>
            <button className="btn-secondary" onClick={fetchData} style={{ padding: '6px 14px' }}>🔄 Refresh</button>
          </div>

          {suggestions.length === 0 ? (
            <div className="dashboard-card" style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '32px', marginBottom: '8px' }}>💡</div>
              <div>No community suggestions submitted yet.</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {suggestions.map(s => (
                <div key={s.id} className="dashboard-card" style={{ padding: '18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
                  <div style={{ flex: 1, minWidth: '280px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                      {getStatusBadge(s.status)}
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>#{s.id} • Author: {s.author_id}</span>
                      <span style={{ fontSize: '12px', color: '#10b981', fontWeight: '600' }}>👍 {s.upvotes}</span>
                      <span style={{ fontSize: '12px', color: '#ef4444', fontWeight: '600' }}>👎 {s.downvotes}</span>
                    </div>

                    <div style={{ fontSize: '15px', color: 'var(--text-main)', lineHeight: 1.5 }}>
                      &ldquo;{s.content}&rdquo;
                    </div>

                    {s.staff_note && (
                      <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--primary)', background: 'rgba(88,101,242,0.1)', padding: '4px 10px', borderRadius: '4px', display: 'inline-block' }}>
                        Staff note: {s.staff_note}
                      </div>
                    )}
                  </div>

                  <div>
                    <button
                      className="btn-primary"
                      onClick={() => {
                        setSelectedSuggestion(s);
                        setReviewStatus(s.status === 'pending' ? 'approved' : s.status);
                        setStaffNote(s.staff_note || '');
                      }}
                      style={{ padding: '6px 16px', fontSize: '13px' }}
                    >
                      Review Idea
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* VERIFICATION TAB */}
      {activeTab === 'verify' && (
        <div className="dashboard-card" style={{ padding: '24px', maxWidth: '600px' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>Verification System Setup</h3>
          <form onSubmit={handleSaveVerify} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">Verified Member Role</label>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 6px' }}>Role assigned when a member completes verification.</p>
              <Select
                value={verifyConfig.verified_role_id || ''}
                onChange={val => setVerifyConfig({ ...verifyConfig, verified_role_id: val })}
                options={roleOptions}
                placeholder="Select role..."
                searchable
              />
            </div>

            <div className="form-group">
              <label className="form-label">Verification Logs Channel</label>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 6px' }}>Channel where verification pass/fail audit logs are sent.</p>
              <Select
                value={verifyConfig.log_channel_id || ''}
                onChange={val => setVerifyConfig({ ...verifyConfig, log_channel_id: val })}
                options={channelOptions}
                placeholder="Select channel..."
                searchable
              />
            </div>

            <div className="form-group">
              <label className="form-label">Minimum Account Age (Days)</label>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 6px' }}>Prevent accounts younger than this from verifying (anti-alt / anti-raid).</p>
              <input
                type="number"
                className="form-input"
                min={0}
                value={verifyConfig.min_account_days || 0}
                onChange={e => setVerifyConfig({ ...verifyConfig, min_account_days: Number(e.target.value) })}
              />
            </div>

            <button type="submit" className="btn-primary" style={{ marginTop: '8px' }}>
              Save Verification Config
            </button>
          </form>
        </div>
      )}

      {/* Review Suggestion Modal */}
      {selectedSuggestion && (
        <div className="modal-overlay" onClick={() => setSelectedSuggestion(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <h3 style={{ marginTop: 0 }}>Review Suggestion #{selectedSuggestion.id}</h3>
            <p style={{ background: 'rgba(255,255,255,0.05)', padding: '12px', borderRadius: '6px', fontSize: '14px', margin: '0 0 16px' }}>
              {selectedSuggestion.content}
            </p>

            <form onSubmit={handleReviewSuggestion} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group">
                <label className="form-label">Decision Status</label>
                <select
                  className="form-input"
                  value={reviewStatus}
                  onChange={e => setReviewStatus(e.target.value)}
                >
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="denied">Denied</option>
                  <option value="implemented">Implemented</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Staff Note / Reason</label>
                <textarea
                  className="form-input"
                  rows={3}
                  value={staffNote}
                  onChange={e => setStaffNote(e.target.value)}
                  placeholder="Optional note for the community..."
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '14px' }}>
                <button type="button" className="btn-secondary" onClick={() => setSelectedSuggestion(null)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={submittingReview}>
                  {submittingReview ? 'Submitting...' : 'Save Decision'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Community;
