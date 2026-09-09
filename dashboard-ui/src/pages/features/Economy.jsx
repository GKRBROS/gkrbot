import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select } from '../../components/Select';

function Economy() {
  const { guildId } = useParams();
  const [items, setItems] = useState([]);
  const [settings, setSettings] = useState({ rob_enabled: true, crime_enabled: true });
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ name: '', description: '', price: '', role_id: '' });

  const fetchData = useCallback(async () => {
    try {
      const [ecoRes, rolesRes] = await Promise.all([
        api.get(`/guilds/${guildId}/economy`),
        api.get(`/guilds/${guildId}/roles`),
      ]);
      setItems(ecoRes.data.shop_items || []);
      setSettings(ecoRes.data.settings || { rob_enabled: true, crime_enabled: true });
      setRoles(rolesRes.data.roles || []);
    } catch (err) {
      console.error('Failed to load economy data', err);
    }
    setLoading(false);
  }, [guildId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      await api.post(`/guilds/${guildId}/economy/settings`, settings);
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save settings');
    }
    setSavingSettings(false);
  };

  const handleAddItem = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await api.post(`/guilds/${guildId}/economy/shop`, form);
      setForm({ name: '', description: '', price: '', role_id: '' });
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add shop item');
    }
    setSubmitting(false);
  };

  const handleDeleteItem = async (itemId) => {
    if (!window.confirm('Remove this item from the shop?')) return;
    try {
      await api.delete(`/guilds/${guildId}/economy/shop/${itemId}`);
      await fetchData();
    } catch (err) {
      console.error('Failed to remove item', err);
    }
  };

  const getRoleName = (id) => roles.find(r => r.id === id)?.name || null;

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '300px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h2 className="page-title"><span>🪙</span> Economy</h2>
        <p className="page-subtitle">Configure the economy system and manage the server shop (members use /eco commands).</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {/* Settings */}
      <div className="glass-panel" style={{ padding: '24px', marginBottom: '32px' }}>
        <h3 className="section-title" style={{ marginBottom: '6px', border: 'none', padding: 0 }}>⚙️ Economy Settings</h3>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '18px' }}>Toggle which risky economy features are available on this server.</p>

        <div className="toggle-wrapper" style={{ marginBottom: '12px' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: '14px' }}>🔪 Allow Robbing</div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '3px' }}>Members can rob coins from each other with /eco rob.</div>
          </div>
          <button
            type="button"
            className={`toggle ${settings.rob_enabled ? 'active' : ''}`}
            onClick={() => setSettings(s => ({ ...s, rob_enabled: !s.rob_enabled }))}
            aria-label="Toggle robbing"
          ></button>
        </div>

        <div className="toggle-wrapper" style={{ marginBottom: '18px' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: '14px' }}>🚔 Allow Crime</div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '3px' }}>Members can try their luck with /eco crime.</div>
          </div>
          <button
            type="button"
            className={`toggle ${settings.crime_enabled ? 'active' : ''}`}
            onClick={() => setSettings(s => ({ ...s, crime_enabled: !s.crime_enabled }))}
            aria-label="Toggle crime"
          ></button>
        </div>

        <div className="flex justify-end">
          <button onClick={handleSaveSettings} className={`btn ${settingsSaved ? 'btn-success' : 'btn-primary'}`} disabled={savingSettings}>
            {settingsSaved ? '✅ Saved!' : (savingSettings ? 'Saving...' : 'Save Settings')}
          </button>
        </div>
      </div>

      {/* Add shop item */}
      <div className="glass-panel" style={{ padding: '24px', marginBottom: '32px', border: '1px solid var(--primary)' }}>
        <h3 className="section-title" style={{ marginBottom: '18px', border: 'none', padding: 0 }}>🛒 Add Shop Item</h3>
        <form onSubmit={handleAddItem}>
          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Item Name</label>
              <input type="text" className="input-field" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. VIP Role" required />
            </div>
            <div className="form-group">
              <label className="form-label">Price (coins)</label>
              <input type="number" min="0" className="input-field" value={form.price} onChange={e => setForm({ ...form, price: e.target.value })} placeholder="e.g. 5000" required />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="input-field" rows={2} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="What does the buyer get?" required />
          </div>
          <div className="grid-2" style={{ alignItems: 'end' }}>
            <div className="form-group">
              <label className="form-label">Role Granted on Purchase (optional)</label>
              <Select
                value={form.role_id}
                onChange={v => setForm({ ...form, role_id: v })}
                options={[{ value: '', label: 'None (no role granted)' }, ...roles.map(r => ({ value: r.id, label: r.name }))]}
                placeholder="Select a role..."
                searchable
              />
            </div>
            <div className="flex justify-end">
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? 'Adding...' : '➕ Add Item'}
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Shop items */}
      <div className="section-header">
        <h3 className="section-title">Shop Items <span className="section-count">{items.length}</span></h3>
      </div>

      {items.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">🛒</div>
          <h3 className="empty-state-title">The shop is empty</h3>
          <p className="empty-state-desc">Add items above so members can spend their coins with /eco shop.</p>
        </div>
      ) : (
        <div className="grid-auto stagger">
          {items.map(item => (
            <div key={item.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div className="flex items-center justify-between">
                <span style={{ fontWeight: 700, fontSize: '15px', color: 'var(--text-main)' }}>{item.name}</span>
                <button onClick={() => handleDeleteItem(item.id)} className="btn btn-icon btn-ghost" style={{ color: 'var(--danger)', padding: '6px' }} title="Remove">🗑️</button>
              </div>
              <p style={{ fontSize: '13px', color: 'var(--text-sub)', lineHeight: '1.6', flex: 1 }}>{item.description}</p>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: '10px', gap: '8px', flexWrap: 'wrap' }}>
                <span className="badge badge-warning">🪙 {Number(item.price).toLocaleString()}</span>
                {item.role_id && (
                  <span className="badge badge-primary" title={item.role_id}>
                    🎭 {getRoleName(item.role_id) || 'Role'}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Economy;
