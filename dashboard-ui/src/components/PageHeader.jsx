import React from 'react';

export function PageHeader({
  title,
  subtitle,
  icon: Icon,
  badge = null,
  actions = null,
  className = '',
}) {
  return (
    <header className={`page-header-container ${className}`}>
      <div className="page-header-main">
        <div className="page-header-title-row">
          {Icon && (
            <div className="page-header-icon-box">
              <Icon size={22} className="page-header-icon-svg" />
            </div>
          )}
          <div className="page-header-headings">
            <div className="flex items-center gap-2">
              <h1 className="page-header-title">{title}</h1>
              {badge}
            </div>
            {subtitle && <p className="page-header-subtitle">{subtitle}</p>}
          </div>
        </div>
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export default PageHeader;
