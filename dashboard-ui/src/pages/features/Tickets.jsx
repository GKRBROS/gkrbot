import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Ticket,
  Plus,
  FolderKanban,
  Send,
  Inbox,
  Sliders,
  Shield,
  Trash2,
  Edit3,
  RefreshCw,
  Hash,
  User,
  CheckCircle2,
  AlertCircle,
  Clock,
  ExternalLink,
  ChevronRight,
  Palette
} from 'lucide-react';
import api from '../../api';
import { withSync, syncParams } from '../../sync';
import { Select, MultiSelect } from '../../components/Select';
import PageHeader from '../../components/PageHeader';
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from '../../components/Card';
import Button from '../../components/Button';
import Badge from '../../components/Badge';
import Modal from '../../components/Modal';
import EmptyState from '../../components/EmptyState';
import Skeleton from '../../components/Skeleton';

function Tickets() {
  const { guildId } = useParams();
  const [activeTab, setActiveTab] = useState('categories'); // 'categories' | 'hub' | 'tickets' | 'settings'

  const [categories, setCategories] = useState([]);
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [stats, setStats] = useState({ categories_count: 0, total_tickets: 0, open_tickets: 0, closed_tickets: 0, hubs_count: 0 });
  const [activeTickets, setActiveTickets] = useState([]);
  const [logChannelId, setLogChannelId] = useState('');
  const [logChannelSaved, setLogChannelSaved] = useState(false);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Category modal
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({
    name: '',
    button_label: '',
    button_emoji: '🎫',
    embed_title: 'Support Ticket',
    embed_description: '',
  });
  const [pingRoles, setPingRoles] = useState([]);
  const [adminRoles, setAdminRoles] = useState([]);

  // Hub Builder State
  const [hubTitle, setHubTitle] = useState('Support Ticket Hub');
  const [hubDesc, setHubDesc] = useState('Need assistance with our community or services? Select the appropriate category below to open a private ticket with our staff team.');
  const [hubColor, setHubColor] = useState('#5865F2');
  const [hubFooter, setHubFooter] = useState('Support System • Fast Response Guaranteed');
  const [hubChannelId, setHubChannelId] = useState('');
  const [selectedHubCats, setSelectedHubCats] = useState([]);
  const [publishingHub, setPublishingHub] = useState(false);

  const EMPTY_FORM = {
    name: '',
    button_label: '',
    button_emoji: '🎫',
    embed_title: 'Support Ticket',
    embed_description: '',
  };

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [ticketsRes, channelsRes, rolesRes, statsRes, listRes] = await Promise.allSettled([
        api.get(`/guilds/${guildId}/tickets`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/roles`),
        api.get(`/guilds/${guildId}/tickets/stats`),
        api.get(`/guilds/${guildId}/tickets/list`),
      ]);

      if (ticketsRes.status === 'fulfilled') {
        const cats = ticketsRes.value.data.categories || [];
        setCategories(cats);
        setLogChannelId(ticketsRes.value.data.log_channel_id || '');
        setSelectedHubCats(prev => (prev.length ? prev : cats.map(c => c.id)));
      }

      if (channelsRes.status === 'fulfilled') {
        setChannels(channelsRes.value.data.channels || []);
      }

      if (rolesRes.status === 'fulfilled') {
        setRoles(rolesRes.value.data.roles || []);
      }

      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value.data || {});
      }

      if (listRes.status === 'fulfilled') {
        setActiveTickets(listRes.value.data.tickets || []);
      }
    } catch (err) {
      console.error('Failed to load tickets data', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddCategory = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      const payload = { ...form, ping_roles: pingRoles.join(', '), admin_roles: adminRoles.join(', ') };
      if (editingId) {
        await api.put(`/guilds/${guildId}/tickets/categories/${editingId}`, withSync(payload));
        setSuccess('Category updated successfully!');
      } else {
        await api.post(`/guilds/${guildId}/tickets`, withSync(payload));
        setSuccess('Category created successfully!');
      }
      await fetchData();
      setShowForm(false);
      setEditingId(null);
      setForm(EMPTY_FORM);
      setPingRoles([]);
      setAdminRoles([]);
    } catch (err) {
      setError(err.response?.data?.error || (editingId ? 'Failed to update category' : 'Failed to create category'));
    }
    setSubmitting(false);
  };

  const handleEditCategory = (cat) => {
    setEditingId(cat.id);
    setForm({
      name: cat.name || '',
      button_label: cat.button_label || '',
      button_emoji: cat.button_emoji || '🎫',
      embed_title: cat.embed_title || '',
      embed_description: cat.embed_description || '',
    });
    setPingRoles(cat.ping_roles ? cat.ping_roles.split(',').map(s => s.trim()).filter(Boolean) : []);
    setAdminRoles(cat.admin_roles ? cat.admin_roles.split(',').map(s => s.trim()).filter(Boolean) : []);
    setShowForm(true);
  };

  const handleDeleteCategory = async (catId) => {
    if (!window.confirm('Delete this ticket category? Active tickets under this category may become unmanaged.')) return;
    try {
      await api.delete(`/guilds/${guildId}/tickets/${catId}${syncParams()}`);
      await fetchData();
      setSuccess('Category deleted successfully.');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete category');
    }
  };

  const handleSaveLogChannel = async () => {
    try {
      await api.post(`/guilds/${guildId}/tickets/log-channel`, withSync({ channel_id: logChannelId }));
      setLogChannelSaved(true);
      setTimeout(() => setLogChannelSaved(false), 3000);
      setSuccess('Ticket transcript log channel updated!');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save log channel');
    }
  };

  const handlePublishHub = async (e) => {
    e.preventDefault();
    if (!hubChannelId) {
      setError('Please select a destination channel for the ticket hub.');
      return;
    }
    if (!selectedHubCats.length) {
      setError('Please select at least one ticket category to include in the hub.');
      return;
    }
    setPublishingHub(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/guilds/${guildId}/tickets/hub`, {
        channel_id: hubChannelId,
        category_ids: selectedHubCats,
        title: hubTitle,
        description: hubDesc,
        embed_color: hubColor,
        footer: hubFooter,
      });
      setSuccess('Ticket Hub panel deployed to Discord successfully!');
      fetchData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to publish ticket hub');
    } finally {
      setPublishingHub(false);
    }
  };

  const channelOptions = channels.map(c => ({ value: c.id, label: `#${c.name}` }));
  const roleOptions = roles.map(r => ({ value: r.id, label: `@${r.name}` }));

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Skeleton height="70px" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
          <Skeleton height="90px" />
          <Skeleton height="90px" />
          <Skeleton height="90px" />
          <Skeleton height="90px" />
        </div>
        <Skeleton height="360px" />
      </div>
    );
  }

  const tabs = [
    { id: 'categories', label: 'Categories', count: categories.length, icon: FolderKanban },
    { id: 'hub', label: 'Hub Builder', icon: Send },
    { id: 'tickets', label: 'Active Tickets', count: activeTickets.length, icon: Inbox },
    { id: 'settings', label: 'Settings & Logs', icon: Sliders },
  ];

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <PageHeader
        icon={Ticket}
        title="Ticket Management"
        subtitle="Multi-category support hubs, private member channels, automated staff pings, and transcripts."
        actions={
          <div style={{ display: 'flex', gap: '10px' }}>
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              loading={refreshing}
              onClick={() => fetchData(true)}
            >
              Refresh
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={Plus}
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY_FORM);
                setPingRoles([]);
                setAdminRoles([]);
                setShowForm(true);
              }}
            >
              New Category
            </Button>
          </div>
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
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Categories
              </div>
              <div style={{ fontSize: '26px', fontWeight: '700', color: 'var(--text-main)', marginTop: '4px' }}>
                {stats.categories_count || categories.length}
              </div>
            </div>
            <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(88, 101, 242, 0.1)', color: 'var(--primary)' }}>
              <FolderKanban size={20} />
            </div>
          </div>
        </Card>

        <Card style={{ padding: '18px 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Open Tickets
              </div>
              <div style={{ fontSize: '26px', fontWeight: '700', color: '#10b981', marginTop: '4px' }}>
                {stats.open_tickets || activeTickets.length}
              </div>
            </div>
            <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
              <Inbox size={20} />
            </div>
          </div>
        </Card>

        <Card style={{ padding: '18px 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Closed Tickets
              </div>
              <div style={{ fontSize: '26px', fontWeight: '700', color: 'var(--text-muted)', marginTop: '4px' }}>
                {stats.closed_tickets || 0}
              </div>
            </div>
            <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-muted)' }}>
              <Clock size={20} />
            </div>
          </div>
        </Card>

        <Card style={{ padding: '18px 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Total Created
              </div>
              <div style={{ fontSize: '26px', fontWeight: '700', color: 'var(--primary)', marginTop: '4px' }}>
                {stats.total_tickets || 0}
              </div>
            </div>
            <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(88, 101, 242, 0.1)', color: 'var(--primary)' }}>
              <Ticket size={20} />
            </div>
          </div>
        </Card>
      </div>

      {/* Tabs Row */}
      <div style={{
        display: 'flex',
        gap: '6px',
        padding: '4px',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        overflowX: 'auto'
      }}>
        {tabs.map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '9px 16px',
                borderRadius: 'var(--radius-md)',
                border: 'none',
                background: isActive ? 'var(--bg-card)' : 'transparent',
                color: isActive ? 'var(--text-main)' : 'var(--text-muted)',
                fontWeight: isActive ? 600 : 500,
                fontSize: '13.5px',
                cursor: 'pointer',
                transition: 'all 150ms ease',
                boxShadow: isActive ? '0 1px 3px rgba(0, 0, 0, 0.2)' : 'none',
                whiteSpace: 'nowrap'
              }}
            >
              <Icon size={16} color={isActive ? 'var(--primary)' : 'currentColor'} />
              <span>{tab.label}</span>
              {typeof tab.count === 'number' && (
                <Badge variant={isActive ? 'primary' : 'neutral'} size="sm">
                  {tab.count}
                </Badge>
              )}
            </button>
          );
        })}
      </div>

      {/* TAB 1: CATEGORIES */}
      {activeTab === 'categories' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
                Configured Ticket Categories
              </h3>
              <p style={{ margin: '3px 0 0', fontSize: '13px', color: 'var(--text-muted)' }}>
                Each category generates a distinct button with custom welcome embeds and staff pings.
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY_FORM);
                setPingRoles([]);
                setAdminRoles([]);
                setShowForm(true);
              }}
            >
              Create Category
            </Button>
          </div>

          {categories.length === 0 ? (
            <EmptyState
              icon={Ticket}
              title="No Ticket Categories Defined"
              description="Create categories such as Support, Billing, or Bug Reports to allow members to open focused private channels."
              actionLabel="Create First Category"
              onAction={() => {
                setEditingId(null);
                setForm(EMPTY_FORM);
                setPingRoles([]);
                setAdminRoles([]);
                setShowForm(true);
              }}
            />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
              {categories.map(cat => (
                <Card key={cat.id} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <CardContent style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '38px',
                          height: '38px',
                          borderRadius: '8px',
                          background: 'rgba(88, 101, 242, 0.1)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '18px'
                        }}>
                          {cat.button_emoji || '🎫'}
                        </div>
                        <div>
                          <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-main)' }}>
                            {cat.name}
                          </h4>
                          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                            Button: "{cat.button_label || cat.name}"
                          </span>
                        </div>
                      </div>
                      <Badge variant="neutral" size="sm">
                        #{cat.ticket_counter || 0} Tickets
                      </Badge>
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
                        <span style={{ color: 'var(--text-muted)' }}>Embed Title</span>
                        <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>
                          {cat.embed_title || 'New Ticket'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Staff Ping</span>
                        <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>
                          {cat.ping_roles ? `${cat.ping_roles.split(',').length} role(s)` : 'None'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Admin Roles</span>
                        <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>
                          {cat.admin_roles ? `${cat.admin_roles.split(',').length} role(s)` : 'Default Staff'}
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
                      variant="outline"
                      size="sm"
                      icon={Edit3}
                      onClick={() => handleEditCategory(cat)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={Trash2}
                      onClick={() => handleDeleteCategory(cat.id)}
                    >
                      Delete
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: HUB BUILDER */}
      {activeTab === 'hub' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 1fr) minmax(360px, 1fr)', gap: '24px' }}>
          {/* Builder Form */}
          <Card>
            <CardHeader>
              <CardTitle>Deploy Ticket Hub Panel</CardTitle>
              <CardDescription>
                Post an interactive Discord embed with button rows directly into a designated channel.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handlePublishHub} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Target Discord Channel
                  </label>
                  <Select
                    value={hubChannelId}
                    onChange={setHubChannelId}
                    options={channelOptions}
                    placeholder="Select destination channel..."
                    searchable
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Panel Embed Title
                  </label>
                  <input
                    type="text"
                    className="form-input"
                    value={hubTitle}
                    onChange={e => setHubTitle(e.target.value)}
                    placeholder="Support Ticket Hub"
                    required
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                    Panel Description / Instructions
                  </label>
                  <textarea
                    className="form-input"
                    rows={3}
                    value={hubDesc}
                    onChange={e => setHubDesc(e.target.value)}
                    placeholder="Explain how members can open a ticket..."
                    required
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                      Accent Color
                    </label>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <input
                        type="color"
                        value={hubColor}
                        onChange={e => setHubColor(e.target.value)}
                        style={{
                          width: '40px',
                          height: '38px',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--border)',
                          cursor: 'pointer',
                          background: 'none'
                        }}
                      />
                      <input
                        type="text"
                        className="form-input"
                        value={hubColor}
                        onChange={e => setHubColor(e.target.value)}
                      />
                    </div>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                      Footer Text
                    </label>
                    <input
                      type="text"
                      className="form-input"
                      value={hubFooter}
                      onChange={e => setHubFooter(e.target.value)}
                      placeholder="Footer notice..."
                    />
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                      Categories to Include in Panel
                    </label>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {selectedHubCats.length} selected
                    </span>
                  </div>

                  {categories.length === 0 ? (
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '12px', background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)' }}>
                      No categories created yet. Create at least one category to publish a hub.
                    </div>
                  ) : (
                    <div style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                      maxHeight: '180px',
                      overflowY: 'auto',
                      padding: '8px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)'
                    }}>
                      {categories.map(cat => {
                        const isChecked = selectedHubCats.includes(cat.id);
                        return (
                          <label
                            key={cat.id}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '10px',
                              padding: '8px 10px',
                              borderRadius: 'var(--radius-sm)',
                              background: isChecked ? 'rgba(88, 101, 242, 0.08)' : 'transparent',
                              cursor: 'pointer',
                              fontSize: '13.5px',
                              transition: 'background 120ms ease'
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={e => {
                                if (e.target.checked) {
                                  setSelectedHubCats([...selectedHubCats, cat.id]);
                                } else {
                                  setSelectedHubCats(selectedHubCats.filter(id => id !== cat.id));
                                }
                              }}
                              style={{ accentColor: 'var(--primary)' }}
                            />
                            <span>{cat.button_emoji || '🎫'}</span>
                            <span style={{ fontWeight: isChecked ? 600 : 400, color: 'var(--text-main)' }}>
                              {cat.name}
                            </span>
                            <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                              Button: {cat.button_label || cat.name}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>

                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  icon={Send}
                  loading={publishingHub}
                  disabled={!hubChannelId || !selectedHubCats.length}
                  style={{ marginTop: '8px', width: '100%' }}
                >
                  Deploy Hub to Discord Channel
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Live Embed Mockup */}
          <Card>
            <CardHeader>
              <CardTitle>Discord Live Preview</CardTitle>
              <CardDescription>
                Simulated view of the message panel as server members will interact with it.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div style={{
                background: '#313338',
                borderRadius: '8px',
                padding: '16px',
                color: '#dbdee1',
                fontFamily: 'gg sans, "Noto Sans", "Helvetica Neue", Helvetica, Arial, sans-serif'
              }}>
                {/* Bot Message Header */}
                <div style={{ display: 'flex', gap: '12px', marginBottom: '10px', alignItems: 'center' }}>
                  <div style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '50%',
                    background: '#5865F2',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#ffffff',
                    fontWeight: 700,
                    fontSize: '14px'
                  }}>
                    BOT
                  </div>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontWeight: 600, color: '#f2f3f5', fontSize: '14px' }}>GKR Bot</span>
                      <span style={{
                        background: '#5865F2',
                        color: '#ffffff',
                        fontSize: '9.5px',
                        padding: '1px 5px',
                        borderRadius: '3px',
                        fontWeight: 600
                      }}>
                        APP
                      </span>
                      <span style={{ fontSize: '11px', color: '#949ba4' }}>Today at 12:00 PM</span>
                    </div>
                  </div>
                </div>

                {/* Embed Content */}
                <div style={{
                  borderLeft: `4px solid ${hubColor || '#5865F2'}`,
                  background: '#2b2d31',
                  borderRadius: '4px',
                  padding: '12px 16px',
                  marginLeft: '48px',
                  marginBottom: '12px'
                }}>
                  <div style={{ fontWeight: 700, color: '#f2f3f5', fontSize: '15px', marginBottom: '6px' }}>
                    {hubTitle || 'Support Ticket Hub'}
                  </div>
                  <div style={{ fontSize: '13.5px', color: '#dbdee1', lineHeight: '1.45', marginBottom: '10px', whiteSpace: 'pre-wrap' }}>
                    {hubDesc || 'Select an option below to open a ticket...'}
                  </div>
                  {hubFooter && (
                    <div style={{
                      fontSize: '11.5px',
                      color: '#949ba4',
                      borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                      paddingTop: '6px'
                    }}>
                      {hubFooter}
                    </div>
                  )}
                </div>

                {/* Discord Buttons Row */}
                <div style={{ marginLeft: '48px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {selectedHubCats.length === 0 ? (
                    <div style={{ fontSize: '12px', color: '#949ba4', fontStyle: 'italic' }}>
                      (No category buttons selected)
                    </div>
                  ) : (
                    selectedHubCats.map(cid => {
                      const cat = categories.find(c => c.id === cid);
                      if (!cat) return null;
                      return (
                        <div
                          key={cid}
                          style={{
                            background: '#4e5058',
                            color: '#ffffff',
                            padding: '7px 14px',
                            borderRadius: '4px',
                            fontSize: '13px',
                            fontWeight: 500,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            userSelect: 'none'
                          }}
                        >
                          <span>{cat.button_emoji || '🎫'}</span>
                          <span>{cat.button_label || cat.name}</span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 3: ACTIVE TICKETS */}
      {activeTab === 'tickets' && (
        <Card>
          <CardHeader>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <CardTitle>Currently Active Tickets</CardTitle>
                <CardDescription>Real-time list of opened member channels currently waiting for staff resolution.</CardDescription>
              </div>
              <Button variant="outline" size="sm" icon={RefreshCw} onClick={() => fetchData(true)}>
                Refresh List
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {activeTickets.length === 0 ? (
              <EmptyState
                icon={CheckCircle2}
                title="Support Queue Clean"
                description="There are currently no open support tickets across this server. All tickets have been handled or archived."
              />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13.5px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', textAlign: 'left', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '12px 14px', fontWeight: 600 }}>Ticket</th>
                      <th style={{ padding: '12px 14px', fontWeight: 600 }}>Category</th>
                      <th style={{ padding: '12px 14px', fontWeight: 600 }}>Channel</th>
                      <th style={{ padding: '12px 14px', fontWeight: 600 }}>Ticket Owner</th>
                      <th style={{ padding: '12px 14px', fontWeight: 600 }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeTickets.map(t => (
                      <tr key={t.channel_id || t.ticket_number} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '12px 14px', fontWeight: 600, color: 'var(--text-main)' }}>
                          #{t.ticket_number}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          <Badge variant="primary" size="sm">{t.category_name || 'General'}</Badge>
                        </td>
                        <td style={{ padding: '12px 14px', color: 'var(--primary)', fontWeight: 500 }}>
                          #{t.channel_name}
                        </td>
                        <td style={{ padding: '12px 14px', color: 'var(--text-main)' }}>
                          {t.owner_name || 'Member'}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          <Badge variant="success" dot size="sm">Open</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* TAB 4: SETTINGS & LOGS */}
      {activeTab === 'settings' && (
        <div style={{ maxWidth: '640px' }}>
          <Card>
            <CardHeader>
              <CardTitle>Ticket Audit & Transcripts</CardTitle>
              <CardDescription>
                When a support channel is closed, a full transcript HTML/text file and closing summary will be logged automatically.
              </CardDescription>
            </CardHeader>
            <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                  Transcript & Activity Log Channel
                </label>
                <Select
                  value={logChannelId}
                  onChange={setLogChannelId}
                  options={channelOptions}
                  placeholder="Select audit channel..."
                  searchable
                />
                <p style={{ margin: '6px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
                  Staff will be able to review closed ticket conversations even after the channel is deleted.
                </p>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-start', marginTop: '6px' }}>
                <Button
                  variant="primary"
                  icon={CheckCircle2}
                  onClick={handleSaveLogChannel}
                >
                  {logChannelSaved ? 'Saved Successfully!' : 'Save Log Channel'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Category Creation / Edit Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => setShowForm(false)}
        title={editingId ? 'Edit Ticket Category' : 'New Ticket Category'}
        maxWidth="540px"
      >
        <form onSubmit={handleAddCategory} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Category Name
            </label>
            <input
              type="text"
              className="form-input"
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. General Support"
              required
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Button Emoji
              </label>
              <input
                type="text"
                className="form-input"
                value={form.button_emoji}
                onChange={e => setForm({ ...form, button_emoji: e.target.value })}
                placeholder="🎫"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
                Button Label
              </label>
              <input
                type="text"
                className="form-input"
                value={form.button_label}
                onChange={e => setForm({ ...form, button_label: e.target.value })}
                placeholder="Open Ticket"
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Ticket Welcome Embed Title
            </label>
            <input
              type="text"
              className="form-input"
              value={form.embed_title}
              onChange={e => setForm({ ...form, embed_title: e.target.value })}
              placeholder="Support Ticket Opened"
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Welcome Embed Description
            </label>
            <textarea
              className="form-input"
              rows={3}
              value={form.embed_description}
              onChange={e => setForm({ ...form, embed_description: e.target.value })}
              placeholder="Instructions for the user when the channel is created..."
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Staff Ping Roles (Mentioned immediately upon opening)
            </label>
            <MultiSelect
              value={pingRoles}
              onChange={setPingRoles}
              options={roleOptions}
              placeholder="Select roles to ping..."
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>
              Ticket Admin Roles (Authorized to close & archive)
            </label>
            <MultiSelect
              value={adminRoles}
              onChange={setAdminRoles}
              options={roleOptions}
              placeholder="Select roles allowed to manage tickets..."
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
            <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={submitting}>
              {editingId ? 'Update Category' : 'Create Category'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default Tickets;
