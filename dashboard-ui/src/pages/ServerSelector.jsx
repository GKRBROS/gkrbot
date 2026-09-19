import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { Button } from '../components/Button';
import { Badge } from '../components/Badge';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/Skeleton';
import { Search, Server, Plus, ArrowRight, ShieldCheck } from 'lucide-react';

export function ServerSelector() {
  const [guilds, setGuilds] = useState([]);
  const [botClientId, setBotClientId] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchGuilds = async () => {
      try {
        const res = await api.get('/users/@me');
        setGuilds(res.data.guilds || []);
        if (res.data.bot_client_id) {
          setBotClientId(res.data.bot_client_id);
        }
      } catch (err) {
        console.error('Failed to fetch guilds', err);
      } finally {
        setLoading(false);
      }
    };
    fetchGuilds();
  }, []);

  const filtered = guilds.filter(g =>
    g.name.toLowerCase().includes(search.trim().toLowerCase())
  );

  return (
    <div className="animate-fade-in max-w-5xl mx-auto px-6 py-14">
      {/* Header */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-medium text-primary mb-4">
          <ShieldCheck size={14} />
          <span>{guilds.length > 0 ? `${guilds.length} Server${guilds.length === 1 ? '' : 's'} Authorized` : 'Your Servers'}</span>
        </div>
        <h1 className="text-3xl font-bold text-main mb-2">Select a Server</h1>
        <p className="text-sm text-muted max-w-md mx-auto">
          Choose a Discord server below to configure features, automations, and moderation tools.
        </p>
      </div>

      {/* Search & Actions Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 max-w-2xl mx-auto mb-8">
        <div className="relative w-full">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            className="input-field pl-10 text-sm"
            placeholder="Search your servers..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {botClientId && (
          <a
            href={`https://discord.com/api/oauth2/authorize?client_id=${botClientId}&permissions=8&scope=bot%20applications.commands`}
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary shrink-0 text-sm"
          >
            <Plus size={15} />
            <span>Invite to Server</span>
          </a>
        )}
      </div>

      {/* Content */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="card p-5">
              <div className="flex items-center gap-4">
                <Skeleton width="48px" height="48px" rounded="lg" />
                <div className="flex-1">
                  <Skeleton width="70%" height="16px" style={{ marginBottom: '8px' }} />
                  <Skeleton width="40%" height="12px" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : guilds.length === 0 ? (
        <EmptyState
          icon={Server}
          title="No Servers Found"
          description="You don't appear to have Administrator permissions on any server where this bot is present."
          action={
            botClientId && (
              <a
                href={`https://discord.com/api/oauth2/authorize?client_id=${botClientId}&permissions=8&scope=bot%20applications.commands`}
                target="_blank"
                rel="noreferrer"
                className="btn btn-primary"
              >
                <Plus size={16} />
                <span>Invite Bot to a Server</span>
              </a>
            )
          }
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No Matching Servers"
          description={`No servers found matching "${search}".`}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(guild => (
            <Link
              key={guild.id}
              to={`/dashboard/${guild.id}`}
              className="card card-hover p-4 flex items-center justify-between gap-4 group no-underline text-inherit"
            >
              <div className="flex items-center gap-3.5 min-w-0">
                {guild.icon ? (
                  <img
                    src={guild.icon}
                    alt={guild.name}
                    className="w-12 h-12 rounded-xl object-cover border border-border shrink-0"
                  />
                ) : (
                  <div className="w-12 h-12 rounded-xl bg-surface border border-border flex items-center justify-center font-bold text-sm text-sub shrink-0">
                    {guild.name.charAt(0).toUpperCase()}
                  </div>
                )}

                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-main truncate group-hover:text-primary transition-colors">
                    {guild.name}
                  </h3>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />
                    <span className="text-xs text-muted">Ready to manage</span>
                  </div>
                </div>
              </div>

              <div className="w-8 h-8 rounded-lg bg-surface border border-border flex items-center justify-center text-muted group-hover:text-primary group-hover:border-primary/40 transition-colors shrink-0">
                <ArrowRight size={15} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default ServerSelector;
