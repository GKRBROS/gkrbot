import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import api from "../../api";

function groupByCategory(stations = []) {
  const groups = {};
  for (const s of stations) {
    if (!groups[s.category]) groups[s.category] = [];
    groups[s.category].push(s);
  }
  return groups;
}

function Radio() {
  const { guildId } = useParams();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionPending, setActionPending] = useState(false);
  const [localVolume, setLocalVolume] = useState(100);
  const volumeDebounce = useRef(null);
  const isDragging = useRef(false);

  const fetchState = async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/radio`);
      setState(res.data);
      setError("");
      if (!isDragging.current) setLocalVolume(res.data.volume ?? 100);
    } catch (err) {
      if (err.response?.status !== 404) setError("Failed to load radio state.");
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 4000);
    return () => clearInterval(interval);
  }, [guildId]);

  const control = async (action, extra = {}) => {
    setActionPending(true);
    try {
      await api.post(`/guilds/${guildId}/radio/control`, { action, ...extra });
      await fetchState();
    } catch (err) {
      alert(err.response?.data?.error || "Action failed");
    }
    setActionPending(false);
  };

  const handleVolumeChange = (val) => {
    isDragging.current = true;
    setLocalVolume(val);
    if (volumeDebounce.current) clearTimeout(volumeDebounce.current);
    volumeDebounce.current = setTimeout(() => {
      isDragging.current = false;
      control("set_volume", { volume: val });
    }, 400);
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: "320px", marginBottom: "24px" }}></div>
        <div className="skeleton" style={{ height: "220px" }}></div>
      </div>
    );
  }

  const stations = state?.stations ?? [];
  const stationGroups = groupByCategory(stations);
  const isActive = state?.active;
  const isPaused = state?.paused;
  const is247 = state?.mode_247;
  const currentStationKey = state?.station_key;
  const currentStation = stations.find((s) => s.key === currentStationKey);

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">📻 Radio Station</h1>
        <p className="page-subtitle">
          24/7 ultra-low CPU radio streaming — control stations directly from the dashboard.
        </p>
      </div>

      {error && (
        <div
          style={{
            background: "rgba(237,66,69,0.12)",
            border: "1px solid rgba(237,66,69,0.4)",
            borderRadius: "12px",
            padding: "14px 20px",
            marginBottom: "20px",
            color: "#ed4245",
            fontSize: "14px",
          }}
        >
          ⚠️ {error}
        </div>
      )}

      <div className="grid-2" style={{ gap: "24px" }}>
        {/* Left: Now Playing */}
        <div
          className="glass-panel"
          style={{ padding: "28px", display: "flex", flexDirection: "column", gap: "20px" }}
        >
          {/* Station banner */}
          <div
            style={{
              borderRadius: "16px",
              overflow: "hidden",
              position: "relative",
              background: isActive
                ? "linear-gradient(135deg, #6366f1 0%, #818cf8 40%, #22d3ee 100%)"
                : "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)",
              padding: "32px 24px",
              textAlign: "center",
              boxShadow: isActive ? "0 8px 32px rgba(99,102,241,0.35)" : "none",
              transition: "all 0.4s ease",
            }}
          >
            {isActive && !isPaused && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  overflow: "hidden",
                  borderRadius: "16px",
                  opacity: 0.15,
                }}
              >
                {[...Array(4)].map((_, i) => (
                  <div
                    key={i}
                    style={{
                      position: "absolute",
                      bottom: "-20px",
                      left: "50%",
                      transform: "translateX(-50%)",
                      width: `${80 + i * 40}px`,
                      height: `${80 + i * 40}px`,
                      borderRadius: "50%",
                      border: "2px solid white",
                      animation: `radioWave 2s ease-out ${i * 0.4}s infinite`,
                    }}
                  />
                ))}
              </div>
            )}

            <div style={{ fontSize: "52px", marginBottom: "12px", position: "relative" }}>
              {currentStation?.emoji ?? "📻"}
            </div>
            <div
              style={{
                fontSize: "20px",
                fontWeight: 800,
                color: "white",
                lineHeight: 1.2,
                position: "relative",
              }}
            >
              {isActive ? currentStation?.name ?? "Unknown Station" : "No Station Playing"}
            </div>
            <div
              style={{
                fontSize: "13px",
                color: isActive ? "rgba(255,255,255,0.8)" : "var(--text-muted)",
                marginTop: "8px",
                position: "relative",
              }}
            >
              {isActive
                ? currentStation?.desc ?? ""
                : "Use /radio play in Discord or pick a station below"}
            </div>

            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                marginTop: "16px",
                padding: "5px 14px",
                borderRadius: "999px",
                background: "rgba(0,0,0,0.3)",
                backdropFilter: "blur(8px)",
                fontSize: "12px",
                fontWeight: 700,
                color: "white",
                position: "relative",
              }}
            >
              <span
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: isActive ? (isPaused ? "#fbbf24" : "#4ade80") : "#6b7280",
                  boxShadow: isActive && !isPaused ? "0 0 8px #4ade80" : "none",
                  animation: isActive && !isPaused ? "pulse 2s ease-in-out infinite" : "none",
                }}
              />
              {isActive ? (isPaused ? "⏸ Paused" : "🟢 Live") : "⏹ Offline"}
            </div>
          </div>

          {/* Playback controls */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "12px",
            }}
          >
            <button
              className={`btn ${isPaused ? "btn-primary" : "btn-ghost"}`}
              style={{ borderRadius: "50%", width: "44px", height: "44px", fontSize: "18px" }}
              onClick={() => control(isPaused ? "resume" : "pause")}
              disabled={!isActive || actionPending}
              title={isPaused ? "Resume" : "Pause"}
            >
              {isPaused ? "▶️" : "⏸️"}
            </button>
            <button
              className="btn btn-danger"
              style={{ borderRadius: "50%", width: "44px", height: "44px", fontSize: "18px" }}
              onClick={() => control("stop")}
              disabled={!isActive || actionPending}
              title="Stop and Disconnect"
            >
              ⏹️
            </button>
          </div>

          {/* Volume */}
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "8px",
              }}
            >
              <span style={{ fontSize: "13px", color: "var(--text-sub)", fontWeight: 600 }}>
                🔈 Volume
              </span>
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 700,
                  color: "var(--primary)",
                  background: "rgba(99,102,241,0.12)",
                  padding: "2px 10px",
                  borderRadius: "999px",
                }}
              >
                {localVolume}%
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="200"
              value={localVolume}
              onChange={(e) => handleVolumeChange(Number(e.target.value))}
              style={{ width: "100%", accentColor: "var(--primary)", cursor: "pointer" }}
            />
          </div>

          {/* 24/7 toggle */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 16px",
              borderRadius: "12px",
              background: is247 ? "rgba(99,102,241,0.12)" : "rgba(255,255,255,0.03)",
              border: `1px solid ${is247 ? "rgba(99,102,241,0.35)" : "var(--border)"}`,
              transition: "all 0.2s ease",
              cursor: "pointer",
            }}
            onClick={() => !actionPending && control("toggle_247")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") control("toggle_247");
            }}
          >
            <div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-main)" }}>
                🔁 24/7 Mode
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
                {is247
                  ? "Bot auto-reconnects on drop or restart"
                  : "Bot disconnects when not playing"}
              </div>
            </div>
            <div
              style={{
                width: "44px",
                height: "24px",
                borderRadius: "999px",
                background: is247 ? "var(--primary)" : "rgba(255,255,255,0.1)",
                position: "relative",
                transition: "background 0.2s ease",
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: "3px",
                  left: is247 ? "22px" : "3px",
                  width: "18px",
                  height: "18px",
                  borderRadius: "50%",
                  background: "white",
                  transition: "left 0.2s ease",
                  boxShadow: "0 1px 4px rgba(0,0,0,0.3)",
                }}
              />
            </div>
          </div>

          {/* Voice channel */}
          {isActive && state?.voice_channel_name && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                padding: "12px 16px",
                borderRadius: "10px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--border)",
              }}
            >
              <span style={{ fontSize: "18px" }}>🔊</span>
              <div>
                <div
                  style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "2px" }}
                >
                  Connected to
                </div>
                <div
                  style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-main)" }}
                >
                  {state.voice_channel_name}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Station Library */}
        <div
          className="glass-panel"
          style={{
            padding: "24px",
            display: "flex",
            flexDirection: "column",
            gap: "16px",
            overflowY: "auto",
            maxHeight: "600px",
          }}
        >
          <div
            style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-main)", marginBottom: "4px" }}
          >
            📡 Station Library
          </div>

          {Object.entries(stationGroups).map(([category, categoryStations]) => (
            <div key={category}>
              <div
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  marginBottom: "8px",
                  paddingLeft: "4px",
                }}
              >
                {category}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {categoryStations.map((station) => {
                  const isSelected = station.key === currentStationKey && isActive;
                  return (
                    <div
                      key={station.key}
                      onClick={() => !actionPending && control("set_station", { station_key: station.key })}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ")
                          control("set_station", { station_key: station.key });
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "12px",
                        padding: "10px 14px",
                        borderRadius: "10px",
                        cursor: actionPending ? "not-allowed" : "pointer",
                        background: isSelected
                          ? "rgba(99,102,241,0.18)"
                          : "rgba(255,255,255,0.03)",
                        border: `1px solid ${
                          isSelected ? "rgba(99,102,241,0.45)" : "var(--border)"
                        }`,
                        transition: "all 0.15s ease",
                        opacity: actionPending ? 0.6 : 1,
                      }}
                    >
                      <span style={{ fontSize: "22px", flexShrink: 0 }}>{station.emoji}</span>
                      <div style={{ flex: 1, overflow: "hidden" }}>
                        <div
                          style={{
                            fontSize: "14px",
                            fontWeight: isSelected ? 700 : 500,
                            color: isSelected ? "#a5b4fc" : "var(--text-main)",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {station.name}
                        </div>
                        <div
                          style={{
                            fontSize: "12px",
                            color: "var(--text-muted)",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {station.desc}
                        </div>
                      </div>
                      {isSelected && (
                        <div
                          style={{
                            fontSize: "10px",
                            fontWeight: 800,
                            color: "#4ade80",
                            background: "rgba(74,222,128,0.12)",
                            padding: "2px 8px",
                            borderRadius: "999px",
                            flexShrink: 0,
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          <span
                            style={{
                              width: "6px",
                              height: "6px",
                              borderRadius: "50%",
                              background: "#4ade80",
                              display: "inline-block",
                              animation: isPaused
                                ? "none"
                                : "pulse 1.5s ease-in-out infinite",
                            }}
                          />
                          {isPaused ? "PAUSED" : "LIVE"}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {stations.length === 0 && (
            <div
              style={{
                textAlign: "center",
                color: "var(--text-muted)",
                padding: "40px 0",
              }}
            >
              📻 No stations available
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes radioWave {
          0% { transform: translateX(-50%) scale(0.2); opacity: 1; }
          100% { transform: translateX(-50%) scale(1); opacity: 0; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}

export default Radio;
