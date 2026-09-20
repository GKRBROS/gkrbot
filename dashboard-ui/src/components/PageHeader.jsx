import React from 'react';
import { Badge } from './Badge';

export function PageHeader({
  title,
  subtitle,
  description,
  icon: Icon,
  badge = null,
  badgeVariant = 'primary',
  actions = null,
  className = '',
}) {
  const sub = subtitle || description;
  const renderedBadge = typeof badge === 'string' ? (
    <Badge variant={badgeVariant} size="sm">{badge}</Badge>
  ) : badge;

  return (
    <header className={`page-header-container ${className}`}>
      <div className="page-header-main">
        <div className="page-header-title-row">
          {Icon && (
            <div className="page-header-icon-box">
              <Icon size={22} className="page-header-icon-svg" />
            </div>
          )}
          <div className="page-header-headings min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="page-header-title">{title}</h1>
              {renderedBadge}
            </div>
            {sub && <p className="page-header-subtitle">{sub}</p>}
          </div>
        </div>
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export default PageHeader;
