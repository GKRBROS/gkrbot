import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

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
      const [ecoRes, rolesRes] = await Promise.all([
        api.get(`/guilds/${guildId}/economy`),
        api.get(`/guilds/${guildId}/roles`),
      ]);
      setItems(ecoRes.data.shop_items || []);
      setSettings(ecoRes.data.settings || { rob_enabled: true, crime_enabled: true });
      setStats(ecoRes.data.stats || { total_currency: 0, accounts: 0 });
      setTopUsers(ecoRes.data.top_users || []);
      setRoles(rolesRes.data.roles || []);
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
      setSuccess('Economy settings saved successfully!');
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
      setSuccess('Shop item added successfully!');
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add shop item');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteItem = async (itemId) => {
    if (!window.confirm('Remove this item from the shop?')) return;
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
      setError('Please provide a valid User ID and amount.');
      return;
    }
    setAdjusting(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/economy/balance`, adjustData);
      setSuccess(`Balance updated for user ${adjustData.user_id}!`);
      setShowAdjustModal(false);
      setAdjustData({ user_id: '', action: 'add', target: 'wallet', amount: 100 });
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to adjust balance');
    } finally {
      setAdjusting(false);
    }
  };

  const roleSelectOptions = [{ value: '', label: 'None (No role reward)' }, ...roles.map(r => ({ value: r.id, label: `@${r.name}` }))];

  if (loading) {
    return <div className="feature-page" style={{ padding: '40px', textAlign: 'center' }}>Loading Economy System...</div>;
  }

  return (
    <div className="feature-page">
      <div className="feature-header">
        <div>
          <h1 className="feature-title">🪙 Economy & Shop</h1>
          <p className="feature-desc">Server economy currency, custom store items, role purchases, and member balance controls.</p>
        </div>
        <button className="btn-primary" onClick={() => setShowAdjustModal(true)}>
          🪙 Adjust Member Coins
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

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div className="dashboard-card" style={{ padding: '20px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700' }}>Circulating Currency</div>
          <div style={{ fontSize: '26px', fontWeight: '800', color: '#f59e0b', marginTop: '6px' }}>
            🪙 {stats.total_currency?.toLocaleString() || 0}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>Combined wallets + banks</div>
        </div>

        <div className="dashboard-card" style={{ padding: '20px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700' }}>Active Accounts</div>
          <div style={{ fontSize: '26px', fontWeight: '800', color: 'var(--text-main)', marginTop: '6px' }}>
            {stats.accounts?.toLocaleString() || 0}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>Registered members with coins</div>
        </div>

        <div className="dashboard-card" style={{ padding: '20px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700' }}>Shop Items</div>
          <div style={{ fontSize: '26px', fontWeight: '800', color: 'var(--primary)', marginTop: '6px' }}>
            {items.length}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>Items available for purchase</div>
        </div>
      </div>

      {/* Economy Gameplay Settings */}
      <div className="dashboard-card" style={{ padding: '24px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '18px' }}>⚙️ Command Permissions</h3>
            <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>Toggle risky commands for server members.</p>
          </div>
          <button className="btn-primary" onClick={handleSaveSettings} disabled={savingSettings}>
            {savingSettings ? 'Saving...' : settingsSaved ? '✓ Saved' : 'Save Settings'}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '8px' }}>
            <input
              type="checkbox"
              checked={settings.rob_enabled}
              onChange={e => setSettings({ ...settings, rob_enabled: e.target.checked })}
            />
            <div>
              <div style={{ fontWeight: '600', fontSize: '14px' }}>Allow /eco rob</div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Members can attempt to rob wallet coins from each other.</div>
            </div>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '8px' }}>
            <input
              type="checkbox"
              checked={settings.crime_enabled}
              onChange={e => setSettings({ ...settings, crime_enabled: e.target.checked })}
            />
            <div>
              <div style={{ fontWeight: '600', fontSize: '14px' }}>Allow /eco crime</div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Members can commit high-risk crimes for big payouts or fines.</div>
            </div>
          </label>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '24px' }}>
        {/* Shop Items Manager */}
        <div>
          <div className="dashboard-card" style={{ padding: '24px', marginBottom: '24px' }}>
            <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>Add Store Item</h3>
            <form onSubmit={handleAddItem} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">Item Name</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g. VIP Role Pass"
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Price (Coins)</label>
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

              <div className="form-group">
                <label className="form-label">Description</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="What does this item grant or do?"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Role Reward (Automatically granted on purchase)</label>
                <Select
                  value={form.role_id}
                  onChange={val => setForm({ ...form, role_id: val })}
                  options={roleSelectOptions}
                  placeholder="None"
                  searchable
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Adding...' : '+ Add Item to Shop'}
                </button>
              </div>
            </form>
          </div>

          {/* Current Shop Items */}
          <div className="dashboard-card" style={{ padding: '24px' }}>
            <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>Store Catalogue ({items.length})</h3>
            {items.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                No items in the server shop yet.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {items.map(item => {
                  const role = roles.find(r => String(r.id) === String(item.role_id));
                  return (
                    <div
                      key={item.id}
                      style={{
                        padding: '14px 18px',
                        borderRadius: '8px',
                        background: 'rgba(255,255,255,0.03)',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontWeight: '700', fontSize: '16px', color: 'var(--text-main)' }}>{item.name}</span>
                          <span className="badge badge-warning" style={{ fontSize: '12px' }}>🪙 {item.price?.toLocaleString()}</span>
                          {role && <span className="badge badge-primary">@{role.name}</span>}
                        </div>
                        {item.description && (
                          <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>{item.description}</div>
                        )}
                      </div>

                      <button className="btn-danger" onClick={() => handleDeleteItem(item.id)} style={{ padding: '6px 12px', fontSize: '12px' }}>
                        Remove
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Top Earners / Richest Members */}
        <div>
          <div className="dashboard-card" style={{ padding: '24px' }}>
            <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>Top Richest Members</h3>
            {topUsers.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>
                No balances recorded yet.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {topUsers.map((u, i) => (
                  <div
                    key={u.user_id}
                    style={{
                      padding: '10px 14px',
                      borderRadius: '8px',
                      background: 'rgba(255,255,255,0.02)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontWeight: '700', color: i < 3 ? 'var(--primary)' : 'var(--text-muted)', width: '20px' }}>
                        {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`}
                      </span>
                      <div>
                        <div style={{ fontWeight: '600', fontSize: '14px', color: 'var(--text-main)' }}>{u.username}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Wallet: {u.wallet?.toLocaleString()} • Bank: {u.bank?.toLocaleString()}</div>
                      </div>
                    </div>

                    <div style={{ fontWeight: '700', color: '#f59e0b', fontSize: '14px' }}>
                      🪙 {u.total?.toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Adjust Coins Modal */}
      {showAdjustModal && (
        <div className="modal-overlay" onClick={() => setShowAdjustModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '460px' }}>
            <h3 style={{ marginTop: 0 }}>Adjust Member Coins</h3>
            <form onSubmit={handleAdjustBalance} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group">
                <label className="form-label">Discord User ID</label>
                <input
                  type="text"
                  className="form-input"
                  value={adjustData.user_id}
                  onChange={e => setAdjustData({ ...adjustData, user_id: e.target.value })}
                  placeholder="e.g. 192837482910384756"
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">Action</label>
                  <select
                    className="form-input"
                    value={adjustData.action}
                    onChange={e => setAdjustData({ ...adjustData, action: e.target.value })}
                  >
                    <option value="add">Add Coins (+)</option>
                    <option value="remove">Remove Coins (-)</option>
                    <option value="set">Set Exact Amount (=)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Target Account</label>
                  <select
                    className="form-input"
                    value={adjustData.target}
                    onChange={e => setAdjustData({ ...adjustData, target: e.target.value })}
                  >
                    <option value="wallet">Wallet</option>
                    <option value="bank">Bank</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Amount</label>
                <input
                  type="number"
                  className="form-input"
                  min={0}
                  value={adjustData.amount}
                  onChange={e => setAdjustData({ ...adjustData, amount: Number(e.target.value) })}
                  required
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '14px' }}>
                <button type="button" className="btn-secondary" onClick={() => setShowAdjustModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={adjusting}>
                  {adjusting ? 'Saving...' : 'Apply Coins'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Economy;
