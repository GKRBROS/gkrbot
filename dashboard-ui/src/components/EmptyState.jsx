import React from 'react';

export function EmptyState({
  icon: Icon,
  title,
  description,
  action = null,
  className = '',
}) {
  return (
    <div className={`empty-state-box ${className}`}>
      {Icon && (
        <div className="empty-state-icon-wrap">
          <Icon size={32} className="empty-state-svg" />
        </div>
      )}
      {title && <h3 className="empty-state-title">{title}</h3>}
      {description && <p className="empty-state-desc">{description}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}

export default EmptyState;
