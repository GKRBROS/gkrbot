import { useEffect, useState } from 'react';
import { RefreshCw, CheckCircle2, AlertCircle, Server } from 'lucide-react';
import api from '../../api';
import Modal from '../../components/Modal';
import Button from '../../components/Button';

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
      }, 1800);
    } catch (err) {
      setResultMsg({
        type: 'error',
        text: err.response?.data?.error || 'Failed to sync settings to other servers.'
      });
    }
    setSyncing(false);
  };

  const footer = (
    <div className="flex items-center justify-end gap-3 w-full">
      <Button
        variant="ghost"
        onClick={onClose}
        disabled={syncing}
      >
        Cancel
      </Button>
      <Button
        variant="primary"
        onClick={handleSync}
        disabled={syncing || selectedGuilds.length === 0}
      >
        {syncing ? (
          <>
            <RefreshCw size={16} className="animate-spin" />
            <span>Syncing...</span>
          </>
        ) : (
          <>
            <RefreshCw size={16} />
            <span>Sync to {selectedGuilds.length} Server(s)</span>
          </>
        )}
      </Button>
    </div>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Sync ${moduleLabel}`}
      description="Copy current settings to your other managed Discord servers."
      maxWidth="520px"
      footer={footer}
    >
      <div className="flex flex-col gap-4">
        {resultMsg && (
          <div
            className={`p-3.5 rounded-xl border flex items-center gap-2.5 text-sm font-medium ${
              resultMsg.type === 'success'
                ? 'bg-success/10 border-success/30 text-success'
                : 'bg-danger/10 border-danger/30 text-danger'
            }`}
          >
            {resultMsg.type === 'success' ? (
              <CheckCircle2 size={18} className="shrink-0" />
            ) : (
              <AlertCircle size={18} className="shrink-0" />
            )}
            <span>{resultMsg.text}</span>
          </div>
        )}

        {loading ? (
          <div className="py-12 text-center text-muted text-sm flex flex-col items-center justify-center">
            <RefreshCw size={24} className="animate-spin mb-2 opacity-50 text-primary" />
            <span>Loading your servers...</span>
          </div>
        ) : guilds.length === 0 ? (
          <div className="py-10 text-center text-muted text-sm flex flex-col items-center justify-center">
            <Server size={32} className="mb-2 opacity-40" />
            <p>No other servers found where you have Administrator permissions.</p>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                Target Servers ({selectedGuilds.length} selected)
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSelectAll}
                className="text-xs text-primary hover:text-primary-hover p-0 h-auto"
              >
                {selectedGuilds.length === guilds.length ? 'Deselect All' : 'Select All'}
              </Button>
            </div>

            <div className="flex flex-col gap-2 max-h-[280px] overflow-y-auto pr-1">
              {guilds.map((guild) => {
                const isChecked = selectedGuilds.includes(guild.id);
                return (
                  <div
                    key={guild.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleToggle(guild.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') handleToggle(guild.id);
                    }}
                    className={`p-2.5 rounded-xl border flex items-center justify-between gap-3 cursor-pointer transition-all duration-150 ${
                      isChecked
                        ? 'bg-primary/10 border-primary/50 shadow-sm shadow-primary/5'
                        : 'bg-card-sub/50 hover:bg-card-sub border-border hover:border-border-hover'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {guild.icon ? (
                        <img
                          src={guild.icon}
                          alt=""
                          className="w-8 h-8 rounded-lg object-cover shrink-0"
                        />
                      ) : (
                        <div className="w-8 h-8 rounded-lg bg-primary/20 text-primary text-sm font-bold flex items-center justify-center shrink-0">
                          {guild.name.charAt(0)}
                        </div>
                      )}
                      <span className="text-sm font-semibold text-main truncate">
                        {guild.name}
                      </span>
                    </div>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => {}}
                      className="w-4 h-4 accent-primary cursor-pointer shrink-0"
                    />
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

export default SyncModal;
