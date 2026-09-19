import React from 'react';

export function Card({ children, className = '', hover = false, border = true, style = {}, ...props }) {
  return (
    <div
      className={`card ${hover ? 'card-hover' : ''} ${!border ? 'card-borderless' : ''} ${className}`}
      style={style}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className = '', action = null, ...props }) {
  return (
    <div className={`card-header ${className}`} {...props}>
      <div className="card-header-content">{children}</div>
      {action && <div className="card-header-action">{action}</div>}
    </div>
  );
}

export function CardTitle({ children, className = '', icon: Icon, ...props }) {
  return (
    <h3 className={`card-title ${className}`} {...props}>
      {Icon && <Icon size={18} className="card-title-icon" />}
      <span>{children}</span>
    </h3>
  );
}

export function CardDescription({ children, className = '', ...props }) {
  return (
    <p className={`card-description ${className}`} {...props}>
      {children}
    </p>
  );
}

export function CardContent({ children, className = '', ...props }) {
  return (
    <div className={`card-body ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardFooter({ children, className = '', ...props }) {
  return (
    <div className={`card-footer ${className}`} {...props}>
      {children}
    </div>
  );
}

export default Card;
