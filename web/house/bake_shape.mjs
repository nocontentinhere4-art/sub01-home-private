// UV unwrapping can reorder and duplicate vertices. Compare positions rather
// than overall bounds: a changed cupboard inside a batch has the same bounds.
export function sameVertexPositions(a, b, tolerance = .0003) {
  const cell = .001;
  const key = (x, y, z) => `${x},${y},${z}`;
  const cloud = values => {
    const buckets = new Map();
    for (let i = 0; i < values.length; i += 3) {
      const x = values[i], y = values[i+1], z = values[i+2];
      if (![x,y,z].every(Number.isFinite)) return null;
      const k = key(Math.floor(x/cell), Math.floor(y/cell), Math.floor(z/cell));
      const points = buckets.get(k) || [];
      points.push(x,y,z); buckets.set(k,points);
    }
    return buckets;
  };
  const contains = (values, buckets) => {
    const limit = tolerance * tolerance;
    for (let i = 0; i < values.length; i += 3) {
      const x=values[i], y=values[i+1], z=values[i+2];
      const ix=Math.floor(x/cell), iy=Math.floor(y/cell), iz=Math.floor(z/cell);
      let found=false;
      for (let dx=-1; dx<=1 && !found; dx++)
        for (let dy=-1; dy<=1 && !found; dy++)
          for (let dz=-1; dz<=1 && !found; dz++) {
            const points=buckets.get(key(ix+dx,iy+dy,iz+dz));
            if (!points) continue;
            for (let j=0;j<points.length;j+=3) {
              if ((x-points[j])**2+(y-points[j+1])**2+(z-points[j+2])**2 <= limit) { found=true; break; }
            }
          }
      if (!found) return false;
    }
    return true;
  };
  if (!a.length || !b.length || a.length % 3 || b.length % 3) return false;
  const ca=cloud(a), cb=cloud(b);
  return !!ca && !!cb && contains(a,cb) && contains(b,ca);
}
