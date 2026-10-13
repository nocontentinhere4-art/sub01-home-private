// Physical bounds of the rendered stair bodies and oak nosings (metres).
// Keep the walking ramp, but give its sides the same .16 m body clearance
// as furniture: point-only floor selection lets the camera enter the risers.
export const STAIR_CLEARANCE = Object.freeze({
  centre: .3, bottom: 2.55, top: -1.7, rise: 3, count: 17,
  run: .25, bodyWidth: .96, treadWidth: 1.02, treadDepth: .27,
  treadThickness: .035, treadOffset: .006, radius: .16,
  // Eye height stays 1.65m in the camera/controller. The standing body extends
  // above the eyes; a 1.82m rounded capsule protects the actual head clearance.
  supportTolerance: .04, stepTolerance: .22, bodyHeight: 1.82,
  railXs: Object.freeze([-.25,.85]), railHeight:.9, railRadius:.03,
  postRadius:.013, postCount:9, postSpacing:.5,
  // Actual raised floor() support boxes. The painted loft edge can meet the
  // rounded head beside the stairs, even while the eye itself clears it.
  loftSlabs:Object.freeze([
    Object.freeze({x0:-4,x1:-.2,z0:-4,z1:4,low:2.88,high:3}),
    Object.freeze({x0:-.2,x1:.8,z0:-3.85,z1:-1.7,low:2.88,high:3}),
    Object.freeze({x0:-4,x1:-.2,z0:4,z1:5.25,low:2.88,high:3}),
  ]),
});

function segmentDistanceSquared(p, pEnd, q, qEnd) {
  const sub=(a,b)=>a.map((v,i)=>v-b[i]);
  const dot=(a,b)=>a.reduce((sum,v,i)=>sum+v*b[i],0);
  const clamp=v=>Math.max(0,Math.min(1,v));
  const u=sub(pEnd,p),v=sub(qEnd,q),r=sub(p,q);
  const a=dot(u,u),b=dot(u,v),c=dot(v,v),e=dot(u,r),f=dot(v,r);
  const denominator=a*c-b*b;
  let s=denominator>1e-10?clamp((b*f-c*e)/denominator):0;
  let t=(b*s+f)/c;
  if(t<0){t=0;s=clamp(-e/a);}
  else if(t>1){t=1;s=clamp((b-e)/a);}
  return r.reduce((sum,n,i)=>sum+(n+s*u[i]-t*v[i])**2,0);
}

export function stairRailsAllow(x,z,feet) {
  const a=STAIR_CLEARANCE;
  if(![x,z,feet].every(Number.isFinite))return false;
  // Grounded capsule: its rounded feet stay at floor height, not below it.
  const p=[x,feet+a.radius,z],end=[x,feet+a.bodyHeight-a.radius,z];
  const overlaps=(q,qEnd,radius)=>segmentDistanceSquared(p,end,q,qEnd)<(a.radius+radius)**2;
  for(const railX of a.railXs){
    if(overlaps([railX,a.railHeight,a.bottom],[railX,a.rise+a.railHeight,a.top],a.railRadius))return false;
    for(let i=0;i<a.postCount;i++){
      const railZ=a.bottom-i*a.postSpacing,h=a.rise*(a.bottom-railZ)/(a.bottom-a.top);
      if(overlaps([railX,h,railZ],[railX,h+a.railHeight,railZ],a.postRadius))return false;
    }
  }
  return true;
}

export function stairHeadroomAllows(x,z,feet) {
  const a=STAIR_CLEARANCE;
  if(![x,z,feet].every(Number.isFinite))return false;
  const lower=feet+a.radius,upper=feet+a.bodyHeight-a.radius;
  for(const slab of a.loftSlabs){
    // The landing is an intentional final climbable step/support, not a head
    // obstruction. Once on it, the capsule's rounded feet stay above the slab.
    if(slab.high<=feet+a.stepTolerance)continue;
    const dx=Math.max(0,slab.x0-x,x-slab.x1),dz=Math.max(0,slab.z0-z,z-slab.z1);
    const dy=Math.max(0,slab.low-upper,lower-slab.high);
    if(dx*dx+dy*dy+dz*dz<a.radius*a.radius)return false;
  }
  return true;
}

export function stairClearanceAllows(x, z, feet) {
  const a = STAIR_CLEARANCE;
  if (![x,z,feet].every(Number.isFinite)) return false;
  if (!stairHeadroomAllows(x,z,feet)) return false;
  if (!stairRailsAllow(x,z,feet)) return false;
  const ramp = Math.max(0, a.rise * (a.bottom - z) / (a.bottom - a.top));
  // Approach the climbable first riser before the centre reaches the ramp.
  const onRamp = z >= a.top - 1e-8 &&
    z <= a.bottom + (a.treadDepth - a.run) / 2 + a.radius &&
    x >= -.2 && x <= .8 && Math.abs(feet - ramp) <= a.stepTolerance;
  if (onRamp) {
    // Adjacent risers are intentional climbable steps, not solid walls.
    // The width is the real nosing minus the body radius on each side.
    return Math.abs(x - a.centre) <= a.treadWidth / 2 - a.radius;
  }
  const overlaps = (width, depth, centreZ, low, high) => {
    if (high <= feet + a.supportTolerance || low >= feet + a.bodyHeight) return false;
    const dx = Math.max(0, Math.abs(x - a.centre) - width / 2);
    const dz = Math.max(0, Math.abs(z - centreZ) - depth / 2);
    return dx * dx + dz * dz < a.radius * a.radius;
  };
  for (let i = 0; i < a.count; i++) {
    const centreZ = a.bottom - (i + .5) * a.run;
    const h = (i + 1) * a.rise / a.count;
    if (overlaps(a.bodyWidth, a.run, centreZ, 0, h) ||
        overlaps(a.treadWidth, a.treadDepth, centreZ,
          h + a.treadOffset - a.treadThickness / 2,
          h + a.treadOffset + a.treadThickness / 2)) return false;
  }
  return true;
}
