// Keyboard and pointer holds share one direction without relying on key-repeat.
export class HeldControls {
  constructor() {
    this.holds = new Map();
    this.version = 0;
    this.acknowledged = 0;
    this.pulses = new Map();
    this.pulseSequence = 0;
  }
  set(id, direction) {
    if (this.holds.get(id) === direction) return;
    this.holds.set(id, direction);
    this.version++;
  }
  release(id) {
    this.pulses.delete(id);
    if (this.holds.delete(id)) this.version++;
  }
  pulse(id, direction, schedule = callback => setTimeout(callback, 250)) {
    const token = ++this.pulseSequence;
    this.pulses.set(id, token);
    this.set(id, direction);
    schedule(() => {
      if (this.pulses.get(id) === token) this.release(id);
    });
  }
  clear() {
    this.pulses.clear();
    if (!this.holds.size) return;
    this.holds.clear();
    this.version++;
  }
  get active() { return this.holds.size > 0; }
  get changed() { return this.version !== this.acknowledged; }
  get direction() {
    return Math.sign([...this.holds.values()].reduce((sum, value) => sum + value, 0));
  }
  acknowledge(version) {
    if (version === this.version) this.acknowledged = version;
  }
}
