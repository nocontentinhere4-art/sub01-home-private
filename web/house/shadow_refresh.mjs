// Refresh cached door shadows at most 8 Hz in motion, plus the final settled pose.
export class ShadowRefresh {
  interval = .125;
  elapsed = 0;
  wasMoving = false;
  count = 0;
  step(dt,moving) {
    this.elapsed = Math.min(this.interval,this.elapsed+dt);
    const refresh = (moving && this.elapsed >= this.interval) || (!moving && this.wasMoving);
    this.wasMoving = moving;
    if (refresh) { this.elapsed=0; this.count++; }
    return refresh;
  }
}
