import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {doorTargets, fixtureLevel, houseStatus, roomLit, roomOf} from '../../web/house/house_interactions.mjs';

// Legacy server (no doors/lights): page proximity and master lamp decide.
assert.deepEqual(doorTargets({}, {front: true}), {front: true, bathroom: false, balcony: false});
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
// A locked door ignores the explore camera; a closed-mode door too.
assert.deepEqual(doorTargets(state, {front: true, bathroom: true, balcony: false}),
  {front: false, bathroom: false, balcony: true});
assert.equal(doorTargets({doors: {front: door(false, false, 'closed')}}, {front: true}).front, false);
assert.equal(doorTargets({doors: {front: door(false)}}, {front: true}).front, true);
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
console.log('house interactions ok');
