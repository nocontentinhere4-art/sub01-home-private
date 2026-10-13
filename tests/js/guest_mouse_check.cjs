const assert = require('node:assert/strict');
const { guestMouse } = require('../../computer/guest_mouse.cjs');
// The receiver models the pinned PS/2 device's documented packet layout,
// independently of framebuffer/VMware state. Decode it as the guest would.
for (const absolute of [false, true]) {
  const packets = [], events = [];
  const vm = { absolute_pointer_enabled: absolute, run() {}, bus: {send(kind, value) {
    events.push([kind, value]);
    if (kind === 'mouse-delta') {
      const [dx, dy] = value;
      packets.push([(dy < 0 ? 32 : 0) | (dx < 0 ? 16 : 0) | 8, dx & 255, dy & 255]);
    }
    if (kind === 'mouse-click') packets.push([8 | value[0] | value[2] << 1 | value[1] << 2, 0, 0]);
  }}};
  const mouse = guestMouse(vm, () => ({available: true, width: 1024, height: 768}));
  mouse({dx: 20, dy: 10, wheel: 0, buttons: [true, false, false]});
  assert.deepEqual(packets, [[0x28, 0x14, 0xf6], [9, 0, 0]], 'PS/2 movement and left click survive either advertised pointer mode');
  const abs = events.find(([kind]) => kind === 'mouse-absolute');
  assert.deepEqual(abs?.[1], absolute ? [532, 394, 1024, 768] : undefined);
  mouse({dx: -20, dy: -10, wheel: 1, buttons: [false, true, true]});
  assert.deepEqual(packets.slice(2), [[0x18, 0xec, 10], [14, 0, 0]]);
  assert.deepEqual(events.at(-1), ['mouse-wheel', [1, 0]]);
}
// Missing graphical pixels must not disable the kernel mouse or button release.
const events = [];
guestMouse({absolute_pointer_enabled:true, run(){}, bus:{send:(...e)=>events.push(e)}}, () => null)
  ({dx: 1, dy: 0, wheel: 0, buttons:[false,false,false]});
assert.deepEqual(events, [['mouse-pointer-lock',false], ['mouse-delta',[1,-0]], ['mouse-click',[0,0,0]]]);
console.log('guest mouse bus contract checks passed (CPU only)');
