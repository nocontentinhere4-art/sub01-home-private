// Spatial rules shared by the real player and focused regression checks.
function supportsPlayer(block, position) {
  return block.x === Math.floor(position.x) && block.z === Math.floor(position.z)
    && block.y < position.y && block.y >= Math.floor(position.y) - 1;
}

function escapeTarget(position, threat, distance = 6) {
  const dx = position.x - threat.x, dz = position.z - threat.z;
  const length = Math.hypot(dx, dz);
  if (length < .01) return [position.x + distance, position.y, position.z];
  return [position.x + dx / length * distance, position.y, position.z + dz / length * distance];
}

// Search actual loaded blocks rather than assuming the cell east of the player
// has a solid floor. Keep the complete player volume clear at block boundaries.
function placementSite(position, blockAt, visible = () => true) {
  const feet = { x: Math.floor(position.x), y: Math.floor(position.y), z: Math.floor(position.z) };
  const empty = new Set(['air', 'cave_air', 'void_air']);
  for (let radius = 1; radius <= 2; radius++) {
    for (const dy of [0, -1, 1]) for (let dx = -radius; dx <= radius; dx++) {
      for (let dz = -radius; dz <= radius; dz++) {
        if (Math.max(Math.abs(dx), Math.abs(dz)) !== radius) continue;
        const target = { x: feet.x + dx, y: feet.y + dy, z: feet.z + dz };
        const overlaps = target.x < position.x + .3 && target.x + 1 > position.x - .3
          && target.z < position.z + .3 && target.z + 1 > position.z - .3
          && target.y < position.y + 1.8 && target.y + 1 > position.y;
        if (overlaps) continue;
        const reach = Math.hypot(target.x + .5 - position.x,
          target.y - (position.y + 1.62), target.z + .5 - position.z);
        if (reach > 4.25) continue;
        const space = blockAt(target);
        const support = blockAt({ x: target.x, y: target.y - 1, z: target.z });
        if (!space || !empty.has(space.name) || support?.boundingBox !== 'block' || !visible(support)) continue;
        return { support, target };
      }
    }
  }
  return null;
}

module.exports = { supportsPlayer, escapeTarget, placementSite };
