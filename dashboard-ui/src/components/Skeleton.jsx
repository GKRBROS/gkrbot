import React from 'react';

export function Skeleton({ className = '', width, height, rounded = 'md', style = {} }) {
  const radiusMap = {
    none: '0px',
    sm: '6px',
    md: '8px',
    lg: '12px',
    full: '9999px',
  };

  return (
    <div
      className={`skeleton-shimmer ${className}`}
      style={{
        width: width || '100%',
        height: height || '20px',
        borderRadius: radiusMap[rounded] || rounded,
        ...style,
      }}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="card skeleton-card">
      <div className="skeleton-card-header">
        <Skeleton width="40px" height="40px" rounded="lg" />
        <div className="flex-1">
          <Skeleton width="60%" height="18px" style={{ marginBottom: '8px' }} />
          <Skeleton width="40%" height="13px" />
        </div>
      </div>
      <Skeleton width="100%" height="48px" rounded="md" style={{ marginTop: '16px' }} />
    </div>
  );
}

export default Skeleton;
