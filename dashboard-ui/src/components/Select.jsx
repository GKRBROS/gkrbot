import { useEffect, useRef, useState } from 'react';

/**
 * Custom styled dropdown — replaces native <select> so it matches the theme.
 * options: [{ value, label }]
 */
export function Select({ value, onChange, options = [], placeholder = 'Select...', searchable = false, style = {}, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef(null);

  const selected = options.find(o => String(o.value) === String(value));

  const toggleOpen = () => {
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setDropUp(window.innerHeight - rect.bottom < 300 && rect.top > 320);
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
    ? options.filter(o => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    : options;

  return (
    <div ref={ref} style={{ position: 'relative', width: '100%', ...style }}>
      <button
        type="button"
        disabled={disabled}
        className={`select-trigger ${open ? 'open' : ''}`}
        onClick={toggleOpen}
      >
        <span style={{
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          color: selected ? 'var(--text-main)' : 'var(--text-muted)'
        }}>
          {selected ? selected.label : placeholder}
        </span>
        <svg
          width="12" height="12" viewBox="0 0 12 12"
          style={{ flexShrink: 0, transition: 'transform 0.2s', transform: open ? 'rotate(180deg)' : 'none' }}
        >
          <path fill="currentColor" d="M6 8L1 3h10z" />
        </svg>
      </button>

      {open && (
        <div className={`select-menu ${dropUp ? 'drop-up' : ''}`}>
          {searchable && options.length > 6 && (
            <input
              autoFocus
              className="select-search"
              placeholder="Type to filter..."
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          )}
          <div className="select-options">
            {filtered.length === 0 ? (
              <div className="select-empty">No matches found</div>
            ) : filtered.map(o => {
              const isSelected = String(o.value) === String(value);
              return (
                <div
                  key={o.value}
                  className={`select-option ${isSelected ? 'selected' : ''}`}
                  onClick={() => { onChange(o.value); setOpen(false); setQuery(''); }}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</span>
                  {isSelected && <span style={{ color: 'var(--accent)', flexShrink: 0 }}>✓</span>}
                </div>
              );
            })}
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
export function MultiSelect({ values = [], onChange, options = [], placeholder = 'Select...', style = {} }) {
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
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setDropUp(window.innerHeight - rect.bottom < 300 && rect.top > 320);
    }
    setOpen(!open);
    setQuery('');
  };

  const filtered = options.filter(o => o.label.toLowerCase().includes(query.trim().toLowerCase()));
  const selectedLabels = values
    .map(v => options.find(o => String(o.value) === String(v)))
    .filter(Boolean);

  return (
    <div ref={ref} style={{ position: 'relative', width: '100%', ...style }}>
      {selectedLabels.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
          {selectedLabels.map(o => (
            <span key={o.value} className="badge badge-primary" style={{ gap: '6px' }}>
              {o.label}
              <button
                type="button"
                onClick={() => toggle(o.value)}
                style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0, fontSize: '12px', lineHeight: 1 }}
                title="Remove"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      <button
        type="button"
        className={`select-trigger ${open ? 'open' : ''}`}
        onClick={toggleOpen}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-main)' }}>
          {selectedLabels.length > 0
            ? `${selectedLabels.length} selected`
            : <span style={{ color: 'var(--text-muted)' }}>{placeholder}</span>}
        </span>
        <svg width="12" height="12" viewBox="0 0 12 12" style={{ flexShrink: 0, transition: 'transform 0.2s', transform: open ? 'rotate(180deg)' : 'none' }}>
          <path fill="currentColor" d="M6 8L1 3h10z" />
        </svg>
      </button>

      {open && (
        <div className={`select-menu ${dropUp ? 'drop-up' : ''}`}>
          <input
            autoFocus
            className="select-search"
            placeholder="Type to filter..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <div className="select-options">
            {filtered.length === 0 ? (
              <div className="select-empty">No matches found</div>
            ) : filtered.map(o => {
              const isSelected = values.includes(o.value);
              return (
                <div
                  key={o.value}
                  className={`select-option ${isSelected ? 'selected' : ''}`}
                  onClick={() => toggle(o.value)}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                    <span style={{
                      width: '15px', height: '15px', borderRadius: '4px', flexShrink: 0,
                      border: isSelected ? 'none' : '1.5px solid var(--border-hover)',
                      background: isSelected ? 'var(--brand-gradient)' : 'transparent',
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '10px', color: 'white'
                    }}>
                      {isSelected ? '✓' : ''}
                    </span>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.label}</span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default Select;
