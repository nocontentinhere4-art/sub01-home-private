import assert from "node:assert/strict";
import { WalkMotion } from "../../web/house/walk_motion.mjs";
function trajectory(dt) {
  const motion = new WalkMotion();
  let distance = 0;
  for (let i = 0; i < Math.round(1 / dt); i++) {
    const old = motion.x,
      [dx] = motion.step(dt, 1.4, 0);
    distance += dx;
    assert.ok(motion.x - old <= 2.8 * dt + 1e-9);
    assert.ok(motion.x <= 1.4);
  }
  assert.equal(motion.x, 1.4);
  const before = distance;
  for (let i = 0; i < Math.round(1 / dt); i++) {
    const [dx] = motion.step(dt, 0, 0);
    distance += dx;
  }
  assert.equal(motion.x, 0);
  assert.ok(distance - before < 0.21);
  return distance;
}
assert.ok(Math.abs(trajectory(1 / 60) - trajectory(1 / 30)) < 0.025);
const motion = new WalkMotion();
for (let i = 0; i < 120; i++)
  motion.step(1 / 60, Math.SQRT1_2 * 1.4, Math.SQRT1_2 * 1.4);
assert.ok(Math.hypot(motion.x, motion.z) <= 1.400001);
motion.reset();
assert.equal(motion.x, 0);
assert.equal(motion.z, 0);
console.log(
  "PASS: bounded acceleration, braking, diagonal speed and 30/60 fps consistency",
);
