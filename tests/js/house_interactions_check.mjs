import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {doorSide, doorState, doorTargets, fixtureLevel, houseStatus, roomLit, roomOf, visitorDoorAllows,
  visitorDoorOpen} from '../../web/house/house_interactions.mjs';

// Legacy server (no doors/lights): page proximity and master lamp decide.
assert.deepEqual(doorTargets({}, [0, 1.65, 0], {front: true}), {front: true, bathroom: false, balcony: false});
assert.equal(roomLit({}, 'kitchen', true), true);
assert.equal(roomLit({}, 'kitchen', false), false);

const door = (open, locked = false, mode = 'auto') => ({open, locked, mode});
const state = {
  doors: {front: door(false, true), bathroom: door(false, true), balcony: door(true)},
  lights: {master: true, dark: true, rooms: {
    living: {on: true, mode: 'auto'}, kitchen: {on: false, mode: 'off'},
    bedroom: {on: false, mode: 'auto'}, bathroom: {on: true, mode: 'auto'}}},
  presence: 'away',
};
// A closed or locked door does not open for a visitor approaching from the
// house; legacy proximity flags are ignored once the server reports doors.
assert.deepEqual(doorTargets(state, [2, 1.65, 3.2], {front: true, bathroom: true}),
  {front: false, bathroom: false, balcony: true});
assert.equal(doorTargets({doors: {front: door(false)}}, [2, 1.65, 3.2], {front: true}).front, false);
// From the dead-end side it opens so he can let himself back in.
assert.equal(doorTargets(state, [2, 1.65, 4.8]).front, true);
assert.equal(doorTargets(state, [-1.5, 4.65, 1.35]).bathroom, true);
assert.equal(doorState({open: false, locked: true}), 'locked');
assert.equal(doorState({open: true, locked: false, state: 'open'}), 'open');
assert.equal(doorState(null), null);
assert.equal(visitorDoorOpen('front', null, [2, 1.65, 4.8]), null);
assert.deepEqual(houseStatus(state), {presence: 'away', frontLocked: true, bathroomLocked: true});
assert.equal(houseStatus({presence: 'bogus'}).presence, 'home');

// Fixtures from home.js map onto the server's rooms.
assert.equal(roomOf([1.1, 1.35, -3.15]), 'living');      // warm desk light
assert.equal(roomOf([-2.7, 1.55, -3.45]), 'kitchen');    // kitchen work light
assert.equal(roomOf([-3.55, 3.768, -3.1]), 'bedroom');   // bedside light
assert.equal(roomOf([-2, 2.55, .5]), 'living');          // ground pendant
assert.equal(roomOf([2, 5.1, -.2]), 'bedroom');          // upper pendant
assert.equal(roomOf([NaN, 1, 1]), null);
assert.equal(fixtureLevel(state, [-2.7, 1.55, -3.45], true), 0);
assert.equal(fixtureLevel(state, [1.1, 1.35, -3.15], true), 1);
assert.equal(fixtureLevel({...state, lights: {...state.lights, master: false}}, [1.1, 1.35, -3.15], true), 0);

// The page zoning matches the actual server rule for every home waypoint.
const server = JSON.parse(execFileSync(process.env.SUB01_TEST_PYTHON || 'python3', ['-c', `
import json
from home_world import NODES
from home_interactions import room_of
print(json.dumps({k: [list(v), room_of(v)] for k, v in NODES.items()}))
`], {cwd: new URL('../..', import.meta.url)}).toString());
for (const [name, [position, room]] of Object.entries(server))
  assert.equal(roomOf(position), room, name);

// The live server view drives these helpers end to end.
const views = JSON.parse(execFileSync(process.env.SUB01_TEST_PYTHON || 'python3', ['-c', `
import json
from home_world import HomeWorld
h = HomeWorld({'node': 'loft'})
for _ in range(4000):
    h.update(.05, .05, {'activity': 'use_bathroom'}, {}, now=0)
    if not h.path: break
print(json.dumps(h.view(compact=True)))
`], {cwd: new URL('../..', import.meta.url)}).toString());
assert.equal(views.privacy, true);
assert.equal(doorTargets(views, {bathroom: true}).bathroom, false);
assert.equal(roomLit(views, 'bathroom'), true);

// ---- visitor movement through doors ----------------------------------
const DOORS = {
  front: {feet: 0, main: [2, 3.2], dead: [2, 4.8], closed: 0, open: -Math.PI * .48},
  bathroom: {feet: 3, main: [-.5, 1.35], dead: [-1.5, 1.35], closed: 1.35, open: 2.3},
  balcony: {feet: 3, main: [-2.2, 3.2], dead: [-2.2, 4.4], closed: 0, open: 1},
};
// Axis-separated steps exactly like home.js canWalk callers.
function walk(name, from, to, state, leaf, steps = 400) {
  const f = DOORS[name].feet;
  let [x, z] = from;
  for (let i = 0; i < steps; i++) {
    const dx = Math.max(-.02, Math.min(.02, to[0] - x)), dz = Math.max(-.02, Math.min(.02, to[1] - z));
    if (visitorDoorAllows(name, [x, z], [x + dx, z], f, state, leaf)) x += dx;
    if (visitorDoorAllows(name, [x, z], [x, z + dz], f, state, leaf)) z += dz;
  }
  return [x, z];
}
const near = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-6;
for (const [name, d] of Object.entries(DOORS)) {
  assert.equal(doorSide(name, ...d.main, d.feet), 'main', name);
  assert.equal(doorSide(name, ...d.dead, d.feet), 'dead', name);
  assert.equal(doorSide(name, ...d.dead, d.feet ? 0 : 3), 'other', name);
  // Open: passes both ways.
  assert.ok(near(walk(name, d.main, d.dead, 'open', d.open), d.dead), name + ' open entry');
  assert.ok(near(walk(name, d.dead, d.main, 'open', d.open), d.main), name + ' open exit');
  for (const st of ['closed', 'locked']) {
    // Closed/locked: no entry, even while the leaf is still visually open.
    for (const leaf of [d.closed, d.open]) {
      const end = walk(name, d.main, d.dead, st, leaf);
      assert.equal(doorSide(name, ...end, d.feet), 'main', `${name} ${st} blocks entry`);
    }
    // Never trapped: from the dead side or any doorway point he gets back in,
    // with the leaf shut or anywhere in between.
    assert.ok(near(walk(name, d.dead, d.main, st, d.closed), d.main), `${name} ${st} exit`);
    const mid = [(d.main[0] + d.dead[0]) / 2, (d.main[1] + d.dead[1]) / 2];
    for (const leaf of [d.closed, (d.closed + d.open) / 2, d.open])
      assert.ok(near(walk(name, mid, d.main, st, leaf), d.main), `${name} ${st} doorway exit`);
    // From the doorway he cannot continue further into the dead end.
    const deeper = walk(name, mid, d.dead, st, d.closed);
    assert.notEqual(doorSide(name, ...deeper, d.feet), 'dead', `${name} ${st} no entry from doorway`);
  }
}
// A leaf that swung onto the visitor never pins him: he can step off it.
assert.equal(visitorDoorAllows('front', [1.5, 3.2], [1.5, 4.5], 0, 'open', -Math.PI * .48), false, 'leaf is solid');
assert.ok(walk('front', [1.5, 4.5], [2, 4.5], 'open', -Math.PI * .48)[0] > 1.9);
// Fixed walls still apply when letting himself out of the bathroom.
assert.equal(visitorDoorAllows('bathroom', [-1.5, .55], [-.85, .55], 3, 'locked', 1.35), false);
// Another floor: the door's own collider decides (unchanged behaviour).
assert.equal(visitorDoorAllows('bathroom', [-.5, 1.35], [-1.5, 1.35], 0, 'locked', 1.35), true);
// Legacy server: exactly the old collider.
assert.equal(visitorDoorAllows('front', [2, 3.2], [2, 3.9], 0, null, 0), false);
assert.equal(visitorDoorAllows('front', [2, 3.2], [2, 3.9], 0, null, -Math.PI * .48), true);
console.log('house interactions ok');
