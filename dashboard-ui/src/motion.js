// Cursor-tracked spotlight for cards (feeds --mx / --my used by theme-flow.css).
// One delegated listener, throttled with requestAnimationFrame.
const SELECTOR = '.card, .server-card';

let frame = 0;
let target = null;
let x = 0;
let y = 0;

function onPointerMove(e) {
  const el = e.target instanceof Element ? e.target.closest(SELECTOR) : null;
  if (!el) return;
  target = el;
  x = e.clientX;
  y = e.clientY;
  if (frame) return;
  frame = requestAnimationFrame(() => {
    frame = 0;
    const r = target.getBoundingClientRect();
    target.style.setProperty('--mx', `${x - r.left}px`);
    target.style.setProperty('--my', `${y - r.top}px`);
  });
}

export function initMotion() {
  if (typeof window === 'undefined') return;
  const noHover = !window.matchMedia('(hover: hover)').matches;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (noHover || reduced) return;
  document.addEventListener('pointermove', onPointerMove, { passive: true });
}