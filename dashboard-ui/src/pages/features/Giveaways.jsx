import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Gift,
  Plus,
  Trophy,
  Clock,
  Users,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  StopCircle,
  Hash,
  Shield,
  Calendar
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
    if (!formData.prize.trim() || !formData.channel_id) {
      setError('Prize name and target Discord channel are required.');
      return;
    }
    setSubmitting(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/giveaways`, formData);
      setSuccess('Giveaway started and posted to Discord successfully!');
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
    if (!window.confirm('End this giveaway early and select winners immediately?')) return;
    try {
      await api.post(`/guilds/${guildId}/giveaways/${id}/end`);
      setSuccess('Giveaway ended and winners drawn!');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to end giveaway');
    }
  };

  const handleReroll = async (id) => {
    if (!window.confirm('Reroll new winners for this completed giveaway?')) return;
    try {
      await api.post(`/guilds/${guildId}/giveaways/${id}/reroll`);
      setSuccess('Giveaway rerolled! New winners announced in Discord.');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to reroll giveaway');
    }
  };

  const channelOptions = channels.map(c => ({ value: c.id, label: `#${c.name}` }));
  const roleOptions = [
    { value: '', label: 'None (Open to all members)' },
    ...roles.map(r => ({ value: r.id, label: `@${r.name}` }))
  ];

  const activeGws = giveaways.filter(g => !g.ended);
  const endedGws = giveaways.filter(g => g.ended);

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
        icon={Gift}
        title="Giveaways & Raffles"
        subtitle="Host automated button-entry giveaways with role eligibility requirements, live countdowns, and rerolls."
        actions={
          <Button
            variant="primary"
            size="sm"
            icon={Plus}
            onClick={() => setShowModal(true)}
          >
            Create Giveaway
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

      {/* Active Giveaways Section */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Active Giveaways
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Raffles currently accepting participant entries in Discord channels.
            </p>
          </div>
          <Badge variant="success" dot size="sm">
            {activeGws.length} Running
          </Badge>
        </div>

        {activeGws.length === 0 ? (
          <EmptyState
            icon={Gift}
            title="No Active Giveaways"
            description="Launch a new community giveaway with custom prizes, required roles, and automatic winner selection."
            actionLabel="Create First Giveaway"
            onAction={() => setShowModal(true)}
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
            {activeGws.map(gw => {
              const ch = channels.find(c => String(c.id) === String(gw.channel_id));
              const reqRole = roles.find(r => String(r.id) === String(gw.required_role_id));
              return (
                <Card key={gw.id} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <CardContent style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                      <div>
                        <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: 'var(--text-main)' }}>
                          {gw.prize}
                        </h4>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '12.5px', marginTop: '4px' }}>
                          <Hash size={13} />
                          <span>{ch ? ch.name : gw.channel_id}</span>
                        </div>
                      </div>
                      <Badge variant="success" dot size="sm">Active</Badge>
                    </div>

                    <div style={{
                      padding: '12px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      fontSize: '12.5px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '6px'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Winners</span>
                        <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>{gw.winners}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Entries</span>
                        <span style={{ color: 'var(--primary)', fontWeight: 600 }}>{gw.entries_count || 0} participants</span>
                      </div>
                      {reqRole && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-muted)' }}>Required Role</span>
                          <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>@{reqRole.name}</span>
                        </div>
                      )}
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Ends At</span>
                        <span style={{ color: 'var(--text-main)' }}>
                          {gw.ends_at ? new Date(gw.ends_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Pending'}
                        </span>
                      </div>
                    </div>
                  </CardContent>

                  <div style={{
                    padding: '12px 20px',
                    borderTop: '1px solid var(--border)',
                    background: 'rgba(255, 255, 255, 0.01)',
                    display: 'flex',
                    justifyContent: 'flex-end',
                    gap: '8px'
                  }}>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={StopCircle}
                      onClick={() => handleEndEarly(gw.id)}
                    >
                      End & Draw
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Finished Giveaways History */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Giveaway History
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Past completed raffles with option to reroll random winners.
            </p>
          </div>
          <Badge variant="neutral" size="sm">{endedGws.length} Completed</Badge>
        </div>

        <Card>
          <CardContent style={{ padding: '0' }}>
            {endedGws.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13.5px' }}>
                No completed giveaways on record.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13.5px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', textAlign: 'left', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '12px 16px', fontWeight: 600 }}>Prize</th>
                      <th style={{ padding: '12px 16px', fontWeight: 600 }}>Channel</th>
                      <th style={{ padding: '12px 16px', fontWeight: 600 }}>Total Entries</th>
                      <th style={{ padding: '12px 16px', fontWeight: 600 }}>Winners Drawn</th>
                      <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {endedGws.map(gw => {
                      const ch = channels.find(c => String(c.id) === String(gw.channel_id));
                      return (
                        <tr key={gw.id} style={{ borderBottom: '1px solid var(--border)' }}>
                          <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-main)' }}>
                            {gw.prize}
                          </td>
                          <td style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>
                            #{ch ? ch.name : gw.channel_id}
                          </td>
                          <td style={{ padding: '12px 16px', color: 'var(--text-main)' }}>
                            {gw.entries_count || 0}
                          </td>
                          <td style={{ padding: '12px 16px', color: 'var(--primary)', fontWeight: 500 }}>
                            {gw.winner_names ? gw.winner_names.join(', ') : `${gw.winners || 1} winner(s)`}
                          </td>
                          <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                            <Button
                              variant="outline"
                              size="sm"
                              icon={RotateCcw}
                              onClick={() => handleReroll(gw.id)}
                            >
                              Reroll
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Creation Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Launch New Giveaway"
        maxWidth="500px"
      >
        <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Prize Description
            </label>
            <input
              type="text"
              className="form-input"
              value={formData.prize}
              onChange={e => setFormData({ ...formData, prize: e.target.value })}
              placeholder="e.g. 1 Month Discord Nitro"
              required
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Discord Destination Channel
            </label>
            <Select
              value={formData.channel_id}
              onChange={val => setFormData({ ...formData, channel_id: val })}
              options={channelOptions}
              placeholder="Select giveaway channel..."
              searchable
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Duration (Minutes)
              </label>
              <input
                type="number"
                min="1"
                className="form-input"
                value={formData.duration_minutes}
                onChange={e => setFormData({ ...formData, duration_minutes: parseInt(e.target.value, 10) || 60 })}
                required
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Number of Winners
              </label>
              <input
                type="number"
                min="1"
                max="20"
                className="form-input"
                value={formData.winners}
                onChange={e => setFormData({ ...formData, winners: parseInt(e.target.value, 10) || 1 })}
                required
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Required Entry Role (Optional)
            </label>
            <Select
              value={formData.required_role_id}
              onChange={val => setFormData({ ...formData, required_role_id: val })}
              options={roleOptions}
              placeholder="None (Open to all)"
              searchable
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
            <Button type="button" variant="outline" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={submitting}>
              Launch Giveaway
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default Giveaways;
