// Physical bounds of the rendered stair bodies and oak nosings (metres).
// Keep the walking ramp, but give its sides the same .16 m body clearance
// as furniture: point-only floor selection lets the camera enter the risers.
export const STAIR_CLEARANCE = Object.freeze({
  centre: .3, bottom: 2.55, top: -1.7, rise: 3, count: 17,
  run: .25, bodyWidth: .96, treadWidth: 1.02, treadDepth: .27,
  treadThickness: .035, treadOffset: .006, radius: .16,
  supportTolerance: .04, stepTolerance: .22, bodyHeight: 1.65,
});

export function stairClearanceAllows(x, z, feet) {
  const a = STAIR_CLEARANCE;
  if (![x,z,feet].every(Number.isFinite)) return false;
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
