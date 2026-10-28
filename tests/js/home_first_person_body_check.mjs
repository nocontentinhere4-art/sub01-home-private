import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import * as T from '../../web/house/vendor/three.module.js';
import { GLTFLoader } from '../../web/house/vendor/GLTFLoader.js';
import { MeshoptDecoder } from '../../web/house/vendor/meshopt_decoder.module.js';
import { createFirstPersonBody, FirstPersonActionEvidence, matchingRestSkeleton, inPlaceCapture, capturedBasePose, FIRST_PERSON_CAPTURES,
  armTriangleIndices, bodyTriangleIndices, walkRate, CAMERA_EYE } from '../../web/house/first_person_body.mjs';
import { clipRate } from '../../web/room/gait.js';

import { productionGlb } from './first_person_asset_fixture.mjs';
const evidence = new FirstPersonActionEvidence();
const home = { activity: 'use_computer', place: 'desk', seated: 1, walking: false };
const computer = { commands: 10, ready: true, paused: false };
assert.notEqual(evidence.step(home, computer, 0, true), 'typing', 'joining must not replay a stale input');
computer.commands++;
assert.equal(evidence.step(home, computer, 1, true), 'typing');
assert.notEqual(evidence.step(home, computer, 7, true), 'typing', 'one command must not produce endless typing');
assert.equal(evidence.step({ ...home, walking: true }, computer, 2, true), 'walking_capture_required');
assert.equal(evidence.step({ ...home, privacy: true }, computer, 2, true), 'hidden');
assert.equal(evidence.step(home, computer, 2, false), 'hidden');

const scene = new T.Scene(); const statuses = [];
const body = createFirstPersonBody(T, scene, { loadAsync: productionGlb }, s => statuses.push(s));
assert.equal(await body.ready, true, JSON.stringify(statuses));
const meshList = []; const bones = [];
body.group.traverse(o => { if (o.isSkinnedMesh) meshList.push(o); if (o.isBone) bones.push(o); });
assert.equal(bones.length, 65, 'head, hips, legs and spine remain as animation parents');
const arms = meshList.filter(m => !/_body$/.test(m.name)), bodies = meshList.filter(m => /_body$/.test(m.name));
assert.ok(arms.length > 0 && bodies.length > 0, 'the arms alone for the seated captures, the body but the head for the walk');
for (const mesh of meshList) {
  assert.equal(mesh.skeleton.bones.length, 65, 'no rebinding or joint-index remapping');
  assert.ok(mesh.geometry.getAttribute('skinWeight'));
}
// the body meshes are the same skin on the same skeleton, less the head and the neck: no triangle keeps a vertex half
// weighted to them, and the arms' triangles are all in it
for (const mesh of bodies) {
  const src = arms.find(a => a.name + '_body' === mesh.name) || arms[0];
  assert.equal(mesh.skeleton, src.skeleton, 'one skeleton for both');
  const names = mesh.skeleton.bones.map(b => b.name), idx = mesh.geometry.index.array, sk = mesh.geometry.getAttribute('skinIndex'), sw = mesh.geometry.getAttribute('skinWeight');
  for (let i = 0; i < idx.length; i += 97) { let head = 0; for (let k = 0; k < 4; k++) if (/Head|Neck|Eye/.test(names[sk.getComponent(idx[i], k)])) head += sw.getComponent(idx[i], k); assert.ok(head < .5, 'no head or neck skin in the first-person body'); }
}
const loaded = statuses.find(s => s.state === 'loaded-awaiting-review');
assert.ok(loaded.bodyTriangles > loaded.armTriangles && loaded.armTriangles > 0, JSON.stringify(loaded));
assert.ok(Math.abs(loaded.eyeHeight - 1.61) < .03, 'the eye line from the rest skeleton: ' + loaded.eyeHeight);
// The owner glTF deliberately stores an initial T-reference pose that differs
// from its IBM bind pose. Preserve the source bytes; identity at rest is NOT a
// requirement of valid glTF skinning or evidence of an anatomy defect.
const { createHash } = await import('node:crypto');
const ownerBytes = await readFile(new URL('../../web/house/assets/first-person/owner.glb', import.meta.url));
const originalBytes = await readFile(new URL('../../web/room/char_mixamo.glb', import.meta.url));
assert.equal(createHash('sha256').update(ownerBytes).digest('hex'), createHash('sha256').update(originalBytes).digest('hex'),
  'original owner geometry, weights, IBM, texture and reference pose must be byte-identical');
for (const mode of ['typing', 'walking', 'phone']) {
  const capture = await productionGlb(FIRST_PERSON_CAPTURES[mode].url);
  const ownerBones = new Map(bones.map(b => [b.name, b]));
  assert.equal(matchingRestSkeleton(ownerBones, capture.scene), true);
  const forearm = capture.scene.getObjectByName('mixamorigRightForeArm');
  forearm.position.y += 2;
  assert.equal(matchingRestSkeleton(ownerBones, capture.scene), false);
  forearm.position.y -= 2;
  const clip = capture.animations[0];
  const movingFingers = clip.tracks.filter(t => /Hand(?:Thumb|Index|Middle|Ring|Pinky)/.test(t.name) &&
    t.values.some((v, i) => Math.abs(v - t.values[i % t.getValueSize()]) > .001));
  assert.ok(movingFingers.length >= 20, mode + ' retains authored finger articulation');
  if (mode === 'walking') {
    const inPlace = inPlaceCapture(clip);
    const base = capturedBasePose(T, clip);
    for (let i = 0; i < clip.tracks.length; i++) {
      const size = clip.tracks[i].getValueSize();
      assert.deepEqual(Array.from(base.tracks[i].values.slice(0, size)), Array.from(clip.tracks[i].values.slice(0, size)), 'base pose must be an actual captured frame');
      assert.deepEqual(Array.from(base.tracks[i].values.slice(size)), Array.from(clip.tracks[i].values.slice(0, size)), 'base idle hold must never introduce artificial articulation');
    }
    for (let i = 0; i < clip.tracks.length; i++) {
      const original = clip.tracks[i], fixed = inPlace.tracks[i];
      if (/Hips\.position$/.test(original.name)) {
        assert.ok(Math.max(...original.values.filter((_, k) => k % 3 === 0)) - Math.min(...original.values.filter((_, k) => k % 3 === 0)) > 1,
          'the real source contains horizontal movement that would otherwise duplicate server travel');
        for (let k = 0; k < fixed.values.length; k += 3) {
          assert.equal(fixed.values[k], original.values[0]);
          assert.equal(fixed.values[k + 2], original.values[2]);
          assert.equal(fixed.values[k + 1], original.values[k + 1], 'vertical authored gait preserved');
        }
      } else assert.deepEqual(fixed.values, original.values, 'all authored rotations and finger movement preserved');
    }
  }
}
// the walk's cadence from the server's speed: the gait model's rate for the capture's own step (1.4 m/s authored)
assert.ok(Math.abs(walkRate(1.2) - clipRate(1.2, 1, 1.4)) < 1e-9 && Math.abs(walkRate(1.2) - 0.857) < .002, walkRate(1.2));
assert.ok(walkRate(0.6) < walkRate(1.2) && walkRate(0.3) < walkRate(0.6), 'slower, fewer steps a second');
assert.equal(walkRate(undefined), 1, 'an older server without a speed: as recorded');
assert.equal(walkRate(0), 1);
body.step(1 / 60, home, computer, 0, true);
computer.commands++;
body.step(1 / 60, home, computer, 1, true);
assert.equal(body.group.visible, false, 'typing recovered contact but visual review remains outstanding');
// walking: the body (not the arms alone) stands on the floor under the camera, its eyes at the camera, facing its way,
// the walk playing at the speed's rate; reviewed from the eye (docs/design/natural-motion/2026-10-23)
const camera = new T.PerspectiveCamera(); camera.position.set(1.3, CAMERA_EYE + 0.2, -0.75); camera.rotation.set(-0.3, 0.7, 0, 'YXZ');
const walking = { ...home, place: 'aisle', seated: 0, walking: true, speed: 1.2 };
body.step(.03, walking, computer, 2, true, camera, () => 0.2);
assert.equal(body.group.visible, FIRST_PERSON_CAPTURES.walking.visualAccepted, 'the walk shows only as reviewed');
if (body.group.visible) {
  for (const m of meshList) assert.equal(m.visible, /_body$/.test(m.name), 'the walk shows the body, not the arms alone');
  assert.ok(Math.abs(body.group.position.y - 0.2) < 1e-6, 'the feet on the floor the page reports');
  assert.ok(body.group.scale.x > .9 && body.group.scale.x < 1.15 && Math.abs(body.group.scale.x - 1.65 / body.eyeHeight) < .01, 'the eyes at the camera by a uniform scale: ' + body.group.scale.x);
  assert.ok(Math.abs(body.group.rotation.y - (camera.rotation.y + Math.PI)) < 1e-6, 'facing where the camera looks');
  body.group.updateMatrixWorld(true);
  const head = bones.find(b => /Head$/.test(b.name)).getWorldPosition(new T.Vector3());
  assert.ok(Math.hypot(head.x - camera.position.x, head.z - camera.position.z) < .15, 'the head under and a little behind the camera');
  let active = null;
  for (const s of statuses) if (s.state === 'walking') active = s;
  assert.ok(active && active.visible, 'the status reports the walk shown');
  body.step(.03, { ...walking, speed: 0.6 }, computer, 2.03, true, camera, () => null);
  assert.ok(Math.abs(body.group.position.y - (camera.position.y - CAMERA_EYE)) < 1e-6, 'no floor known: the camera eye height down');
}
// standing still: the held first frame shows on his feet (reviewed: fp_idle_down.png), never under a seated camera
body.step(.03, { ...home, walking: false, activity: 'idle', place: 'aisle', seated: 0 }, computer, 3, true, camera, () => 0);
assert.equal(body.group.visible, FIRST_PERSON_CAPTURES.idle.visualAccepted, 'standing: the held base frame as reviewed');
body.step(.03, { ...home, walking: false, activity: 'watch_tv', place: 'desk', seated: 1 }, computer, 3.1, true, camera, () => 0);
assert.equal(body.group.visible, false, 'seated at the desk without typing evidence: no standing body under a seated camera');
body.step(.03, { ...home, walking: false, activity: 'idle', place: 'sofa', seated: 0.5 }, computer, 3.2, true, camera, () => 0);
assert.equal(body.group.visible, false, 'half seated: hidden');
body.step(.03, { ...home, activity: 'phone' }, computer, 4, true);
assert.equal(body.group.visible, false, 'one-handed phone attachment requires measured right-palm contact and visual review');
// the eye point stands EYE_FORWARD ahead of the Head joint: the camera is clear of the skull and the collar
body.step(.03, walking, computer, 5, true, camera, () => 0);
body.group.updateMatrixWorld(true);
const headNow = bones.find(b => /Head$/.test(b.name)).getWorldPosition(new T.Vector3());
const ahead = Math.hypot(headNow.x - camera.position.x, headNow.z - camera.position.z);
assert.ok(ahead > .10 && ahead < .14, 'the Head joint 12 cm behind the camera: ' + ahead);
let hoodShown = false; body.group.traverse(o => { if (o.isSkinnedMesh && o.visible && /hood/i.test(o.name)) hoodShown = true; });
assert.equal(hoodShown, false, 'the hood meshes (the lining faces the camera) are not part of the first-person body');
console.log('PASS: unchanged original owner reference pose and skin, complete 65-bone hierarchy, the body less the head for the walk, actual authored finger tracks, real command evidence, preserved vertical gait with no double root travel, cadence from the server speed, feet on the floor and eyes at the camera, rejected mismatched rests, and visual/contact gates.');
