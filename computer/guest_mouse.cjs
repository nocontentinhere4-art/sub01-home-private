// Match the pinned v86 browser adapter's bus contract. PS/2 always consumes
// relative movement; an unlocked VMware pointer additionally consumes absolute
// coordinates. Advertising absolute mode must not suppress PS/2 delivery.
function guestMouse(vm, capture) {
  let x = null, y = null;
  return function input(m) {
    vm.run();
    const absolute = !!vm.absolute_pointer_enabled;
    vm.bus.send('mouse-pointer-lock', !absolute);
    vm.bus.send('mouse-delta', [m.dx, -m.dy]);
    if (absolute) {
      const frame = capture();
      if (frame?.available) {
        x = Math.max(0, Math.min(frame.width - 1, (x ?? frame.width / 2) + m.dx));
        y = Math.max(0, Math.min(frame.height - 1, (y ?? frame.height / 2) + m.dy));
        vm.bus.send('mouse-absolute', [x, y, frame.width, frame.height]);
      }
    }
    vm.bus.send('mouse-click', m.buttons.map(Number));
    if (m.wheel) vm.bus.send('mouse-wheel', [m.wheel, 0]);
  };
}
module.exports = { guestMouse };
