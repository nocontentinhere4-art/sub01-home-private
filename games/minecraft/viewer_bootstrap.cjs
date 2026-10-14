// One genuine idle view, bounded independently from autonomous play authority.
function viewerBootstrap({ isActive, connect, release, setTimer = setTimeout, clearTimer = clearTimeout, limitMs = 20000 }) {
  let requested = false, pending = false, timer = null;
  function finish() {
    if (!pending) return;
    pending = false;
    if (timer !== null) clearTimer(timer);
    timer = null;
    if (!isActive()) release();
  }
  return {
    allowed: () => pending,
    request() {
      if (requested || isActive()) return false;
      requested = true; pending = true;
      timer = setTimer(finish, limitMs);
      connect();
      return true;
    },
    finish
  };
}
module.exports = { viewerBootstrap };
