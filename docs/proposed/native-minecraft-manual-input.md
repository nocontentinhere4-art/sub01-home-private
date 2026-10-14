# Private manual TV input (runtime qualification pending)

`HOME_NATIVE_MANUAL_TV_INPUT` defaults OFF. Autonomous Minecraft still requires
HomeWorld's genuine physical sofa readiness. This manual path does not produce
seating evidence or reposition any actor/player.

The generator owner installs `tools/unreal_minecraft_tv_input.install(header,cpp)`
after the device/manual/live adapters. It adds a separate Slate processor;
phone/Notes composition remains with the existing device processor. The narrow
DeviceBridge getter returns only the identity of the actual painted Minecraft
texture, with a fresh public backend state.

An actual native E ray hit on the uniquely tagged authored TV starts a focus
event. While the real Manual capsule remains public, its camera still ray-hits
that component within 200cm and the same native process retains focus, an atomic
0600 file `/home/unreal/.sub01-private/native-tv-focus.json` publishes kernel PID
and startticks, actual actor/eye/hit/bounds, painted frame and event identity.
Backend validates this independently of the HTTP body. No payload-supplied mode
or coordinates are accepted. Evidence expires after 750ms. Escape clears the
receipt and sends release. Mouse-up sends cancel (digging only, not focus exit).

Authenticated actual-loopback routes:

- POST `/api/home/minecraft/focus`: `{consumer_id,focus_event_id,frame_id}`.
- POST `/api/home/minecraft/input`: same fields plus monotonically increasing
  `input_id`, `operation` (`controls`, `mine`, `place`, `cancel`, `release`).
  Controls optionally include boolean `keys` (forward/back/left/right/jump/sneak/
  sprint) and `look_delta` (yaw/pitch radians, each bounded to 0.35).

Native input renews focus from its current painted frame; controls follow a
successful focus response. Worker keys expire after 250ms without renewals.
Mining and placement raycast the actual Mineflayer view within 4.5 blocks and
use its real inventory/world; no forced position. Operations return correlated
worker receipts, not a pipe-write acknowledgement. Release remains possible
with a stale frame or privacy active. Place calls already sent to the real
server cannot be rolled back; new calls are forbidden after expiry.

Source fixtures and bounded worker method tests pass. Native compilation,
protected E-hit publication, actual player/world change, and resulting native TV
pixels are not yet accepted. Enable only in a coordinated qualification window
after the independent actual E receipt is verified; retain enabled operation only
if genuine game input and fresh output pass. No extra VM/Java server is required.
