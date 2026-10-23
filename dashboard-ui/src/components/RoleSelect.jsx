import React, { useMemo, useState, useRef, useEffect } from 'react';
import { ChevronDown, Search, Check, Lock, ShieldAlert } from 'lucide-react';

/**
 * Discord Role Selector with hierarchy sorting and permission boundary enforcement.
 * Prevents assigning or modifying roles positioned higher than the bot's highest role.
 */
export function RoleSelect({
  value,
  onChange,
  roles = [],
  placeholder = 'Select a role...',
  disabled = false,
  className = '',
  style = {},
  searchable = true,
  manageableOnly = true, // When true, lock roles above bot's top role
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [dropUp, setDropUp] = useState(false);
  const ref = useRef(null);

  // Normalize and sort roles by hierarchy (highest position first)
  const sortedRoles = useMemo(() => {
    return [...roles]
      .filter(r => r.name !== '@everyone')
      .sort((a, b) => (b.position || 0) - (a.position || 0));
  }, [roles]);

  const selected = useMemo(() => {
    if (!value) return null;
    return sortedRoles.find(r => String(r.id) === String(value)) || null;
  }, [sortedRoles, value]);

  const filteredRoles = useMemo(() => {
    if (!query.trim()) return sortedRoles;
    const q = query.trim().toLowerCase();
    return sortedRoles.filter(r => r.name.toLowerCase().includes(q));
  }, [sortedRoles, query]);

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

  const handleSelect = (role) => {
    if (disabled || !onChange) return;
    if (manageableOnly && (role.is_higher || role.can_manage === false)) return;

    try {
      onChange(role.id, { target: { value: role.id, name: '' } });
    } catch {
      onChange({ target: { value: role.id, name: '' } });
    }
    setOpen(false);
    setQuery('');
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
              <span
                className="w-3 h-3 rounded-full shrink-0 border border-white/20"
                style={{ backgroundColor: selected.color || '#99aab5' }}
              />
              <span className="font-medium text-main truncate" style={{ color: selected.color !== '#99aab5' ? selected.color : undefined }}>
                {selected.name}
              </span>
            </>
          ) : (
            <span className="text-muted placeholder">{placeholder}</span>
          )}
        </span>
        <ChevronDown size={16} className={`select-chevron ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className={`select-menu ${dropUp ? 'drop-up' : ''}`} style={{ maxHeight: '320px', overflowY: 'auto' }}>
          {searchable && sortedRoles.length > 5 && (
            <div className="select-search-box">
              <Search size={14} className="select-search-icon" />
              <input
                autoFocus
                className="select-search-input"
                placeholder="Search server role..."
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
            </div>
          )}

          <div className="select-options" role="listbox">
            {filteredRoles.length === 0 ? (
              <div className="select-empty">No roles found</div>
            ) : (
              filteredRoles.map(role => {
                const isSelected = selected && selected.id === role.id;
                const isLocked = manageableOnly && (role.is_higher || role.can_manage === false);

                return (
                  <div
                    key={role.id}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={isLocked}
                    onClick={() => !isLocked && handleSelect(role)}
                    className={`select-option flex items-center justify-between ${
                      isSelected ? 'selected' : ''
                    } ${isLocked ? 'opacity-40 cursor-not-allowed bg-surface-card/40' : 'cursor-pointer'}`}
                    title={
                      isLocked
                        ? role.managed
                          ? 'This role is managed by an external integration and cannot be assigned'
                          : 'This role is higher than the bot top role in server hierarchy'
                        : `Position: ${role.position}`
                    }
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span
                        className="w-2.5 h-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: role.color || '#99aab5' }}
                      />
                      <span className="select-option-text truncate">{role.name}</span>
                      {isLocked && (
                        <span className="flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.2 rounded bg-warning/15 text-warning border border-warning/25">
                          <Lock size={10} />
                          {role.managed ? 'Managed' : 'Higher than Bot'}
                        </span>
                      )}
                    </div>
                    {isSelected && <Check size={14} className="select-option-check text-primary shrink-0" />}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default RoleSelect;
