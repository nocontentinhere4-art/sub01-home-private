// Server-authoritative doors and room lights (home_interactions.py) for the page.
// Pure helpers: home.js keeps the animation, this decides the targets. Older
// servers without `doors`/`lights` keep the original proximity/lamp behaviour.

export const LIGHT_ROOMS = Object.freeze(['living', 'kitchen', 'bedroom', 'bathroom']);
const BATHROOM = Object.freeze({x0: -3.78, x1: -0.85, z0: .5, z1: 2.7});

// Same zoning as home_interactions.room_of, for light fixtures and positions.
export function roomOf(position) {
  if (!Array.isArray(position) || position.length !== 3 || !position.every(Number.isFinite)) return null;
  const [x, y, z] = position;
  if (y > 3) return x > BATHROOM.x0 && x < BATHROOM.x1 && z > BATHROOM.z0 && z < BATHROOM.z1
    ? 'bathroom' : 'bedroom';
  if (z > 3.9) return null;
  return x <= .7 && z < -1 ? 'kitchen' : 'living';
}

// Door targets. `local` holds the page's own proximity results for the free
// explore camera ({front, bathroom, balcony}); the server state is the
// character's. A locked bathroom never opens for anyone.
export function doorTargets(state, local = {}) {
  const doors = state && typeof state.doors === 'object' && state.doors ? state.doors : null;
  const out = {};
  for (const name of ['front', 'bathroom', 'balcony']) {
    const server = doors?.[name];
    const own = !!local[name];
    if (!server || typeof server.open !== 'boolean') { out[name] = own; continue; }
    if (server.locked) { out[name] = false; continue; }
    out[name] = server.open || (own && server.mode !== 'closed');
  }
  return out;
}

// Whether a room's fixtures are lit. Falls back to the legacy master lamp.
export function roomLit(state, room, lampOn = true) {
  const rooms = state?.lights?.rooms;
  if (!rooms || typeof rooms[room]?.on !== 'boolean') return !!lampOn;
  return rooms[room].on && state.lights.master !== false;
}

// Intensity multiplier for a fixture at a position (0 or 1).
export function fixtureLevel(state, position, lampOn = true) {
  const room = roomOf(position);
  return room && roomLit(state, room, lampOn) ? 1 : 0;
}

// Front-door lock and house presence for the status line / HUD.
export function houseStatus(state) {
  const presence = ['home', 'leaving', 'away', 'returning'].includes(state?.presence) ? state.presence : 'home';
  return {presence, frontLocked: !!state?.doors?.front?.locked, bathroomLocked: !!state?.doors?.bathroom?.locked};
}
