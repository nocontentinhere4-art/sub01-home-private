// Match the existing upper-floor sliding bathroom leaf and wall opening.
export const BATHROOM_ACCESS = Object.freeze({
  plane: -.85, closed: 1.35, open: 2.3, leafWidth: .89, thickness: .065,
  openingStart: .85, openingEnd: 1.8, wallStart: .5, wallEnd: 2.7,
  radius: .16, clearance: .01, approach: 1.6,
});

export function bathroomApproach(position) {
  const a = BATHROOM_ACCESS;
  return !!position && position[1] > 3 &&
    Math.hypot(position[0] - a.plane, position[2] - a.closed) < a.approach;
}

export function bathroomDoorPosition(current, dt, open) {
  const a = BATHROOM_ACCESS;
  const target = open ? a.open : a.closed;
  return current + (target - current) * Math.min(1, Math.max(0, dt) * 8);
}

export function bathroomAllows(x, z, feet, leafCentre) {
  const a = BATHROOM_ACCESS, radius = a.radius + a.clearance;
  if (feet < 2.5 || Math.abs(x - a.plane) > radius + a.thickness / 2 ||
      z < a.wallStart - radius || z > a.wallEnd + radius) return true;
  // Fixed wall remains fixed even after the leaf has moved aside.
  if (z < a.openingStart + radius || z > a.openingEnd - radius) return false;
  if (!Number.isFinite(leafCentre)) return false;
  return z + radius <= leafCentre - a.leafWidth / 2 ||
    z - radius >= leafCentre + a.leafWidth / 2;
}
