// Turn toward a direction, not a moving point that can pass behind the camera.
// Eye orientation stays level during walking; there is no artificial head sway.
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
export const shortestAngle = angle => Math.atan2(Math.sin(angle), Math.cos(angle));
export class FirstPersonLook {
  constructor(yaw = 0, pitch = 0) { this.reset(yaw, pitch); }
  reset(yaw, pitch) { this.yaw = yaw; this.pitch = pitch; }
  step(dt, position, target) {
    const dx = target[0] - position[0], dy = target[1] - position[1], dz = target[2] - position[2];
    const horizontal = Math.hypot(dx, dz);
    if (horizontal < .001 && Math.abs(dy) < .001) return [this.yaw, this.pitch];
    const targetYaw = horizontal > .001 ? Math.atan2(-dx, -dz) : this.yaw;
    const targetPitch = clamp(Math.atan2(dy, horizontal), -1.25, 1.25);
    const blend = 1 - Math.exp(-4 * dt);
    this.yaw += clamp(shortestAngle(targetYaw - this.yaw) * blend, -1.8 * dt, 1.8 * dt);
    this.pitch += clamp((targetPitch - this.pitch) * blend, -1.2 * dt, 1.2 * dt);
    this.yaw = shortestAngle(this.yaw);
    return [this.yaw, this.pitch];
  }
}
