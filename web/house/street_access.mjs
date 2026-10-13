// A short real courtyard/pavement route; the distant panorama is not walkable.
export const STREET_ACCESS = Object.freeze({
  radius:.16, railRadius:.025, railZ:5.75,
  openingLeft:1.4, openingRight:2.6,
  // Include the real hinge/latch depth, not only the .034m bar thickness.
  gateX:1.4, gateZ:6.25, gateWidth:1.13, gateThickness:.10,
  sidewalkStart:6.52, sidewalkEnd:8.60, sidewalkLeft:-3.60, sidewalkRight:3.60,
});

export function streetGateAllows(x,z,angle) {
  const a=STREET_ACCESS;
  if(!Number.isFinite(angle)) return false;
  const c=Math.cos(angle),s=Math.sin(angle),dx=x-a.gateX,dz=z-a.gateZ;
  const localX=c*dx-s*dz,localZ=s*dx+c*dz;
  const nx=Math.max(0,Math.min(a.gateWidth,localX));
  const nz=Math.max(-a.gateThickness/2,Math.min(a.gateThickness/2,localZ));
  return Math.hypot(localX-nx,localZ-nz)>a.radius;
}

export function streetAccessAllows(x,z,gateAngle=-Math.PI*.53) {
  const a=STREET_ACCESS;
  if(z<=3.76) return true;
  if(z<4.12) return x>=1.63&&x<=2.37;
  if(z<=a.railZ-a.radius-a.railRadius)
    return x>=.8+a.radius+a.railRadius&&x<=3.2-a.radius-a.railRadius;
  // A .16m cylinder passes through the new rail gap and real pillar opening.
  if(z<a.sidewalkStart)
    return x>=a.openingLeft+a.radius+a.railRadius &&
      x<=a.openingRight-a.radius-a.railRadius && streetGateAllows(x,z,gateAngle);
  return z<=a.sidewalkEnd && x>=a.sidewalkLeft && x<=a.sidewalkRight &&
    streetGateAllows(x,z,gateAngle);
}

export function buildCourtyardFrontRail(beam,material) {
  const a=STREET_ACCESS;
  for(const [left,right] of [[.8,a.openingLeft],[a.openingRight,3.2]]) {
    beam([left,.9,a.railZ],[right,.9,a.railZ],.025,material);
    const count=Math.ceil((right-left)/.4);
    for(let i=0;i<=count;i++) {
      const x=left+(right-left)*i/count;
      beam([x,.06,a.railZ],[x,.9,a.railZ],.018,material);
    }
  }
}
