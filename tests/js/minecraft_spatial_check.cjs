const assert = require('node:assert/strict');
const { supportsPlayer, escapeTarget } = require('../../games/minecraft/spatial.cjs');

// Fractional and negative world coordinates must protect the support block.
const player = { x: -4.2, y: 69, z: 1.6 };
assert.equal(supportsPlayer({ x: -5, y: 68, z: 1 }, player), true);
assert.equal(supportsPlayer({ x: -4, y: 68, z: 1 }, player), false);
assert.equal(supportsPlayer({ x: -5, y: 69, z: 1 }, player), false);
assert.equal(supportsPlayer({ x: -5, y: 60, z: 1 }, player), false);
for (const threat of [{ x: -1, z: 1 }, { x: -9, z: -5 }, { x: -4.2, z: 1.6 }]) {
  const target = escapeTarget(player, threat);
  assert.equal(target[1], player.y);
  assert.ok(target.every(Number.isFinite));
  assert.ok(Math.abs(Math.hypot(target[0] - player.x, target[2] - player.z) - 6) < 1e-8);
  assert.ok(Math.hypot(target[0] - threat.x, target[2] - threat.z) > Math.hypot(player.x - threat.x, player.z - threat.z));
}
console.log('Minecraft: support blocks protected; escape increases distance from the threat.');
