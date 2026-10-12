// Box furniture uses metres, so grain does not stretch with each cabinet door.
export function metricBoxUv(geometry, metresPerTile = 1) {
  const p = geometry.attributes.position, n = geometry.attributes.normal, uv = geometry.attributes.uv;
  if (!p || !n || !uv) return;
  for (let i = 0; i < p.count; i++) {
    const x = Math.abs(n.getX(i)), y = Math.abs(n.getY(i)), z = Math.abs(n.getZ(i));
    const u = x > y && x > z ? p.getZ(i) : p.getX(i);
    const v = y > x && y > z ? p.getZ(i) : p.getY(i);
    uv.setXY(i, u / metresPerTile, v / metresPerTile);
  }
  uv.needsUpdate = true;
}
