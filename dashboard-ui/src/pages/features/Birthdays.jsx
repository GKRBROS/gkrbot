import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

function Birthdays() {
  const { guildId } = useParams();
  const [birthdays, setBirthdays] = useState([]);
  const [channels, setChannels] = useState([]);
  const [channelId, setChannelId] = useState('');
  const [months, setMonths] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Add modal
  const [showModal, setShowModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [userId, setUserId] = useState('');
  const [username, setUsername] = useState('');
  const [birthDay, setBirthDay] = useState(1);
  const [birthMonth, setBirthMonth] = useState(1);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [bRes, chRes] = await Promise.all([
        api.get(`/guilds/${guildId}/birthdays`),
        api.get(`/guilds/${guildId}/channels`),
      ]);
      setBirthdays(bRes.data.birthdays || []);
      setChannelId(bRes.data.channel_id || '');
      setMonths(bRes.data.months || []);
      setChannels(chRes.data.channels || []);
      setError('');
    } catch (err) {
      console.error('Failed to load birthdays', err);
      setError(err.response?.data?.error || 'Failed to load birthdays');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const handleSaveChannel = async () => {
    try {
      await api.post(`/guilds/${guildId}/birthdays/channel`, { channel_id: channelId });
      setSuccess('🎂 Birthday announcement channel updated!');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update channel');
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!userId.trim()) {
      setError('Member Discord User ID is required.');
      return;
    }
    setSubmitting(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/birthdays`, {
        user_id: userId.trim(),
        username: username.trim() || 'Member',
        birth_day: Number(birthDay),
        birth_month: Number(birthMonth),
      });
      setSuccess('Birthday registered successfully!');
      setShowModal(false);
      setUserId('');
      setUsername('');
      setBirthDay(1);
      setBirthMonth(1);
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save birthday');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (uId) => {
    if (!window.confirm('Remove this member\'s birthday?')) return;
    try {
      await api.delete(`/guilds/${guildId}/birthdays/${uId}`);
      setSuccess('Birthday removed.');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete birthday');
    }
  };

  const channelOptions = [{ value: '', label: 'None (Disabled)' }, ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))];

  return (
    <div className="feature-page">
      <div className="feature-header">
        <div>
          <h1 className="feature-title">🎂 Birthday System</h1>
          <p className="feature-desc">Automatic daily celebration messages & member birthday calendar announcements.</p>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + Add Member Birthday
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

      {/* Channel Config Card */}
      <div className="dashboard-card" style={{ padding: '20px', marginBottom: '24px' }}>
        <h3 style={{ margin: '0 0 14px', fontSize: '17px' }}>Announcement Configuration</h3>
        <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ margin: 0, minWidth: '280px', flex: 1 }}>
            <label className="form-label">Birthday Announcement Channel</label>
            <Select
              value={channelId}
              onChange={setChannelId}
              options={channelOptions}
              placeholder="Select channel..."
              searchable
            />
          </div>
          <button className="btn-primary" onClick={handleSaveChannel}>
            Save Channel
          </button>
        </div>
      </div>

      {/* Member Birthday List */}
      <div className="dashboard-card" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0, fontSize: '18px' }}>Registered Birthdays ({birthdays.length})</h3>
          <button className="btn-secondary" onClick={fetchData} style={{ padding: '6px 14px' }}>🔄 Refresh</button>
        </div>

        {birthdays.length === 0 ? (
          <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: '32px', marginBottom: '8px' }}>🎂</div>
            <div>No birthdays registered yet. Click &ldquo;+ Add Member Birthday&rdquo; to add!</div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '12px 8px' }}>Member</th>
                  <th style={{ padding: '12px 8px' }}>User ID</th>
                  <th style={{ padding: '12px 8px' }}>Date</th>
                  <th style={{ padding: '12px 8px' }}>Month</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {birthdays.map(b => (
                  <tr key={b.user_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '12px 8px', fontWeight: '600', color: 'var(--text-main)' }}>
                      🎉 {b.username}
                    </td>
                    <td style={{ padding: '12px 8px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                      {b.user_id}
                    </td>
                    <td style={{ padding: '12px 8px', fontWeight: '700' }}>
                      Day {b.birth_day}
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <span className="badge badge-primary">{b.month_name}</span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                      <button className="btn-danger" onClick={() => handleDelete(b.user_id)} style={{ padding: '4px 10px', fontSize: '12px' }}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '480px' }}>
            <h3 style={{ marginTop: 0 }}>Add Member Birthday</h3>
            <form onSubmit={handleAdd} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group">
                <label className="form-label">Discord User ID</label>
                <input
                  type="text"
                  className="form-input"
                  value={userId}
                  onChange={e => setUserId(e.target.value)}
                  placeholder="e.g. 847291827491029384"
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Member Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="e.g. Alex"
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">Birth Day (1-31)</label>
                  <input
                    type="number"
                    className="form-input"
                    min={1}
                    max={31}
                    value={birthDay}
                    onChange={e => setBirthDay(Number(e.target.value))}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Birth Month</label>
                  <select
                    className="form-input"
                    value={birthMonth}
                    onChange={e => setBirthMonth(Number(e.target.value))}
                  >
                    {months.map((m, idx) => (
                      <option key={idx + 1} value={idx + 1}>
                        {idx + 1} - {m}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Saving...' : '🎂 Add Birthday'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Birthdays;
