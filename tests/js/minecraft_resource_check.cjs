const assert = require('node:assert/strict');
const { harvestResource } = require('../../games/minecraft/resources.cjs');

async function run() {
  const resource = { name: 'oak_log', position: { x: 0, y: 74, z: 0, toArray() { return [0,74,0]; } } };
  let reachable = true, visible = true, active = true, current = resource, digs = 0, approaches = 0;
  const player = {
    entity: { position: { x: .5, y: 70, z: .5 } },
    canDigBlock: () => reachable, canSeeBlock: () => visible,
    blockAt: () => current, dig: async () => { digs++; }
  };
  const approach = async (position, horizontal) => {
    assert.deepEqual(position, [0,74,0]); assert.equal(horizontal, true);
    approaches++; reachable = true;
  };
  // A high, already reachable log must not trigger a path to its Y coordinate.
  assert.equal(await harvestResource(player, resource, approach, () => active), true);
  assert.equal(approaches, 0); assert.equal(digs, 1);
  reachable = false;
  await harvestResource(player, resource, approach, () => active);
  assert.equal(approaches, 1); assert.equal(digs, 2);
  reachable = false;
  assert.equal(await harvestResource(player, resource, async () => { active = false; }, () => active), false);
  assert.equal(digs, 2); // console put away during approach
  active = true; reachable = true; visible = false;
  await assert.rejects(harvestResource(player, resource, approach, () => active), /hidden/);
  visible = true; current = { ...resource, name: 'air' };
  await assert.rejects(harvestResource(player, resource, approach, () => active), /changed/);
  current = resource; player.entity.position.y = 75;
  await assert.rejects(harvestResource(player, resource, approach, () => active), /ground under/);
  assert.equal(digs, 2);
  console.log('Minecraft: reachable logs skip walking; horizontal approach; cancellation, occlusion and support checks.');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
