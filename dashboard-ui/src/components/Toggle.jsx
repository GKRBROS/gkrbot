import React from 'react';

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  size = 'md', // 'sm' | 'md'
  className = '',
  id,
  ariaLabel,
  ...props
}) {
  const toggleId = id || (label ? `toggle-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined);
  const accessibleLabel = ariaLabel || props['aria-label'] || (typeof label === 'string' ? label : undefined);

  if (!label && !description) {
    return (
      <button
        type="button"
        id={toggleId}
        role="switch"
        aria-checked={Boolean(checked)}
        aria-label={accessibleLabel}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`toggle-switch ${checked ? 'active' : ''} toggle-${size} ${disabled ? 'opacity-50 cursor-not-allowed' : ''} ${className}`}
        {...props}
      >
        <span className="toggle-thumb" />
      </button>
    );
  }

  return (
    <div className={`toggle-container ${disabled ? 'opacity-50 cursor-not-allowed' : ''} ${className}`}>
      <label htmlFor={toggleId} className="toggle-text-block">
        {label && <span className="toggle-label">{label}</span>}
        {description && <span className="toggle-desc">{description}</span>}
      </label>
      <button
        type="button"
        id={toggleId}
        role="switch"
        aria-checked={Boolean(checked)}
        aria-label={accessibleLabel}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`toggle-switch ${checked ? 'active' : ''} toggle-${size}`}
        {...props}
      >
        <span className="toggle-thumb" />
      </button>
    </div>
  );
}

export default Toggle;
