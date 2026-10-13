import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import * as T from '../../web/house/vendor/three.module.js';
import {BATH_FALLBACK_CALLS, findReplacedPrimitives, parsePrimitiveCall, sameCalls}
  from '../../web/house/replaced_primitives.mjs';

// Same placement rules as home.js box/cylinder/beam (BoxGeometry has the same
// bounds as the RoundedBoxGeometry home.js uses).
const box = (w, h, d, x, y, z) => { const o = new T.Mesh(new T.BoxGeometry(w, h, d)); o.position.set(x, y, z); return o; };
const cylinder = (r, h, x, y, z) => { const o = new T.Mesh(new T.CylinderGeometry(r, r, h, 24)); o.position.set(x, y, z); return o; };
function beam(a, b, r) {
  const A = new T.Vector3(...a), B = new T.Vector3(...b), D = B.clone().sub(A);
  const o = new T.Mesh(new T.CylinderGeometry(r, r, D.length(), 10));
  o.position.copy(A.add(B).multiplyScalar(.5));
  o.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), D.normalize());
  return o;
}

assert.deepEqual(parsePrimitiveCall('box(0.62, 0.66, 0.48, -3.5, 3.36, 1.1, M.wood, 0.02);'),
  {kind: 'box', position: [-3.5, 3.36, 1.1], size: [.62, .66, .48]});
assert.deepEqual(parsePrimitiveCall('const bathDoor = box(0.065, 2, 0.89, -0.85, 4.05, 1.35, M.darkwood, 0.012);').position,
  [-.85, 4.05, 1.35]);
assert.deepEqual(parsePrimitiveCall('cylinder(0.12, 0.05, -3.5, 3.81, 1.1, M.white);').size, [.24, .05, .24]);
const b = parsePrimitiveCall('beam([-3.5, 3.8, 0.92], [-3.5, 4.01, 0.92], 0.017, M.brass);');
assert.equal(b.kind, 'beam');
assert.ok(Math.abs(b.position[1] - 3.905) < 1e-9 && Math.abs(b.size[1] - .21) < 1e-9);
assert.throws(() => parsePrimitiveCall('obstacle(-3.5, 1.1, 0.68, 0.5, 1);'), /Not a home.js primitive/);

// The actual home.js fallback lines, built like home.js builds them.
const scene = [
  box(0.62, 0.66, 0.48, -3.5, 3.36, 1.1), box(0.68, 0.1, 0.5, -3.5, 3.73, 1.1),
  cylinder(0.12, 0.05, -3.5, 3.81, 1.1),
  beam([-3.5, 3.8, 0.92], [-3.5, 4.01, 0.92], 0.017), beam([-3.5, 4.01, 0.92], [-3.5, 4.01, 1.04], 0.017),
  box(0.42, 0.42, 0.6, -2.9, 3.24, 2.23), box(0.43, 0.64, 0.18, -2.9, 3.47, 2.49), box(0.36, 0.04, 0.46, -2.9, 3.48, 2.18),
  box(0.9, 0.1, 1, -1.5, 3.08, 2.15),                                // shower tray: never touched
];
const vanity = findReplacedPrimitives(scene, BATH_FALLBACK_CALLS.vanity);
assert.deepEqual(vanity, scene.slice(0, 5));
assert.deepEqual(findReplacedPrimitives(scene, BATH_FALLBACK_CALLS.toilet), scene.slice(5, 8));
// Ambiguity or absence refuses instead of hiding the wrong thing.
assert.throws(() => findReplacedPrimitives([...scene, box(0.62, 0.66, 0.48, -3.5, 3.36, 1.1)], BATH_FALLBACK_CALLS.vanity), /found 2/);
assert.throws(() => findReplacedPrimitives(scene.slice(1), BATH_FALLBACK_CALLS.vanity), /found 0/);
assert.throws(() => findReplacedPrimitives(scene, []), /No replaced/);
assert.ok(sameCalls([...BATH_FALLBACK_CALLS.toilet], BATH_FALLBACK_CALLS.toilet));
assert.ok(!sameCalls(BATH_FALLBACK_CALLS.toilet.slice(1), BATH_FALLBACK_CALLS.toilet));
assert.ok(!sameCalls(null, BATH_FALLBACK_CALLS.toilet));

// The list matches the generator and the current home.js literals.
const python = process.env.SUB01_TEST_PYTHON || 'python3';
const generator = JSON.parse(execFileSync(python, ['-c', `
import json, sys
sys.path.insert(0, 'tools')
import build_home_bath_fixtures as b
print(json.dumps({k: v['replaces_home_js'] for k, v in b.FIXTURES.items()}))
`], {cwd: new URL('../..', import.meta.url)}).toString());
assert.deepEqual(generator, JSON.parse(JSON.stringify(BATH_FALLBACK_CALLS)));
const home = fs.readFileSync(new URL('../../web/house/home.js', import.meta.url), 'utf8');
for (const call of Object.values(BATH_FALLBACK_CALLS).flat()) assert.ok(home.includes('\n' + call + '\n'), call);
console.log('replaced primitives ok');
