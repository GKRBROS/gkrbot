import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';

const MODULE_OPTIONS = [
  { id: 'welcome', label: '👋 Welcome & Leave Setup', desc: 'Welcome and leave messages, image attachments, and channel configs' },
  { id: 'security', label: '🛡️ Security & Anti-Spam', desc: 'Message limits, time windows, mass mention limits, and image scanner' },
  { id: 'sticky', label: '📌 Sticky Messages', desc: 'Channel stickies (matches channels by name on target servers)' },
  { id: 'autoreact', label: '⚡ Auto Reactions', desc: 'Emoji reaction triggers (matches channels by name on target servers)' },
  { id: 'tickets', label: '🎫 Tickets System', desc: 'Ticket categories and transcript log channel (channels matched by name)' },
  { id: 'streamalerts', label: '📺 Stream Alerts', desc: 'YouTube / Twitch / Kick alerts (notification channels matched by name)' },
  { id: 'moderation', label: '⚖️ Staff Roles & Moderation', desc: 'Designated staff roles (matched by role name on target servers)' },
];

function ServerSync() {
  const { guildId } = useParams();
  const [guilds, setGuilds] = useState([]);
  const [currentGuild, setCurrentGuild] = useState(null);
  const [selectedModules, setSelectedModules] = useState(['welcome', 'security', 'sticky', 'autoreact']);
  const [selectedGuilds, setSelectedGuilds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    const loadGuilds = async () => {
      try {
        const res = await api.get('/users/@me');
        const allGuilds = res.data.guilds || [];
        const current = allGuilds.find(g => g.id === guildId);
        setCurrentGuild(current);
        const others = allGuilds.filter(g => g.id !== guildId);
        setGuilds(others);
      } catch (err) {
        console.error('Failed to load servers for sync:', err);
      }
      setLoading(false);
    };
    loadGuilds();
  }, [guildId]);

  const toggleModule = (id) => {
    setSelectedModules(prev =>
      prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id]
    );
  };

  const toggleGuild = (id) => {
    setSelectedGuilds(prev =>
      prev.includes(id) ? prev.filter(gId => gId !== id) : [...prev, id]
    );
  };

  const handleSelectAllGuilds = () => {
    if (selectedGuilds.length === guilds.length) {
      setSelectedGuilds([]);
    } else {
      setSelectedGuilds(guilds.map(g => g.id));
    }
  };

  const handleSelectAllModules = () => {
    if (selectedModules.length === MODULE_OPTIONS.length) {
      setSelectedModules([]);
    } else {
      setSelectedModules(MODULE_OPTIONS.map(m => m.id));
    }
  };

  const handleExecuteSync = async () => {
    if (selectedGuilds.length === 0 || selectedModules.length === 0) return;
    setSyncing(true);
    setResult(null);
    try {
      const res = await api.post(`/guilds/${guildId}/sync`, {
        target_guild_ids: selectedGuilds,
        modules: selectedModules
      });
      setResult({
        type: 'success',
        text: `✓ Successfully synced ${selectedModules.length} module(s) across ${res.data.synced_servers} target server(s)!`
      });
    } catch (err) {
      setResult({
        type: 'error',
        text: err.response?.data?.error || 'Failed to sync settings. Please try again.'
      });
    }
    setSyncing(false);
  };

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
      {/* Header */}
      <div className="page-header" style={{ marginBottom: '24px' }}>
        <h2 className="page-title">
          <span>🔄</span> Multi-Server Settings Sync
        </h2>
        <p className="page-subtitle">
          Replicate and keep settings identical across multiple Discord servers in a single click.
        </p>
      </div>

      {result && (
        <div style={{
          padding: '14px 18px',
          borderRadius: '10px',
          marginBottom: '24px',
          background: result.type === 'success' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
          border: `1px solid ${result.type === 'success' ? 'var(--success)' : 'var(--danger)'}`,
          color: result.type === 'success' ? 'var(--success)' : 'var(--danger)',
          fontWeight: 500,
          fontSize: '14px'
        }}>
          {result.text}
        </div>
      )}

      {/* Source Server Banner */}
      <div className="card glass-panel flex items-center justify-between" style={{
        marginBottom: '28px',
        padding: '18px 24px',
        background: 'linear-gradient(135deg, rgba(88,101,242,0.12) 0%, rgba(0,212,255,0.05) 100%)',
        border: '1px solid rgba(88,101,242,0.3)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          {currentGuild?.icon ? (
            <img src={currentGuild.icon} alt="" style={{ width: '48px', height: '48px', borderRadius: '12px' }} />
          ) : (
            <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '20px', fontWeight: 'bold' }}>
              {currentGuild?.name?.charAt(0) || 'G'}
            </div>
          )}
          <div>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '1px', color: 'var(--accent)', fontWeight: 700 }}>
              SOURCE SERVER (MASTER)
            </span>
            <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-main)' }}>
              {currentGuild?.name}
            </div>
          </div>
        </div>
        <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
          Settings will be copied <strong>FROM</strong> this server.
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px', marginBottom: '32px' }}>
        {/* Step 1: Select Modules */}
        <div className="card glass-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>1️⃣</span> Select Modules to Clone
            </h3>
            <button
              type="button"
              onClick={handleSelectAllModules}
              style={{ background: 'transparent', border: 'none', color: 'var(--primary)', fontSize: '12px', cursor: 'pointer', fontWeight: 600 }}
            >
              {selectedModules.length === MODULE_OPTIONS.length ? 'Deselect All' : 'Select All'}
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {MODULE_OPTIONS.map(mod => {
              const isChecked = selectedModules.includes(mod.id);
              return (
                <div
                  key={mod.id}
                  onClick={() => toggleModule(mod.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: '12px',
                    padding: '12px 14px',
                    borderRadius: '8px',
                    background: isChecked ? 'rgba(88,101,242,0.12)' : 'rgba(255,255,255,0.02)',
                    border: `1px solid ${isChecked ? 'var(--primary)' : 'var(--border)'}`,
                    cursor: 'pointer',
                    transition: 'all 0.15s'
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-main)' }}>
                      {mod.label}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      {mod.desc}
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {}}
                    style={{ width: '16px', height: '16px', accentColor: 'var(--primary)', cursor: 'pointer', marginTop: '3px' }}
                  />
                </div>
              );
            })}
          </div>
        </div>

        {/* Step 2: Select Target Servers */}
        <div className="card glass-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>2️⃣</span> Select Target Servers ({selectedGuilds.length})
            </h3>
            {guilds.length > 0 && (
              <button
                type="button"
                onClick={handleSelectAllGuilds}
                style={{ background: 'transparent', border: 'none', color: 'var(--primary)', fontSize: '12px', cursor: 'pointer', fontWeight: 600 }}
              >
                {selectedGuilds.length === guilds.length ? 'Deselect All' : 'Select All'}
              </button>
            )}
          </div>

          {guilds.length === 0 ? (
            <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              You don&apos;t have any other servers where you are an Administrator and where the bot is invited.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '360px', overflowY: 'auto' }}>
              {guilds.map(guild => {
                const isChecked = selectedGuilds.includes(guild.id);
                return (
                  <div
                    key={guild.id}
                    onClick={() => toggleGuild(guild.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      borderRadius: '8px',
                      background: isChecked ? 'rgba(88,101,242,0.12)' : 'rgba(255,255,255,0.02)',
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
                      onChange={() => {}}
                      style={{ cursor: 'pointer', width: '16px', height: '16px', accentColor: 'var(--primary)' }}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Action Bar */}
      <div className="card glass-panel flex items-center justify-between" style={{ padding: '20px 24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: '15px' }}>
            Ready to synchronize?
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            This will overwrite the selected modules on {selectedGuilds.length} target server(s) with the master settings from {currentGuild?.name}.
          </div>
        </div>

        <button
          type="button"
          onClick={handleExecuteSync}
          disabled={syncing || selectedGuilds.length === 0 || selectedModules.length === 0}
          className="btn btn-primary"
          style={{
            padding: '12px 28px',
            fontSize: '15px',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          {syncing ? 'Synchronizing Servers...' : `⚡ Clone & Sync to ${selectedGuilds.length} Server(s)`}
        </button>
      </div>
    </div>
  );
}

export default ServerSync;
