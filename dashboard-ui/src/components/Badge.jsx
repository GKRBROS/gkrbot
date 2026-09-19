import React from 'react';

export function Badge({
  children,
  variant = 'neutral', // 'primary' | 'success' | 'warning' | 'danger' | 'neutral' | 'outline'
  size = 'md', // 'sm' | 'md'
  icon: Icon,
  dot = false,
  className = '',
  ...props
}) {
  return (
    <span className={`badge badge-${variant} badge-${size} ${className}`} {...props}>
      {dot && <span className="badge-dot" />}
      {Icon && <Icon size={size === 'sm' ? 11 : 13} className="badge-icon" />}
      <span>{children}</span>
    </span>
  );
}

export default Badge;
