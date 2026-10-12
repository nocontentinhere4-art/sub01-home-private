// Small physical acceleration/braking for the visitor, in metres and seconds.
export class WalkMotion {
  x = 0;
  z = 0;
  reset() {
    this.x = this.z = 0;
  }
  step(dt, targetX, targetZ) {
    const dx = targetX - this.x,
      dz = targetZ - this.z;
    const distance = Math.hypot(dx, dz);
    const acceleration = Math.hypot(targetX, targetZ) > 0 ? 2.8 : 5;
    const amount = Math.min(1, (acceleration * dt) / Math.max(distance, 1e-9));
    this.x += dx * amount;
    this.z += dz * amount;
    if (Math.hypot(this.x, this.z) < 0.001) this.reset();
    return [this.x * dt, this.z * dt];
  }
}
