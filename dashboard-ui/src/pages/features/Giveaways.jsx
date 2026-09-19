import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

function Giveaways() {
  const { guildId } = useParams();
  const [giveaways, setGiveaways] = useState([]);
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Creation modal
  const [showModal, setShowModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    prize: '',
    channel_id: '',
    duration_minutes: 60,
    winners: 1,
    required_role_id: '',
  });

  const fetchData = async () => {
    try {
      setLoading(true);
      const [gwRes, chRes, roRes] = await Promise.all([
        api.get(`/guilds/${guildId}/giveaways`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/roles`),
      ]);
      setGiveaways(gwRes.data.giveaways || []);
      setChannels(chRes.data.channels || []);
      setRoles(roRes.data.roles || []);
      setError('');
    } catch (err) {
      console.error('Failed to fetch giveaways', err);
      setError(err.response?.data?.error || 'Failed to fetch giveaways');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [guildId]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!formData.prize || !formData.channel_id) {
      setError('Prize and channel are required.');
      return;
    }
    setSubmitting(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/giveaways`, formData);
      setSuccess('🎉 Giveaway created and posted to Discord!');
      setShowModal(false);
      setFormData({
        prize: '',
        channel_id: '',
        duration_minutes: 60,
        winners: 1,
        required_role_id: '',
      });
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to start giveaway');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEndEarly = async (id) => {
    if (!window.confirm('End this giveaway early and choose winners now?')) return;
    try {
      await api.post(`/guilds/${guildId}/giveaways/${id}/end`);
      setSuccess('Giveaway ended and winners selected!');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to end giveaway');
    }
  };

  const handleReroll = async (id) => {
    if (!window.confirm('Reroll new winners for this giveaway?')) return;
    try {
      await api.post(`/guilds/${guildId}/giveaways/${id}/reroll`);
      setSuccess('Giveaway rerolled! New winners announced in Discord.');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to reroll giveaway');
    }
  };

  const channelOptions = channels.map(c => ({ value: c.id, label: `#${c.name}` }));
  const roleOptions = [{ value: '', label: 'None (Open to everyone)' }, ...roles.map(r => ({ value: r.id, label: `@${r.name}` }))];

  const activeGws = giveaways.filter(g => !g.ended);
  const endedGws = giveaways.filter(g => g.ended);

  return (
    <div className="feature-page">
      <div className="feature-header">
        <div>
          <h1 className="feature-title">🎉 Giveaway System</h1>
          <p className="feature-desc">Create button-based giveaways with role requirements, instant winner draws & rerolls.</p>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + Create Giveaway
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

      {/* Active Giveaways */}
      <div style={{ marginBottom: '32px' }}>
        <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: 'var(--text-main)' }}>
          Active Giveaways ({activeGws.length})
        </h3>

        {activeGws.length === 0 ? (
          <div className="dashboard-card" style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: '32px', marginBottom: '8px' }}>🎁</div>
            <div>No active giveaways. Click &ldquo;+ Create Giveaway&rdquo; to launch one!</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
            {activeGws.map(gw => {
              const ch = channels.find(c => c.id === gw.channel_id);
              return (
                <div key={gw.id} className="dashboard-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <h4 style={{ margin: '0 0 6px', fontSize: '18px', color: 'var(--text-main)' }}>
                        🎁 {gw.prize}
                      </h4>
                      <span className="badge badge-success">Running</span>
                    </div>

                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <div><strong>Channel:</strong> #{ch ? ch.name : gw.channel_id}</div>
                      <div><strong>Winners:</strong> {gw.winners} winner(s)</div>
                      <div><strong>Entries:</strong> {gw.entries_count} participant(s)</div>
                      <div><strong>Ends at:</strong> {new Date(gw.ends_at).toLocaleString()}</div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px', marginTop: '18px', justifyContent: 'flex-end' }}>
                    <button className="btn-danger" onClick={() => handleEndEarly(gw.id)} style={{ padding: '6px 14px', fontSize: '12px' }}>
                      End & Draw Winners
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Finished Giveaways */}
      <div>
        <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: 'var(--text-main)' }}>
          Giveaway History ({endedGws.length})
        </h3>

        {endedGws.length === 0 ? (
          <div className="dashboard-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            No past giveaways.
          </div>
        ) : (
          <div className="dashboard-card" style={{ padding: '16px', overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '10px 8px' }}>Prize</th>
                  <th style={{ padding: '10px 8px' }}>Channel</th>
                  <th style={{ padding: '10px 8px' }}>Entries</th>
                  <th style={{ padding: '10px 8px' }}>Winners</th>
                  <th style={{ padding: '10px 8px' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {endedGws.map(gw => {
                  const ch = channels.find(c => c.id === gw.channel_id);
                  return (
                    <tr key={gw.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <td style={{ padding: '10px 8px', fontWeight: '600' }}>🎁 {gw.prize}</td>
                      <td style={{ padding: '10px 8px', color: 'var(--text-muted)' }}>#{ch ? ch.name : gw.channel_id}</td>
                      <td style={{ padding: '10px 8px' }}>{gw.entries_count}</td>
                      <td style={{ padding: '10px 8px' }}>
                        {gw.winner_ids && gw.winner_ids.length ? (
                          <span style={{ color: '#10b981' }}>{gw.winner_ids.length} winner(s)</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>None</span>
                        )}
                      </td>
                      <td style={{ padding: '10px 8px' }}>
                        <button className="btn-secondary" onClick={() => handleReroll(gw.id)} style={{ padding: '4px 10px', fontSize: '12px' }}>
                          🔄 Reroll
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <h3 style={{ marginTop: 0 }}>Create New Giveaway</h3>
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group">
                <label className="form-label">Prize Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.prize}
                  onChange={e => setFormData({ ...formData, prize: e.target.value })}
                  placeholder="e.g. Discord Nitro (1 Month)"
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Destination Discord Channel</label>
                <Select
                  value={formData.channel_id}
                  onChange={val => setFormData({ ...formData, channel_id: val })}
                  options={channelOptions}
                  placeholder="Select channel..."
                  searchable
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">Duration (Minutes)</label>
                  <input
                    type="number"
                    className="form-input"
                    min={1}
                    value={formData.duration_minutes}
                    onChange={e => setFormData({ ...formData, duration_minutes: Number(e.target.value) })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Number of Winners</label>
                  <input
                    type="number"
                    className="form-input"
                    min={1}
                    max={20}
                    value={formData.winners}
                    onChange={e => setFormData({ ...formData, winners: Number(e.target.value) })}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Required Role (Optional)</label>
                <Select
                  value={formData.required_role_id}
                  onChange={val => setFormData({ ...formData, required_role_id: val })}
                  options={roleOptions}
                  placeholder="None"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Launching...' : '🎉 Launch Giveaway'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Giveaways;
