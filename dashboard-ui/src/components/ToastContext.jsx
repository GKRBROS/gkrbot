import { createContext, useCallback, useContext, useRef, useState } from 'react';

const ToastContext = createContext(null);

let _id = 0;

/** toast(message, type?) — call from anywhere via useToast() */
export function useToast() {
  return useContext(ToastContext);
}

const ICONS = {
  error: '✕',
  success: '✓',
  warning: '⚠',
  info: 'ℹ',
};

const COLORS = {
  error:   { bg: 'rgba(239,68,68,0.12)',   border: '#ef4444', icon: '#ef4444' },
  success: { bg: 'rgba(34,197,94,0.12)',   border: '#22c55e', icon: '#22c55e' },
  warning: { bg: 'rgba(234,179,8,0.12)',   border: '#eab308', icon: '#eab308' },
  info:    { bg: 'rgba(99,102,241,0.12)',  border: '#6366f1', icon: '#818cf8' },
};

function ToastItem({ id, message, type = 'error', onRemove }) {
  const c = COLORS[type] || COLORS.info;
  return (
    <div
      id={`toast-${id}`}
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
        padding: '12px 16px',
        borderRadius: '10px',
        background: c.bg,
        border: `1px solid ${c.border}`,
        backdropFilter: 'blur(12px)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        maxWidth: '380px',
        width: '100%',
        animation: 'toast-in 0.28s cubic-bezier(.22,1,.36,1) both',
        fontSize: '13.5px',
        color: 'var(--text-main, #f1f5f9)',
        lineHeight: 1.4,
        wordBreak: 'break-word',
      }}
    >
      <span style={{ color: c.icon, fontWeight: 700, fontSize: '15px', flexShrink: 0, marginTop: '1px' }}>
        {ICONS[type] || ICONS.info}
      </span>
      <span style={{ flex: 1 }}>{message}</span>
      <button
        onClick={() => onRemove(id)}
        aria-label="Dismiss"
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-muted, #94a3b8)', fontSize: '14px', padding: '0 0 0 4px',
          lineHeight: 1, flexShrink: 0,
        }}
      >✕</button>
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef({});

  const remove = useCallback((id) => {
    clearTimeout(timers.current[id]);
    delete timers.current[id];
    setToasts(t => t.filter(x => x.id !== id));
  }, []);

  const toast = useCallback((message, type = 'error', duration = 5000) => {
    const id = ++_id;
    setToasts(t => [...t, { id, message, type }]);
    timers.current[id] = setTimeout(() => remove(id), duration);
    return id;
  }, [remove]);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      {/* Toast container — bottom-right */}
      <div
        aria-live="polite"
        style={{
          position: 'fixed', bottom: '24px', right: '24px',
          zIndex: 99999, display: 'flex', flexDirection: 'column',
          gap: '10px', alignItems: 'flex-end', pointerEvents: 'none',
        }}
      >
        {toasts.map(t => (
          <div key={t.id} style={{ pointerEvents: 'all' }}>
            <ToastItem id={t.id} message={t.message} type={t.type} onRemove={remove} />
          </div>
        ))}
      </div>
      <style>{`
        @keyframes toast-in {
          from { opacity: 0; transform: translateY(16px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)   scale(1); }
        }
      `}</style>
    </ToastContext.Provider>
  );
}
