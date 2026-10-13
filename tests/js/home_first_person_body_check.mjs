import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import * as T from '../../web/house/vendor/three.module.js';
import { GLTFLoader } from '../../web/house/vendor/GLTFLoader.js';
import { MeshoptDecoder } from '../../web/house/vendor/meshopt_decoder.module.js';
import { createFirstPersonBody, FirstPersonActionEvidence, matchingRestSkeleton, inPlaceCapture, capturedBasePose, FIRST_PERSON_CAPTURES } from '../../web/house/first_person_body.mjs';

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
body.group.traverse(o => { if (o.isSkinnedMesh && o.visible) meshList.push(o); if (o.isBone) bones.push(o); });
assert.equal(bones.length, 65, 'head, hips, legs and spine remain as animation parents');
assert.ok(meshList.length > 0);
const retained = new Set();
for (const mesh of meshList) {
  assert.equal(mesh.skeleton.bones.length, 65, 'no rebinding or joint-index remapping');
  for (const i of mesh.geometry.index.array) retained.add(i);
  assert.ok(mesh.geometry.getAttribute('skinWeight'));
}
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
body.step(1 / 60, home, computer, 0, true);
computer.commands++;
body.step(1 / 60, home, computer, 1, true);
assert.equal(body.group.visible, false, 'typing recovered contact but visual review remains outstanding');
body.step(.03, { ...home, walking: true }, computer, 2, true);
assert.equal(body.group.visible, false, 'walking camera and anatomy are awaiting review');
body.step(.03, { ...home, activity: 'phone' }, computer, 2, true);
assert.equal(body.group.visible, false, 'one-handed phone attachment requires measured right-palm contact and visual review');
console.log('PASS: unchanged original owner reference pose and skin, complete 65-bone hierarchy, actual authored finger tracks, real command evidence, preserved vertical gait with no double root travel, rejected mismatched rests, and visual/contact gates.');
