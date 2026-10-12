import assert from 'node:assert/strict';
import * as T from 'three';
import { createCurtainPanel } from '../../web/house/curtain_panels.mjs';

const shared = new T.MeshStandardMaterial();
for (const direction of [-1, 1]) {
  const panel = createCurtainPanel(T, shared, { direction });
  const geometry = panel.mesh.geometry;
  const closed = geometry.boundingBox.clone();
  const uv = Array.from(geometry.attributes.uv.array);
  assert(Math.abs(closed.max.x - closed.min.x - 1.8) < .0001);
  assert(panel.group.userData.excludeStaticBake && panel.mesh.userData.excludeStaticBake);
  assert.equal(panel.group.children.length, 1);
  assert.equal(geometry.index.count / 3, 5120);
  assert.notEqual(panel.mesh.material, shared);
  assert.equal(shared.side, T.FrontSide);

  panel.setOpen(true);
  const beforeAnimation = panel.state().width;
  panel.update(1 / 60);
  assert(panel.state().width < beforeAnimation && panel.state().width > .306);
  for (let i = 0; i < 240; i++) panel.update(1 / 60);
  assert(Math.abs(panel.state().width - .306) < .0001);
  assert.deepEqual(Array.from(geometry.attributes.uv.array), uv);
  const open = geometry.boundingBox;
  assert(open.max.z - open.min.z > closed.max.z - closed.min.z);

  // Gathering moves folds, while conserving cloth length and texture coordinates.
  const positions = geometry.attributes.position;
  let length = 0;
  for (let i = 1; i <= 128; i++) {
    const a = 10 * 129 + i, b = a - 1;
    length += Math.hypot(positions.getX(a) - positions.getX(b), positions.getZ(a) - positions.getZ(b));
  }
  assert(Math.abs(length - panel.clothLength) < .0002);
  assert(Array.from(positions.array).every(Number.isFinite));
  assert.equal(panel.update(Number.NaN), false);
  panel.setOpen(false, { immediate: true });
  assert(Math.abs(panel.state().width - 1.8) < .0001);
  const indices = geometry.index.array;
  assert(Math.max(...indices) < positions.count);
  panel.dispose();
}
assert.throws(() => createCurtainPanel(T, shared, { width: Infinity }), /Invalid curtain/);
assert.throws(() => createCurtainPanel(T, shared, { height: 0 }), /Invalid curtain/);
console.log('Curtain geometry, continuous gathering, conserved cloth length, metric UV and shared material checks passed.');
