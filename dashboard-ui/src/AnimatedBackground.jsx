import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

// Full-page animated background: a GPU shader that draws slow, silky, flowing
// ribbons of light in the dashboard's brand colours (indigo / violet / sky).
//
//  • Mounted once (see main.jsx) so it survives every route change.
//  • Transparent output — the existing dot-grid + top glow in index.css still
//    shows through underneath.
//  • Cheap: renders at ~half resolution, capped at 30 fps, pauses when the tab is
//    hidden, and flows slowly (instead of freezing) if the OS asks for reduced motion.
//  • If WebGL is unavailable the old CSS aurora (body::after) stays as fallback.

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform vec2  uRes;
uniform float uTime;
uniform vec2  uMouse;
uniform float uStrength;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p = p * 2.02 + vec2(1.7, 9.2);
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 p  = (gl_FragCoord.xy - 0.5 * uRes) / min(uRes.x, uRes.y);
  float t = uTime * 0.12;

  // Whole field slowly drifts + follows the cursor a little
  p += vec2(uTime * 0.022, sin(uTime * 0.08) * 0.20);   // waves travel across the screen
  p += (uMouse - 0.5) * 0.10;

  // Domain-warped noise = liquid, flowing motion (low frequency => big, smooth waves)
  vec2 q = vec2(fbm(p * 0.85 + vec2(0.0, t)),
                fbm(p * 0.85 + vec2(5.2, 1.3) - t));
  vec2 r = vec2(fbm(p * 1.1 + 2.2 * q + vec2(1.7, 9.2) + 0.8 * t),
                fbm(p * 1.1 + 2.2 * q + vec2(8.3, 2.8) - 0.7 * t));
  float f = fbm(p * 1.0 + 2.4 * r);

  // Soft glowing ribbons that ride along the flow
  float ridge = 1.0 - abs(2.0 * fbm(p * 1.25 + 2.0 * r + t) - 1.0);
  ridge = pow(ridge, 4.0);

  vec3 indigo = vec3(0.345, 0.396, 0.949);   // #5865F2
  vec3 violet = vec3(0.655, 0.545, 0.980);   // #a78bfa
  vec3 sky    = vec3(0.220, 0.741, 0.973);   // #38bdf8

  vec3 col = mix(indigo, violet, smoothstep(0.20, 0.80, q.x));
  col = mix(col, sky, smoothstep(0.35, 0.90, r.y) * 0.85);

  float cloud = smoothstep(0.30, 0.90, f);
  float a = (cloud * 0.50 + ridge * 0.50) * uStrength;

  // Calmer toward the edges so text stays readable
  float vig = smoothstep(1.30, 0.25, length(uv - 0.5) * 1.25);
  a *= mix(0.72, 1.0, vig);

  col += ridge * 0.30;
  a += (hash(gl_FragCoord.xy + uTime) - 0.5) / 255.0;   // dither: no banding
  a = clamp(a, 0.0, 1.0);

  gl_FragColor = vec4(col * a, a);       // premultiplied alpha
}
`;

const RENDER_SCALE = 0.5;   // fraction of CSS pixels actually rendered
const FRAME_MS = 1000 / 30; // 30 fps cap
// When the OS has "reduce motion" on we do NOT freeze the background any more;
// it just flows much more slowly (a frozen background looked "broken").
const REDUCED_SPEED = 0.35;

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    console.warn('[AnimatedBackground] shader error:', gl.getShaderInfoLog(s));
    gl.deleteShader(s);
    return null;
  }
  return s;
}

// How bold the effect is per page: loud on the login/landing screen, calmer
// on data-heavy dashboard pages so text stays easy to read.
function strengthFor(pathname) {
  if (pathname === '/' || pathname.startsWith('/auth')) return 1.0;
  if (pathname === '/dashboard' || pathname === '/dashboard/') return 0.85;
  return 0.6;
}

export default function AnimatedBackground() {
  const canvasRef = useRef(null);
  const { pathname } = useLocation();
  const strengthTarget = useRef(strengthFor(pathname));
  strengthTarget.current = strengthFor(pathname);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;

    const gl = canvas.getContext('webgl', {
      alpha: true,
      premultipliedAlpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: 'low-power',
    });
    if (!gl) return undefined; // keep the CSS aurora fallback

    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return undefined;

    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return undefined;
    gl.useProgram(program);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(program, 'aPos');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(program, 'uRes');
    const uTime = gl.getUniformLocation(program, 'uTime');
    const uMouse = gl.getUniformLocation(program, 'uMouse');
    const uStrength = gl.getUniformLocation(program, 'uStrength');
    let strength = strengthTarget.current;

    const root = document.documentElement;
    root.classList.add('has-live-bg');

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const mouse = { x: 0.5, y: 0.5, tx: 0.5, ty: 0.5 };
    let raf = 0;
    let last = 0;
    let running = true;
    const start = performance.now();

    const resize = () => {
      const w = Math.max(2, Math.floor(window.innerWidth * RENDER_SCALE));
      const h = Math.max(2, Math.floor(window.innerHeight * RENDER_SCALE));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      gl.viewport(0, 0, w, h);
      gl.uniform2f(uRes, w, h);
    };

    const draw = (now) => {
      mouse.x += (mouse.tx - mouse.x) * 0.05;
      mouse.y += (mouse.ty - mouse.y) * 0.05;
      strength += (strengthTarget.current - strength) * 0.06;   // eased page-to-page change
      gl.uniform1f(uStrength, strength);
      gl.uniform1f(uTime, ((now - start) / 1000) * (reduced ? REDUCED_SPEED : 1) + 12);
      gl.uniform2f(uMouse, mouse.x, mouse.y);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const loop = (now) => {
      if (!running) return;
      raf = requestAnimationFrame(loop);
      if (now - last < FRAME_MS) return;
      last = now;
      draw(now);
    };

    const onPointer = (e) => {
      mouse.tx = e.clientX / window.innerWidth;
      mouse.ty = 1 - e.clientY / window.innerHeight;
    };
    const onVisibility = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!running) {
        running = true;
        raf = requestAnimationFrame(loop);
      }
    };
    const onLost = (e) => {
      e.preventDefault();
      running = false;
      cancelAnimationFrame(raf);
      root.classList.remove('has-live-bg'); // fall back to the CSS aurora
    };

    resize();
    window.addEventListener('resize', resize);
    canvas.addEventListener('webglcontextlost', onLost);
    window.addEventListener('pointermove', onPointer, { passive: true });
    document.addEventListener('visibilitychange', onVisibility);
    raf = requestAnimationFrame(loop);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointer);
      document.removeEventListener('visibilitychange', onVisibility);
      canvas.removeEventListener('webglcontextlost', onLost);
      root.classList.remove('has-live-bg');
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      gl.deleteBuffer(buf);
    };
  }, []);

  return <canvas ref={canvasRef} className="live-bg" aria-hidden="true" />;
}
