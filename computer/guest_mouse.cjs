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

// Read only pinned-v86 protocol flags, never guest memory or host metadata.
function mouseDiagnostics(vm) {
  const d = vm.v86?.cpu?.devices, p = d?.ps2, w = d?.vmware;
  const bool = value => typeof value === 'boolean' ? value : null;
  const byte = value => Number.isInteger(value) && value >= 0 && value <= 255 ? value : null;
  return {
    absolute_pointer_enabled: bool(vm.absolute_pointer_enabled),
    ps2_use_mouse: bool(p?.use_mouse),
    ps2_stream_enabled: bool(p?.enable_mouse_stream),
    ps2_stream_active: bool(p?.mouse_stream_active?.()),
    ps2_mouse_id: byte(p?.mouse_id),
    ps2_command_register: byte(p?.command_register),
    vmware_enabled: bool(w?.enabled),
    vmware_absolute: bool(w?.absolute),
    vmware_host_pointer_locked: bool(w?.host_pointer_locked),
  };
}
module.exports.mouseDiagnostics = mouseDiagnostics;
