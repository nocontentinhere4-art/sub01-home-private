const { supportsPlayer } = require('./spatial.cjs');

async function harvestResource(player, resource, approach, stillActive) {
  if (!resource) throw new Error('resource not visible');
  if (!stillActive()) return false;
  // Mineflayer measures reach from eye height. A visible high log can already
  // be dug even though no walkable node exists at the log's own Y coordinate.
  if (!player.canDigBlock(resource) || !player.canSeeBlock(resource))
    await approach(resource.position.toArray(), true);
  if (!stillActive()) return false;
  const current = player.blockAt(resource.position);
  if (!current || current.name !== resource.name) throw new Error('resource changed before collection');
  if (supportsPlayer(current.position, player.entity.position)) throw new Error('keep the ground under my feet');
  if (!player.canDigBlock(current) || !player.canSeeBlock(current)) throw new Error('resource out of reach or hidden');
  await player.dig(current);
  return true;
}

module.exports = { harvestResource };
