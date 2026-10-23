import React, { useMemo, useState, useRef, useEffect } from 'react';
import { ChevronDown, Hash, Volume2, Megaphone, Folder, Search, Check, AlertCircle } from 'lucide-react';

/**
 * Discord Channel Selector with type filtering and category grouping.
 * Prevents selecting invalid channels (e.g. voice or category) for text alerts.
 */
export function ChannelSelect({
  value,
  onChange,
  channels = [],
  allowedTypes = ['text', 'news'], // default: text-based alerts only
  placeholder = 'Select a channel...',
  disabled = false,
  className = '',
  style = {},
  searchable = true,
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [dropUp, setDropUp] = useState(false);
  const ref = useRef(null);

  // Normalize channel list
  const normalizedChannels = useMemo(() => {
    return channels.map(c => ({
      id: String(c.id),
      name: c.name || 'unnamed-channel',
      type: c.type || 'text',
      category_name: c.category_name || (c.category ? c.category.name : null),
      can_send: c.can_send_messages !== undefined ? c.can_send_messages : (c.type === 'text' || c.type === 'news'),
    }));
  }, [channels]);

  // Find currently selected channel
  const selected = useMemo(() => {
    if (!value) return null;
    return normalizedChannels.find(c => c.id === String(value)) || null;
  }, [normalizedChannels, value]);

  // Filter channels by query and allowed types
  const filteredChannels = useMemo(() => {
    let list = normalizedChannels;
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter(c =>
        c.name.toLowerCase().includes(q) ||
        (c.category_name && c.category_name.toLowerCase().includes(q))
      );
    }
    return list;
  }, [normalizedChannels, query]);

  // Group by category
  const grouped = useMemo(() => {
    const groups = {};
    filteredChannels.forEach(c => {
      const cat = c.category_name || 'NO CATEGORY';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(c);
    });
    return groups;
  }, [filteredChannels]);

  const toggleOpen = () => {
    if (disabled) return;
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setDropUp(window.innerHeight - rect.bottom < 290 && rect.top > 300);
    }
    setOpen(!open);
    setQuery('');
  };

  useEffect(() => {
    const onDocClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const handleSelect = (ch) => {
    if (disabled || !onChange) return;
    const isAllowed = allowedTypes.includes(ch.type);
    if (!isAllowed) return;

    try {
      onChange(ch.id, { target: { value: ch.id, name: '' } });
    } catch {
      onChange({ target: { value: ch.id, name: '' } });
    }
    setOpen(false);
    setQuery('');
  };

  const getChannelIcon = (type) => {
    switch (type) {
      case 'voice':
        return <Volume2 size={15} className="text-muted shrink-0" />;
      case 'news':
        return <Megaphone size={15} className="text-primary shrink-0" />;
      case 'category':
        return <Folder size={15} className="text-muted shrink-0" />;
      default:
        return <Hash size={15} className="text-muted shrink-0" />;
    }
  };

  return (
    <div ref={ref} className={`select-wrapper ${className}`} style={{ position: 'relative', width: '100%', ...style }}>
      <button
        type="button"
        disabled={disabled}
        onClick={toggleOpen}
        className={`select-trigger ${open ? 'open' : ''} ${disabled ? 'disabled' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 truncate">
          {selected ? (
            <>
              {getChannelIcon(selected.type)}
              <span className="font-medium text-main">{selected.name}</span>
              {selected.category_name && (
                <span className="text-[11px] text-muted truncate">({selected.category_name})</span>
              )}
            </>
          ) : (
            <span className="text-muted placeholder">{placeholder}</span>
          )}
        </span>
        <ChevronDown size={16} className={`select-chevron ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className={`select-menu ${dropUp ? 'drop-up' : ''}`} style={{ maxHeight: '320px', overflowY: 'auto' }}>
          {searchable && normalizedChannels.length > 5 && (
            <div className="select-search-box">
              <Search size={14} className="select-search-icon" />
              <input
                autoFocus
                className="select-search-input"
                placeholder="Search channel or category..."
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
            </div>
          )}

          <div className="select-options" role="listbox">
            {Object.keys(grouped).length === 0 ? (
              <div className="select-empty">No channels found</div>
            ) : (
              Object.entries(grouped).map(([category, items]) => (
                <div key={category} className="channel-group mb-1">
                  <div className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-muted/70 bg-surface-hover/30 rounded">
                    {category}
                  </div>
                  {items.map(ch => {
                    const isSelected = selected && selected.id === ch.id;
                    const isAllowed = allowedTypes.includes(ch.type);

                    return (
                      <div
                        key={ch.id}
                        role="option"
                        aria-selected={isSelected}
                        aria-disabled={!isAllowed}
                        onClick={() => isAllowed && handleSelect(ch)}
                        className={`select-option flex items-center justify-between ${
                          isSelected ? 'selected' : ''
                        } ${!isAllowed ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
                        title={!isAllowed ? `Cannot select ${ch.type} channel for text alerts` : ''}
                      >
                        <div className="flex items-center gap-2 truncate">
                          {getChannelIcon(ch.type)}
                          <span className="select-option-text truncate">{ch.name}</span>
                          {!isAllowed && (
                            <span className="text-[10px] uppercase font-semibold px-1.5 py-0.2 rounded bg-danger/15 text-danger border border-danger/25">
                              {ch.type}
                            </span>
                          )}
                        </div>
                        {isSelected && <Check size={14} className="select-option-check text-primary shrink-0" />}
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default ChannelSelect;
