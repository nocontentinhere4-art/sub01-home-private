// One genuine cold idle view; release early on a real frame, never grant play.
function viewerBootstrap({ isActive, connect, release, setTimer = setTimeout, clearTimer = clearTimeout, limitMs = 90000 }) {
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
