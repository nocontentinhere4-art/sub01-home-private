// Change-triggered device refresh from the optional `devices` object of the
// private WebSocket home message. Without it (an older server) nothing changes
// and the page keeps its polling fallback. `{privacy:true}` clears the page's
// device state once and bumps the epoch, so responses requested before a
// privacy entry/exit can be recognised as stale and dropped.
export const DEVICE_KEYS = ["computer", "desk", "phone", "minecraft", "console_game"];

export function createDeviceRevisions({ refresh, onPrivacy = () => {} }) {
  let last = null, epoch = 0, privacy = false, running = false, again = false, resync = false;
  function run() {
    if (running) { again = true; return; }
    running = true;
    Promise.resolve().then(refresh).catch(() => {}).finally(() => {
      running = false;
      if (again) { again = false; run(); }
    });
  }
  return {
    get epoch() { return epoch; },
    get private() { return privacy; },
    // Returns the device keys whose identity changed (and triggered a refresh).
    accept(devices) {
      if (!devices || typeof devices !== "object") return [];
      if (devices.privacy) {
        if (!privacy) { privacy = true; epoch++; last = null; onPrivacy(); }
        return [];
      }
      if (privacy) { privacy = false; epoch++; resync = true; }
      const current = Object.fromEntries(DEVICE_KEYS.map(key => [key, devices[key] ?? null]));
      // The first message after load is a baseline (the page has just
      // synchronised); after privacy everything is refreshed once.
      const changed = !last ? (resync ? DEVICE_KEYS.slice() : [])
        : DEVICE_KEYS.filter(key => current[key] !== last[key]);
      last = current; resync = false;
      if (changed.length) run();
      return changed;
    },
  };
}
