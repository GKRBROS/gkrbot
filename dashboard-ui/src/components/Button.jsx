import React from 'react';
import { Loader2 } from 'lucide-react';

export function Button({
  children,
  variant = 'primary', // 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'success'
  size = 'md', // 'sm' | 'md' | 'lg' | 'icon'
  icon: Icon,
  iconRight: IconRight,
  loading = false,
  disabled = false,
  className = '',
  type = 'button',
  onClick,
  ...props
}) {
  const classes = [
    'btn',
    `btn-${variant}`,
    size !== 'md' ? `btn-${size}` : '',
    loading ? 'loading' : '',
    className
  ].filter(Boolean).join(' ');

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      onClick={onClick}
      {...props}
    >
      {loading ? (
        <Loader2 className="btn-spinner animate-spin" size={size === 'sm' ? 14 : size === 'lg' ? 18 : 16} />
      ) : Icon ? (
        <Icon size={size === 'sm' ? 14 : size === 'lg' ? 18 : 16} className="btn-icon-svg" />
      ) : null}
      
      {children && <span>{children}</span>}

      {!loading && IconRight && (
        <IconRight size={size === 'sm' ? 14 : size === 'lg' ? 18 : 16} className="btn-icon-svg" />
      )}
    </button>
  );
}

export default Button;
