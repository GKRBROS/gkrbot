import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Cake,
  Plus,
  Trash2,
  Calendar,
  Hash,
  CheckCircle2,
  AlertCircle,
  Gift
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

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function Birthdays() {
  const { guildId } = useParams();
  const [birthdays, setBirthdays] = useState([]);
  const [channels, setChannels] = useState([]);
  const [channelId, setChannelId] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingChannel, setSavingChannel] = useState(false);
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
    setSavingChannel(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/birthdays/channel`, { channel_id: channelId });
      setSuccess('Birthday announcement channel updated successfully!');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update channel');
    } finally {
      setSavingChannel(false);
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
    if (!window.confirm('Remove this member\'s birthday record?')) return;
    try {
      await api.delete(`/guilds/${guildId}/birthdays/${uId}`);
      setSuccess('Birthday record removed.');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete birthday');
    }
  };

  const channelOptions = [
    { value: '', label: 'None (Announcements Disabled)' },
    ...channels.map(c => ({ value: c.id, label: `#${c.name}` }))
  ];

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <Skeleton height="140px" />
        <Skeleton height="260px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Cake}
        title="Birthday Celebrations"
        subtitle="Schedule automated celebratory announcements and custom roles when server members have birthdays."
        actions={
          <Button
            variant="primary"
            size="sm"
            icon={Plus}
            onClick={() => setShowModal(true)}
          >
            Register Birthday
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

      {/* Announcement Channel Card */}
      <Card>
        <CardHeader>
          <CardTitle>Announcement Channel Configuration</CardTitle>
          <CardDescription>
            Where the bot will automatically post birthday congratulations at 00:00 UTC.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end', maxWidth: '540px' }}>
            <div style={{ flex: 1, minWidth: '260px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Celebration Channel
              </label>
              <Select
                value={channelId}
                onChange={setChannelId}
                options={channelOptions}
                placeholder="Select broadcast channel..."
                searchable
              />
            </div>
            <Button
              variant="primary"
              icon={CheckCircle2}
              loading={savingChannel}
              onClick={handleSaveChannel}
            >
              Save Channel
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Member Birthday Registry */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
              Registered Member Birthdays
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
              Calendar of community birthdays.
            </p>
          </div>
          <Badge variant="primary" size="sm">{birthdays.length} Registered</Badge>
        </div>

        <Card>
          <CardContent style={{ padding: '0' }}>
            {birthdays.length === 0 ? (
              <EmptyState
                icon={Cake}
                title="No Birthdays Registered"
                description="Members can register their birthdays using the Discord slash command or you can add them manually above."
                actionLabel="Add Member Birthday"
                onAction={() => setShowModal(true)}
              />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13.5px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', textAlign: 'left', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '12px 16px', fontWeight: 600 }}>Member</th>
                      <th style={{ padding: '12px 16px', fontWeight: 600 }}>Discord User ID</th>
                      <th style={{ padding: '12px 16px', fontWeight: 600 }}>Date</th>
                      <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {birthdays.map(b => (
                      <tr key={b.user_id} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-main)' }}>
                          {b.username || 'Community Member'}
                        </td>
                        <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '12px' }}>
                          {b.user_id}
                        </td>
                        <td style={{ padding: '12px 16px' }}>
                          <Badge variant="neutral" size="sm">
                            {MONTH_NAMES[b.birth_month - 1]} {b.birth_day}
                          </Badge>
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                          <Button
                            variant="ghost"
                            size="sm"
                            icon={Trash2}
                            onClick={() => handleDelete(b.user_id)}
                          >
                            Remove
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Manual Registration Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Register Member Birthday"
        maxWidth="460px"
      >
        <form onSubmit={handleAdd} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Discord User ID
            </label>
            <input
              type="text"
              className="form-input"
              value={userId}
              onChange={e => setUserId(e.target.value)}
              placeholder="e.g. 192837482910384756"
              required
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Display Name (Optional)
            </label>
            <input
              type="text"
              className="form-input"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Username label..."
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Month
              </label>
              <select
                className="form-input"
                value={birthMonth}
                onChange={e => setBirthMonth(Number(e.target.value))}
              >
                {MONTH_NAMES.map((m, idx) => (
                  <option key={idx + 1} value={idx + 1}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Day
              </label>
              <input
                type="number"
                min="1"
                max="31"
                className="form-input"
                value={birthDay}
                onChange={e => setBirthDay(Number(e.target.value))}
                required
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
            <Button type="button" variant="outline" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={submitting}>
              Save Birthday
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default Birthdays;
