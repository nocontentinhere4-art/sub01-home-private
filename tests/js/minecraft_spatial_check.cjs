const assert = require('node:assert/strict');
const { supportsPlayer, escapeTarget, placementSite } = require('../../games/minecraft/spatial.cjs');

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
// The old fixed eastern position is occupied; search must find another site.
const blockAt = p => ({ name: p.y < 69 || (p.x === -4 && p.z === 1) ? 'stone' : 'air',
  boundingBox: p.y < 69 || (p.x === -4 && p.z === 1) ? 'block' : 'empty', position: p });
const site = placementSite(player, blockAt);
assert.ok(site);
assert.equal(blockAt(site.target).name, 'air');
assert.equal(site.support.boundingBox, 'block');
assert.ok(!(site.target.x === -4 && site.target.z === 1));
assert.equal(placementSite(player, () => null), null); // unloaded chunks
assert.equal(placementSite(player, () => ({ name: 'air', boundingBox: 'empty' })), null); // no floor
assert.equal(placementSite(player, blockAt, () => false), null); // obstructed view
// A fractional position crosses the next cell; that cell cannot be filled.
const edge = { x: .95, y: 69, z: .95 };
const soleSite = p => ({ name: p.y === 68 ? 'stone' : p.x === 1 && p.z === 1 && p.y === 69 ? 'air' : 'stone',
  boundingBox: p.y === 68 ? 'block' : 'empty', position: p });
assert.equal(placementSite(edge, soleSite), null);
console.log('Minecraft: protected support; escape distance; reachable placement with floor, visibility and body clearance.');
