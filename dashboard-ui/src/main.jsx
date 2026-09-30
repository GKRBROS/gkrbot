import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { BotProvider } from './BotContext.jsx';
import { ToastProvider } from './components/ToastContext.jsx';
import './index.css';
import './theme-flow.css';
import './live-bg.css';
import './landing.css';
import './site.css';
import { initMotion } from './motion.js';
import AnimatedBackground from './AnimatedBackground.jsx';

initMotion();

function setHeadLink(rel, href, type) {
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement('link');
    el.rel = rel;
    document.head.appendChild(el);
  }
  el.href = href;
  if (type) el.type = type;
  el.removeAttribute('sizes');
}
setHeadLink('icon', '/favicon.png', 'image/png');
setHeadLink('apple-touch-icon', '/apple-touch-icon.png');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AnimatedBackground />
      <BotProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </BotProvider>
    </BrowserRouter>
  </React.StrictMode>,
);