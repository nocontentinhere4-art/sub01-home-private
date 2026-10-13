// Server-authoritative doors and room lights (home_interactions.py) for the page.
// Pure helpers: home.js keeps the animation, this decides the targets. Older
// servers without `doors`/`lights` keep the original proximity/lamp behaviour.
import {frontDoorAllows} from './front_door_access.mjs';
import {bathroomAllows} from './bathroom_access.mjs';
import {balconyAllows} from './balcony_access.mjs';

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

// Visitor doors. Each separates the house ("main") from a dead end ("dead":
// street, bathroom, balcony). A closed or locked door blocks main -> dead;
// a visitor on the dead side or in the doorway can always come back in, so
// nobody is ever shut in. `leaf` is the actual animated leaf parameter that
// the existing collider takes (front angle, bathroom leaf centre, balcony
// openness); `pass` checks only the fixed frame/wall, ignoring the leaf.
const BAND = .26;      // body radius + leaf half-thickness + margin
export const VISITOR_DOORS = Object.freeze({
  front: Object.freeze({upper: false, axis: 'z', plane: 3.9, dead: 1, span: [1.42, 2.57],
    approach: 1.8, allows: frontDoorAllows, pass: () => true}),
  bathroom: Object.freeze({upper: true, axis: 'x', plane: -.85, dead: -1, span: [.85, 1.8],
    approach: 1.6, allows: bathroomAllows, pass: (x, z, feet) => bathroomAllows(x, z, feet, 1e6)}),
  balcony: Object.freeze({upper: true, axis: 'z', plane: 3.85, dead: 1, span: [-2.725, -1.675],
    approach: 1.7, allows: balconyAllows, pass: (x, z, feet) => balconyAllows(x, z, feet, 1)}),
});

// 'main' | 'doorway' | 'dead' | 'other' (another floor) for a feet position.
export function doorSide(name, x, z, feet) {
  const d = VISITOR_DOORS[name];
  if (!d || ![x, z, feet].every(Number.isFinite)) return 'other';
  if ((feet > 2.5) !== d.upper) return 'other';
  const along = d.axis === 'z' ? z : x, across = d.axis === 'z' ? x : z;
  const s = (along - d.plane) * d.dead;
  if (Math.abs(s) <= BAND && across >= d.span[0] - .16 && across <= d.span[1] + .16) return 'doorway';
  return s > 0 ? 'dead' : 'main';
}

// 'open' | 'closed' | 'locked' from the server view, or null (older server).
export function doorState(server) {
  if (!server || typeof server.open !== 'boolean') return null;
  if (['open', 'closed', 'locked'].includes(server.state)) return server.state;
  return server.open ? 'open' : server.locked ? 'locked' : 'closed';
}

// May the visitor step from `from` [x, z] to `to` [x, z] past this door?
export function visitorDoorAllows(name, from, to, feet, state, leaf) {
  const d = VISITOR_DOORS[name];
  const [tx, tz] = to, [fx, fz] = from;
  if (!state) return d.allows(tx, tz, feet, leaf);           // legacy behaviour
  const a = doorSide(name, fx, fz, feet), b = doorSide(name, tx, tz, feet);
  // Already inside the leaf (it closed or swung onto him): any move that
  // does not go further in is allowed, against the fixed frame only.
  const stuck = !d.allows(fx, fz, feet, leaf);
  if (state === 'open') return d.allows(tx, tz, feet, leaf) || (stuck && d.pass(tx, tz, feet));
  if (a === 'other' && b === 'other') return d.allows(tx, tz, feet, leaf);
  if (a === 'dead') return d.pass(tx, tz, feet);              // always free to come back
  if (a === 'doorway') return b !== 'dead' && d.pass(tx, tz, feet);
  if (b === 'doorway' || b === 'dead') return false;          // closed: no entry
  return d.allows(tx, tz, feet, leaf) || (stuck && d.pass(tx, tz, feet));
}

// Should the leaf be shown open for this visitor? Open doors stay open; a
// closed or locked one opens from the inside (dead side or doorway) so he
// visibly lets himself out. Null for older servers (use proximity).
export function visitorDoorOpen(name, state, position) {
  if (!state) return null;
  if (state === 'open') return true;
  if (!Array.isArray(position) || position.length !== 3) return false;
  const [x, y, z] = position, feet = y - 1.65, d = VISITOR_DOORS[name];
  const side = doorSide(name, x, z, feet);
  if (side === 'doorway') return true;
  if (side !== 'dead') return false;
  const along = d.axis === 'z' ? z : x, across = d.axis === 'z' ? x : z;
  const mid = (d.span[0] + d.span[1]) / 2;
  return Math.hypot(along - d.plane, across - mid) < d.approach;
}

// Door leaf targets for the page. `camera` is the visitor's eye [x, y, z];
// `legacy` holds the old proximity results, used only for older servers.
export function doorTargets(state, camera, legacy = {}) {
  const out = {};
  for (const name of ['front', 'bathroom', 'balcony']) {
    const st = doorState(state?.doors?.[name]);
    out[name] = st ? !!visitorDoorOpen(name, st, camera) : !!legacy[name];
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
