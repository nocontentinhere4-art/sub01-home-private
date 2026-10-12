// Keyboard and pointer holds share one direction without relying on key-repeat.
export class HeldControls {
  constructor() {
    this.holds = new Map();
    this.version = 0;
    this.acknowledged = 0;
  }
  set(id, direction) {
    if (this.holds.get(id) === direction) return;
    this.holds.set(id, direction);
    this.version++;
  }
  release(id) {
    if (this.holds.delete(id)) this.version++;
  }
  clear() {
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
