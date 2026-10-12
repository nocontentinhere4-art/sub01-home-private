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

module.exports = { supportsPlayer, escapeTarget };
