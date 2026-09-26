import { useEffect, useState } from "react";
import { PlugZap, RefreshCw, DatabaseZap, LayoutDashboard, CheckCircle2, Loader2 } from "lucide-react";
import { useBotName } from "../BotContext";

/**
 * BotDeckLoader — brutalist card-stack loader themed to the bot's own boot
 * sequence. Pure CSS/Tailwind animation, deliberately with NO framer-motion
 * (or any animation library) so it can never hit React/hook-version conflicts.
 *
 * Drop-in, same API as before:
 *   <Loader label="Loading your servers…" />
 *   <Loader fullscreen={false} label="Loading…" />
 */

const STEPS = [
  { id: 1, title: "CONNECTING", tag: "STEP 01", color: "bg-[var(--primary,#5865F2)]", icon: PlugZap },
  { id: 2, title: "SYNCING GUILDS", tag: "STEP 02", color: "bg-[var(--violet,#818cf8)]", icon: RefreshCw },
  { id: 3, title: "LOADING CONFIG", tag: "STEP 03", color: "bg-[var(--accent,#38bdf8)]", icon: DatabaseZap },
  { id: 4, title: "PREPARING UI", tag: "STEP 04", color: "bg-[var(--success,#34d399)]", icon: LayoutDashboard },
  { id: 5, title: "READY", tag: "STEP 05", color: "bg-[var(--pink,#f472b6)]", icon: CheckCircle2 },
];

// Where a card sits in the stack (0 = front/top) maps to a fixed transform.
// Because each card keeps the SAME DOM node (stable `key`) across reorders,
// changing these inline styles animates via the CSS `transition` below —
// no animation library required.
function stackStyle(position) {
  if (position >= STEPS.length) {
    // Cycled all the way to the back: shoot off to the side then reappear at the back.
    return { transform: "translate(160px, -30px) rotate(16deg) scale(0.9)", opacity: 0, zIndex: 0 };
  }
  const offsetY = position * 7;
  const offsetX = position * 3;
  const rotate = (position % 2 === 0 ? 1 : -1) * position * 2;
  const scale = 1 - position * 0.045;
  return {
    transform: `translate(${offsetX}px, ${offsetY}px) rotate(${rotate}deg) scale(${scale})`,
    opacity: 1,
    zIndex: STEPS.length - position,
  };
}

// How long each card stays on top before the next one slides in. Slower =
// easier to actually read each step; the progress bar is paced to match.
const CARD_DURATION_MS = 3400;
const PROGRESS_STEP_MS = Math.round(CARD_DURATION_MS / 100);

export function Loader({ label, fullscreen = true }) {
  const botName = useBotName();
  const brand = (botName || "Bot").trim();

  const [order, setOrder] = useState(STEPS.map((s) => s.id));
  const [progress, setProgress] = useState(0);

  // Card rotation — slow and deliberate.
  useEffect(() => {
    const cycle = setInterval(() => {
      setOrder((prev) => [...prev.slice(1), prev[0]]);
    }, CARD_DURATION_MS);
    return () => clearInterval(cycle);
  }, []);

  // Progress bar fills exactly once per card, then resets with the next one —
  // so it always finishes right as the card changes, instead of racing ahead.
  useEffect(() => {
    setProgress(0);
    const tick = setInterval(() => {
      setProgress((p) => Math.min(100, p + 1));
    }, PROGRESS_STEP_MS);
    return () => clearInterval(tick);
  }, [order[0]]);

  const wrapClass = fullscreen
    ? "fixed inset-0 z-[200] flex items-center justify-center p-8 antialiased"
    : "relative flex items-center justify-center p-6 antialiased";

  const wrapStyle = {
    background: fullscreen ? "var(--bg, #090b10)" : "transparent",
    backgroundImage: "radial-gradient(var(--border, rgba(255,255,255,0.14)) 1px, transparent 1px)",
    backgroundSize: "20px 20px",
  };

  return (
    <div className={wrapClass} style={wrapStyle} role="status" aria-live="polite">
      <div className="relative flex flex-col items-center">
        <div className="relative w-56 h-72 flex items-center justify-center [perspective:1200px]">
          {STEPS.map((card) => {
            const position = order.indexOf(card.id);
            const isTop = position === 0;
            const Icon = card.icon;
            return (
              <div
                key={card.id}
                className={`absolute w-56 h-72 border-[3px] border-black p-4 flex flex-col justify-between shadow-[7px_7px_0px_0px_rgba(0,0,0,0.85)] ${card.color} select-none text-black`}
                style={{
                  ...stackStyle(position),
                  transition: "transform 0.6s cubic-bezier(0.22,1,0.36,1), opacity 0.45s ease",
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="w-6 h-6 rounded-full border-2 border-black bg-white flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-black" />
                  </div>
                  <span className="text-[9px] font-mono font-black border-2 border-black bg-white px-1.5 py-0.5 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                    {card.tag}
                  </span>
                </div>

                <div className="flex flex-col items-center justify-center my-auto gap-2.5">
                  <div
                    className={`p-2.5 rounded-full border-2 border-black ${isTop ? "bg-black text-white animate-spin-slow" : "bg-white/60 text-black"}`}
                  >
                    <Icon size={20} />
                  </div>
                  <h3 className="text-lg font-black uppercase tracking-tight text-center leading-none">
                    {card.title}
                  </h3>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between items-center text-[9px] font-mono font-bold">
                    <span>STATUS</span>
                    <span>{isTop ? `${progress}%` : "—"}</span>
                  </div>
                  <div className="w-full h-3 border-2 border-black bg-white p-0.5 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                    <div
                      className="h-full bg-black"
                      style={{ width: `${isTop ? progress : 0}%`, transition: "width 0.06s linear" }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-8 flex items-center justify-center gap-2.5 bg-black text-white border-[3px] border-black px-4 py-2 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] font-mono text-[11px] font-bold uppercase w-fit z-10">
          <Loader2 className="animate-spin text-[var(--accent,#38bdf8)] shrink-0" size={14} />
          <span>{label || `LOADING ${brand.toUpperCase()}...`}</span>
        </div>
      </div>

      {/* Only this component needs the slow custom spin; kept scoped/local. */}
      <style>{`
        @keyframes deckSpinSlow { to { transform: rotate(360deg); } }
        .animate-spin-slow { animation: deckSpinSlow 3s linear infinite; }
        @media (prefers-reduced-motion: reduce) {
          .animate-spin-slow { animation: none; }
        }
      `}</style>
    </div>
  );
}

// Small inline spinner for buttons / tight spaces (unrelated to the deck above).
export function Spinner({ size = 16 }) {
  return (
    <span
      className="site-spinner"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  );
}

export default Loader;
