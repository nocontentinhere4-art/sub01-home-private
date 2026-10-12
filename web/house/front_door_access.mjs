// Match the actual hinged leaf in home.js, in metres and radians.
export const FRONT_DOOR = Object.freeze({x:1.47,z:3.9,width:1.05,thickness:.075,radius:.16});
export function frontDoorApproach(position) {
  return !!position && position[1] < 3 && Math.hypot(position[0]-2,position[2]-3.9)<1.8;
}
export function frontDoorAllows(x,z,feet,angle) {
  if (feet>2.5) return true;
  if (!Number.isFinite(angle)) return false;
  const a=FRONT_DOOR,c=Math.cos(angle),s=Math.sin(angle),dx=x-a.x,dz=z-a.z;
  const localX=c*dx-s*dz,localZ=s*dx+c*dz;
  const nearestX=Math.max(0,Math.min(a.width,localX));
  const nearestZ=Math.max(-a.thickness/2,Math.min(a.thickness/2,localZ));
  return Math.hypot(localX-nearestX,localZ-nearestZ)>a.radius;
}
