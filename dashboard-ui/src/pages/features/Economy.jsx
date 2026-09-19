import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Coins,
  Store,
  Users,
  Settings,
  Plus,
  Trash2,
  ArrowUpDown,
  Wallet,
  Building2,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  Trophy,
  Award,
  Tag
} from 'lucide-react';
import api from '../../api';
import { Select } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import Toggle from '../../components/Toggle';
import Modal from '../../components/Modal';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function Economy() {
  const { guildId } = useParams();
  const [items, setItems] = useState([]);
  const [settings, setSettings] = useState({ rob_enabled: true, crime_enabled: true });
  const [stats, setStats] = useState({ total_currency: 0, accounts: 0 });
  const [topUsers, setTopUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Shop item form
  const [form, setForm] = useState({ name: '', description: '', price: '', role_id: '' });

  // Manual coin adjust modal
  const [showAdjustModal, setShowAdjustModal] = useState(false);
  const [adjustData, setAdjustData] = useState({ user_id: '', action: 'add', target: 'wallet', amount: 100 });
  const [adjusting, setAdjusting] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [ecoRes, rolesRes] = await Promise.allSettled([
        api.get(`/guilds/${guildId}/economy`),
        api.get(`/guilds/${guildId}/roles`),
      ]);

      if (ecoRes.status === 'fulfilled') {
        setItems(ecoRes.value.data.shop_items || []);
        setSettings(ecoRes.value.data.settings || { rob_enabled: true, crime_enabled: true });
        setStats(ecoRes.value.data.stats || { total_currency: 0, accounts: 0 });
        setTopUsers(ecoRes.value.data.top_users || []);
      }

      if (rolesRes.status === 'fulfilled') {
        setRoles(rolesRes.value.data.roles || []);
      }
      setError('');
    } catch (err) {
      console.error('Failed to load economy data', err);
      setError(err.response?.data?.error || 'Failed to load economy data');
    } finally {
      setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/economy/settings`, settings);
      setSettingsSaved(true);
      setSuccess('Economy gameplay rules updated successfully!');
      setTimeout(() => setSettingsSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save settings');
    } finally {
      setSavingSettings(false);
    }
  };

  const handleAddItem = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/economy/shop`, form);
      setForm({ name: '', description: '', price: '', role_id: '' });
      setSuccess('Item published to server shop successfully!');
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add shop item');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteItem = async (itemId) => {
    if (!window.confirm('Are you sure you want to remove this item from the store?')) return;
    try {
      await api.delete(`/guilds/${guildId}/economy/shop/${itemId}`);
      setSuccess('Item removed from shop.');
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to remove item');
    }
  };

  const handleAdjustBalance = async (e) => {
    e.preventDefault();
    if (!adjustData.user_id.trim() || adjustData.amount < 0) {
      setError('Please provide a valid Discord User ID and non-negative amount.');
      return;
    }
    setAdjusting(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/economy/balance`, adjustData);
      setSuccess(`Account balance updated for user ${adjustData.user_id}!`);
      setShowAdjustModal(false);
      setAdjustData({ user_id: '', action: 'add', target: 'wallet', amount: 100 });
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to adjust balance');
    } finally {
      setAdjusting(false);
    }
  };

  const roleSelectOptions = [
    { value: '', label: 'None (Cosmetic / No role grant)' },
    ...roles.map(r => ({ value: r.id, label: `@${r.name}` }))
  ];

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
          <Skeleton height="90px" />
          <Skeleton height="90px" />
          <Skeleton height="90px" />
        </div>
        <Skeleton height="360px" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Coins}
        title="Economy & Marketplace"
        subtitle="Manage server coins, create custom shop items with automated role rewards, and govern economy gameplay rules."
        actions={
          <Button
            variant="primary"
            size="sm"
            icon={ArrowUpDown}
            onClick={() => setShowAdjustModal(true)}
          >
            Adjust Member Balance
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

      {/* Metrics Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        <Card style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Circulating Currency
              </div>
              <div style={{ fontSize: '26px', fontWeight: '700', color: '#f59e0b', marginTop: '4px' }}>
                {stats.total_currency?.toLocaleString() || 0}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Combined wallets & bank deposits
              </div>
            </div>
            <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' }}>
              <Coins size={22} />
            </div>
          </div>
        </Card>

        <Card style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Registered Wallets
              </div>
              <div style={{ fontSize: '26px', fontWeight: '700', color: 'var(--text-main)', marginTop: '4px' }}>
                {stats.accounts?.toLocaleString() || 0}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Active member bank accounts
              </div>
            </div>
            <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(88, 101, 242, 0.1)', color: 'var(--primary)' }}>
              <Users size={22} />
            </div>
          </div>
        </Card>

        <Card style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Store Catalogue
              </div>
              <div style={{ fontSize: '26px', fontWeight: '700', color: '#10b981', marginTop: '4px' }}>
                {items.length}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Items available for purchase
              </div>
            </div>
            <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
              <Store size={22} />
            </div>
          </div>
        </Card>
      </div>

      {/* Economy Gameplay Rules Card */}
      <Card>
        <CardHeader>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <CardTitle>Gameplay Rules & Commands</CardTitle>
              <CardDescription>Control which interactive economy risk commands members are permitted to use.</CardDescription>
            </div>
            <Button
              variant="primary"
              size="sm"
              icon={CheckCircle2}
              loading={savingSettings}
              onClick={handleSaveSettings}
            >
              {settingsSaved ? 'Saved!' : 'Save Rules'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
            <div style={{
              padding: '16px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)'
            }}>
              <Toggle
                checked={settings.rob_enabled}
                onChange={val => setSettings({ ...settings, rob_enabled: val })}
                label="Allow /eco rob"
                description="Members can attempt to steal pocket coins from other members with risk of failure."
              />
            </div>

            <div style={{
              padding: '16px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)'
            }}>
              <Toggle
                checked={settings.crime_enabled}
                onChange={val => setSettings({ ...settings, crime_enabled: val })}
                label="Allow /eco crime"
                description="Members can execute risky criminal actions for large coin rewards or hefty fines."
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Two Columns: Store Manager + Leaderboard */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(340px, 1.3fr) minmax(300px, 0.7fr)', gap: '24px' }}>
        {/* Left Column: Add Store Item & Store Catalogue */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <Card>
            <CardHeader>
              <CardTitle>Add Store Item</CardTitle>
              <CardDescription>Create an item that members can buy with their earned coins.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleAddItem} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                      Item Name
                    </label>
                    <input
                      type="text"
                      className="form-input"
                      value={form.name}
                      onChange={e => setForm({ ...form, name: e.target.value })}
                      placeholder="e.g. VIP Member Pass"
                      required
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                      Price (Coins)
                    </label>
                    <input
                      type="number"
                      className="form-input"
                      min={0}
                      value={form.price}
                      onChange={e => setForm({ ...form, price: e.target.value })}
                      placeholder="500"
                      required
                    />
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Item Description
                  </label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.description}
                    onChange={e => setForm({ ...form, description: e.target.value })}
                    placeholder="Describe the perks or purpose of this item..."
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Automated Role Reward
                  </label>
                  <Select
                    value={form.role_id}
                    onChange={val => setForm({ ...form, role_id: val })}
                    options={roleSelectOptions}
                    placeholder="Select optional role to assign on purchase..."
                    searchable
                  />
                  <p style={{ margin: '5px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                    If assigned, the bot will automatically grant this Discord role upon checkout.
                  </p>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
                  <Button type="submit" variant="primary" icon={Plus} loading={submitting}>
                    Add Item to Shop
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          {/* Current Shop Items */}
          <Card>
            <CardHeader>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <CardTitle>Active Store Catalogue</CardTitle>
                <Badge variant="primary" size="sm">{items.length} Items</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {items.length === 0 ? (
                <EmptyState
                  icon={Store}
                  title="No Items in Server Store"
                  description="Use the form above to add items, badges, or role rewards that your members can purchase."
                />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {items.map(item => {
                    const role = roles.find(r => String(r.id) === String(item.role_id));
                    return (
                      <div
                        key={item.id}
                        style={{
                          padding: '14px 16px',
                          borderRadius: 'var(--radius-md)',
                          background: 'var(--bg-surface)',
                          border: '1px solid var(--border)',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: '12px'
                        }}
                      >
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                            <span style={{ fontWeight: 600, fontSize: '14.5px', color: 'var(--text-main)' }}>
                              {item.name}
                            </span>
                            <Badge variant="warning" size="sm">
                              🪙 {item.price?.toLocaleString()}
                            </Badge>
                            {role && (
                              <Badge variant="primary" size="sm">
                                @{role.name}
                              </Badge>
                            )}
                          </div>
                          {item.description && (
                            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                              {item.description}
                            </span>
                          )}
                        </div>

                        <Button
                          variant="danger"
                          size="sm"
                          icon={Trash2}
                          onClick={() => handleDeleteItem(item.id)}
                        >
                          Remove
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Wealthiest Members Leaderboard */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle>Server Wealth Rankings</CardTitle>
              <CardDescription>Top balances recorded across all server members.</CardDescription>
            </CardHeader>
            <CardContent>
              {topUsers.length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13.5px' }}>
                  No member balances recorded yet.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {topUsers.map((u, i) => {
                    const isTop3 = i < 3;
                    return (
                      <div
                        key={u.user_id}
                        style={{
                          padding: '10px 14px',
                          borderRadius: 'var(--radius-sm)',
                          background: isTop3 ? 'rgba(255, 255, 255, 0.02)' : 'transparent',
                          border: '1px solid var(--border)',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center'
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <div style={{
                            width: '24px',
                            height: '24px',
                            borderRadius: '4px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '12px',
                            fontWeight: 700,
                            color: i === 0 ? '#fbbf24' : i === 1 ? '#94a3b8' : i === 2 ? '#b45309' : 'var(--text-muted)'
                          }}>
                            {i === 0 ? '1' : i === 1 ? '2' : i === 2 ? '3' : `${i + 1}`}
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: '13.5px', color: 'var(--text-main)' }}>
                              {u.username || `User ${u.user_id.slice(0, 6)}...`}
                            </div>
                            <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', display: 'flex', gap: '8px' }}>
                              <span>Wallet: {u.wallet?.toLocaleString()}</span>
                              <span>•</span>
                              <span>Bank: {u.bank?.toLocaleString()}</span>
                            </div>
                          </div>
                        </div>

                        <div style={{ fontWeight: 700, color: '#f59e0b', fontSize: '13.5px' }}>
                          {u.total?.toLocaleString()} 🪙
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Adjust Coins Modal */}
      <Modal
        isOpen={showAdjustModal}
        onClose={() => setShowAdjustModal(false)}
        title="Adjust Member Coins"
        maxWidth="460px"
      >
        <form onSubmit={handleAdjustBalance} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Discord User ID
            </label>
            <input
              type="text"
              className="form-input"
              value={adjustData.user_id}
              onChange={e => setAdjustData({ ...adjustData, user_id: e.target.value })}
              placeholder="e.g. 192837482910384756"
              required
            />
            <p style={{ margin: '5px 0 0', fontSize: '11.5px', color: 'var(--text-muted)' }}>
              Enable Developer Mode in Discord to right-click any member and copy their ID.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Action
              </label>
              <select
                className="form-input"
                value={adjustData.action}
                onChange={e => setAdjustData({ ...adjustData, action: e.target.value })}
              >
                <option value="add">Add (+)</option>
                <option value="remove">Remove (-)</option>
                <option value="set">Set Exact (=)</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Account Target
              </label>
              <select
                className="form-input"
                value={adjustData.target}
                onChange={e => setAdjustData({ ...adjustData, target: e.target.value })}
              >
                <option value="wallet">Wallet</option>
                <option value="bank">Bank Vault</option>
              </select>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Coin Amount
            </label>
            <input
              type="number"
              className="form-input"
              min={0}
              value={adjustData.amount}
              onChange={e => setAdjustData({ ...adjustData, amount: Number(e.target.value) })}
              required
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
            <Button type="button" variant="outline" onClick={() => setShowAdjustModal(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={adjusting}>
              Apply Balance Change
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default Economy;
