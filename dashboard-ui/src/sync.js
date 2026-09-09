// Global auto-sync setting. When enabled, every edit saved in the dashboard is
// automatically replicated to ALL other servers the bot is in.
const KEY = 'gkr_auto_sync_all';

export function autoSyncEnabled() {
  return localStorage.getItem(KEY) !== 'off';
}

export function setAutoSyncEnabled(on) {
  localStorage.setItem(KEY, on ? 'on' : 'off');
}

// Attach the sync_all flag to any POST/PUT payload
export function withSync(data = {}) {
  return { ...data, sync_all: autoSyncEnabled() };
}

// Query params for DELETE requests
export function syncParams() {
  return autoSyncEnabled() ? { sync_all: 1 } : {};
}
