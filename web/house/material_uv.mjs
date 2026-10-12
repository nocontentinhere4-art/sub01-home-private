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

// CylinderGeometry's normalized UV otherwise maps a whole wood scan around a
// centimetre-scale handrail, and stretches its grain over the entire stair run.
// Keep grain along the cylinder axis; caps use the actual circular cross-section.
export function metricCylinderUv(geometry, radius, height, metresPerTile = 1) {
  if (![radius,height,metresPerTile].every(value=>Number.isFinite(value)&&value>0))
    throw new Error('Cylinder dimensions and texture coverage must be positive metres');
  const p=geometry.attributes.position,n=geometry.attributes.normal,uv=geometry.attributes.uv;
  if(!p||!n||!uv)return;
  for(let i=0;i<p.count;i++){
    if(Math.abs(n.getY(i))>.9)
      uv.setXY(i,p.getX(i)/metresPerTile,p.getZ(i)/metresPerTile);
    else
      uv.setXY(i,uv.getX(i)*Math.PI*2*radius/metresPerTile,(p.getY(i)+height/2)/metresPerTile);
  }
  uv.needsUpdate=true;
}
