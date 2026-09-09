import { useEffect, useState } from 'react';
import api from '../../api';

function SyncModal({ isOpen, onClose, currentGuildId, moduleName, moduleLabel }) {
  const [guilds, setGuilds] = useState([]);
  const [selectedGuilds, setSelectedGuilds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [resultMsg, setResultMsg] = useState(null);

  useEffect(() => {
    if (!isOpen) {
      setResultMsg(null);
      return;
    }
    const fetchAdminGuilds = async () => {
      setLoading(true);
      try {
        const res = await api.get('/users/@me');
        // Exclude current guild from the target list
        const otherGuilds = (res.data.guilds || []).filter(g => g.id !== currentGuildId);
        setGuilds(otherGuilds);
        // By default, do not preselect all to avoid accidental overwrites
        setSelectedGuilds([]);
      } catch (err) {
        console.error('Failed to load servers for sync:', err);
      }
      setLoading(false);
    };
    fetchAdminGuilds();
  }, [isOpen, currentGuildId]);

  if (!isOpen) return null;

  const handleToggle = (id) => {
    setSelectedGuilds(prev =>
      prev.includes(id) ? prev.filter(gId => gId !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    if (selectedGuilds.length === guilds.length) {
      setSelectedGuilds([]);
    } else {
      setSelectedGuilds(guilds.map(g => g.id));
    }
  };

  const handleSync = async () => {
    if (selectedGuilds.length === 0) return;
    setSyncing(true);
    setResultMsg(null);
    try {
      const res = await api.post(`/guilds/${currentGuildId}/sync`, {
        target_guild_ids: selectedGuilds,
        modules: [moduleName]
      });
      setResultMsg({
        type: 'success',
        text: `Successfully synced ${moduleLabel} to ${res.data.synced_servers} server(s)!`
      });
      setTimeout(() => {
        onClose();
      }, 2000);
    } catch (err) {
      setResultMsg({
        type: 'error',
        text: err.response?.data?.error || 'Failed to sync settings to other servers.'
      });
    }
    setSyncing(false);
  };

  return (
    <div className="modal-overlay">
      <div className="card glass-panel animate-fade-in" style={{
        width: '100%',
        maxWidth: '520px',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,0.8)',
        border: '1px solid rgba(88,101,242,0.3)',
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 24px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>🔄</span> Sync {moduleLabel}
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
              Copy current settings to your other managed Discord servers.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              fontSize: '20px',
              cursor: 'pointer',
              padding: '4px 8px'
            }}
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
          {resultMsg && (
            <div style={{
              padding: '12px 16px',
              borderRadius: '8px',
              marginBottom: '16px',
              fontSize: '13px',
              background: resultMsg.type === 'success' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
              border: `1px solid ${resultMsg.type === 'success' ? 'var(--success)' : 'var(--danger)'}`,
              color: resultMsg.type === 'success' ? 'var(--success)' : 'var(--danger)'
            }}>
              {resultMsg.text}
            </div>
          )}

          {loading ? (
            <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
              Loading your other servers...
            </div>
          ) : guilds.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
              No other servers found where you have Administrator permissions.
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-sub)' }}>
                  Target Servers ({selectedGuilds.length} selected)
                </span>
                <button
                  type="button"
                  onClick={handleSelectAll}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--primary)',
                    fontSize: '13px',
                    cursor: 'pointer',
                    fontWeight: 600
                  }}
                >
                  {selectedGuilds.length === guilds.length ? 'Deselect All' : 'Select All'}
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '280px', overflowY: 'auto' }}>
                {guilds.map(guild => {
                  const isChecked = selectedGuilds.includes(guild.id);
                  return (
                    <div
                      key={guild.id}
                      onClick={() => handleToggle(guild.id)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '10px 14px',
                        borderRadius: '8px',
                        background: isChecked ? 'rgba(88,101,242,0.12)' : 'rgba(255,255,255,0.03)',
                        border: `1px solid ${isChecked ? 'var(--primary)' : 'var(--border)'}`,
                        cursor: 'pointer',
                        transition: 'all 0.15s'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        {guild.icon ? (
                          <img src={guild.icon} alt="" style={{ width: '32px', height: '32px', borderRadius: '8px', objectFit: 'cover' }} />
                        ) : (
                          <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>
                            {guild.name.charAt(0)}
                          </div>
                        )}
                        <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-main)' }}>
                          {guild.name}
                        </span>
                      </div>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}} // Handled by container onClick
                        style={{ cursor: 'pointer', width: '16px', height: '16px', accentColor: 'var(--primary)' }}
                      />
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '16px 24px',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '12px'
        }}>
          <button
            type="button"
            onClick={onClose}
            className="btn"
            style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-sub)' }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSync}
            disabled={syncing || selectedGuilds.length === 0}
            className="btn btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            {syncing ? 'Syncing...' : `Sync to ${selectedGuilds.length} Server(s)`}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SyncModal;
