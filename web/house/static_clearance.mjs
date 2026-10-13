// Measured rigid geometry in the current private home (metres). These are
// body colliders, not new render geometry. Keep empty window/door gaps open.
export const STATIC_BODY_BOXES = Object.freeze([
  Object.freeze({name:'TV wall backing',x0:-3.91,x1:-3.77,z0:-1.125,z1:1.025,low:0,high:2.8}),
  Object.freeze({name:'Office oak shelves',x0:.95,x1:3.30,z0:-3.89,z1:-3.55,low:.125,high:2.5175}),
  Object.freeze({name:'Shower fixed glass',x0:-1.9925,x1:-1.9675,z0:1.65,z1:2.65,low:3.10,high:5.10}),
  // Actual frame(-2.2,4.65,-3.88,.9,1.2): backing plus art plane at z+.021.
  Object.freeze({name:'Loft wall art',x0:-2.67,x1:-1.73,z0:-3.8975,z1:-3.859,low:4.03,high:5.27}),
]);
export const SHOWER_TRAY = Object.freeze({x0:-1.95,x1:-1.05,z0:1.65,z1:2.65,top:3.13});

export function showerSupportHeight(x,z) {
  const s=SHOWER_TRAY;
  return x>=s.x0 && x<=s.x1 && z>=s.z0 && z<=s.z1 ? s.top : 3;
}

// Derive the rigid pot cylinder from the actual rendered mesh, including its
// local offset and fitted model scale. Leaves stay flexible and are not walls.
export function rigidPotFromMesh(T,mesh) {
  const a=mesh.geometry?.attributes?.position;
  if(!a || !a.count)return null;
  const low=new T.Vector3(Infinity,Infinity,Infinity),high=new T.Vector3(-Infinity,-Infinity,-Infinity);
  const v=new T.Vector3();
  for(let i=0;i<a.count;i++) {
    v.fromBufferAttribute(a,i).applyMatrix4(mesh.matrixWorld);
    low.min(v);high.max(v);
  }
  const x=(low.x+high.x)/2,z=(low.z+high.z)/2;
  let radius=0;
  for(let i=0;i<a.count;i++) {
    v.fromBufferAttribute(a,i).applyMatrix4(mesh.matrixWorld);
    radius=Math.max(radius,Math.hypot(v.x-x,v.z-z));
  }
  return {name:mesh.name,x,z,radius,low:low.y,high:high.y};
}

export function rigidBoxFromMesh(T,mesh) {
  mesh.updateWorldMatrix(true,false);
  const b=new T.Box3().setFromObject(mesh);
  return {name:mesh.name,x0:b.min.x,x1:b.max.x,z0:b.min.z,z1:b.max.z,low:b.min.y,high:b.max.y};
}

export function rigidBoxesFromInstances(T,mesh) {
  mesh.updateWorldMatrix(true,false);
  mesh.geometry.computeBoundingBox();
  const boxes=[],local=new T.Matrix4();
  for(let i=0;i<mesh.count;i++) {
    mesh.getMatrixAt(i,local);
    const b=mesh.geometry.boundingBox.clone().applyMatrix4(new T.Matrix4().multiplyMatrices(mesh.matrixWorld,local));
    boxes.push({name:mesh.name,x0:b.min.x,x1:b.max.x,z0:b.min.z,z1:b.max.z,low:b.min.y,high:b.max.y});
  }
  return boxes;
}

export function staticBodyAllows(x,z,feet,pots=[],boundaryBoxes=[],height=1.82,radius=.16) {
  if(![x,z,feet,height,radius].every(Number.isFinite))return false;
  const lower=feet+radius,upper=feet+height-radius;
  for(let i=0;i<STATIC_BODY_BOXES.length+boundaryBoxes.length;i++) {
    const b=i<STATIC_BODY_BOXES.length?STATIC_BODY_BOXES[i]:boundaryBoxes[i-STATIC_BODY_BOXES.length];
    const dx=Math.max(0,b.x0-x,x-b.x1),dz=Math.max(0,b.z0-z,z-b.z1);
    const dy=Math.max(0,b.low-upper,lower-b.high);
    if(dx*dx+dy*dy+dz*dz<radius*radius)return false;
  }
  for(const p of pots) {
    const horizontal=Math.max(0,Math.hypot(x-p.x,z-p.z)-p.radius);
    const vertical=Math.max(0,p.low-upper,lower-p.high);
    if(horizontal*horizontal+vertical*vertical<radius*radius)return false;
  }
  // The real upper balcony slab ends at x=-.2. Its unrailed corner must
  // support the whole standing foot/body footprint, not an imaginary strip.
  if(feet>=2.5 && z>=4 && z<=5.25 && x>-.2-radius)return false;
  return true;
}
