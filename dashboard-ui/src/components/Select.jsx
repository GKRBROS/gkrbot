import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Check, Search, X } from 'lucide-react';

/**
 * Custom styled dropdown — replaces native <select> so it matches the theme.
 * options: [{ value, label }]
 */
export function Select({
  value,
  onChange,
  options = [],
  placeholder = 'Select an option...',
  searchable = false,
  style = {},
  disabled = false,
  className = '',
}) {
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef(null);

  const selected = options.find(o => String(o.value) === String(value));

  const toggleOpen = () => {
    if (disabled) return;
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setDropUp(window.innerHeight - rect.bottom < 280 && rect.top > 300);
    }
    setOpen(!open);
    setQuery('');
  };

  useEffect(() => {
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const filtered = searchable
    ? options.filter(o => String(o.label).toLowerCase().includes(query.trim().toLowerCase()))
    : options;

  return (
    <div ref={ref} className={`select-wrapper ${className}`} style={{ position: 'relative', width: '100%', ...style }}>
      <button
        type="button"
        disabled={disabled}
        className={`select-trigger ${open ? 'open' : ''} ${disabled ? 'disabled' : ''}`}
        onClick={toggleOpen}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={`select-label ${!selected ? 'placeholder' : ''}`}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown
          size={16}
          className={`select-chevron ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div className={`select-menu ${dropUp ? 'drop-up' : ''}`}>
          {searchable && options.length > 6 && (
            <div className="select-search-box">
              <Search size={14} className="select-search-icon" />
              <input
                autoFocus
                className="select-search-input"
                placeholder="Search options..."
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
            </div>
          )}
          <div className="select-options" role="listbox">
            {filtered.length === 0 ? (
              <div className="select-empty">No options found</div>
            ) : (
              filtered.map(o => {
                const isSelected = String(o.value) === String(value);
                return (
                  <div
                    key={o.value}
                    role="option"
                    aria-selected={isSelected}
                    className={`select-option ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      onChange(o.value);
                      setOpen(false);
                      setQuery('');
                    }}
                  >
                    <span className="select-option-text">{o.label}</span>
                    {isSelected && <Check size={15} className="select-option-check" />}
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

/**
 * Multi-select dropdown with removable chips — used for role pickers etc.
 * values: array of selected option values
 */
export function MultiSelect({
  values = [],
  onChange,
  options = [],
  placeholder = 'Select options...',
  style = {},
  disabled = false,
  className = '',
}) {
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const toggle = (v) => {
    onChange(values.includes(v) ? values.filter(x => x !== v) : [...values, v]);
  };

  const toggleOpen = () => {
    if (disabled) return;
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setDropUp(window.innerHeight - rect.bottom < 280 && rect.top > 300);
    }
    setOpen(!open);
    setQuery('');
  };

  const filtered = options.filter(o =>
    String(o.label).toLowerCase().includes(query.trim().toLowerCase())
  );
  
  const selectedItems = values
    .map(v => options.find(o => String(o.value) === String(v)))
    .filter(Boolean);

  return (
    <div ref={ref} className={`select-wrapper ${className}`} style={{ position: 'relative', width: '100%', ...style }}>
      {selectedItems.length > 0 && (
        <div className="select-chips-container">
          {selectedItems.map(o => (
            <span key={o.value} className="select-chip">
              <span className="select-chip-label">{o.label}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(o.value);
                }}
                className="select-chip-remove"
                title="Remove"
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}

      <button
        type="button"
        disabled={disabled}
        className={`select-trigger ${open ? 'open' : ''} ${disabled ? 'disabled' : ''}`}
        onClick={toggleOpen}
      >
        <span className="select-label">
          {selectedItems.length > 0
            ? `${selectedItems.length} selected`
            : <span className="placeholder">{placeholder}</span>}
        </span>
        <ChevronDown
          size={16}
          className={`select-chevron ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div className={`select-menu ${dropUp ? 'drop-up' : ''}`}>
          <div className="select-search-box">
            <Search size={14} className="select-search-icon" />
            <input
              autoFocus
              className="select-search-input"
              placeholder="Filter options..."
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </div>
          <div className="select-options">
            {filtered.length === 0 ? (
              <div className="select-empty">No options found</div>
            ) : (
              filtered.map(o => {
                const isSelected = values.includes(o.value);
                return (
                  <div
                    key={o.value}
                    className={`select-option ${isSelected ? 'selected' : ''}`}
                    onClick={() => toggle(o.value)}
                  >
                    <div className="flex items-center gap-2">
                      <div className={`select-checkbox ${isSelected ? 'checked' : ''}`}>
                        {isSelected && <Check size={12} />}
                      </div>
                      <span className="select-option-text">{o.label}</span>
                    </div>
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

export default Select;
