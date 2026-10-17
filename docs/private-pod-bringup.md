# Private pod bring-up from the volume

A replacement pod gets a fresh container disk: only `/workspace` (volume `dvrlt6yk2k`) survives.
Everything under `/home/unreal` and every apt package must be rebuilt. This is the order that
brought the r22 home back on `jofornuokzg0ll` (RTX 4090, 2026-10-17). Guards come first; nothing
heavy starts without them.

## 0. Guards (before anything else)

- The pod start command writes `/root/.sub01-home-private/control.json` and starts the root guard
  with an absolute `END`. **Update `END` in the start command before resuming**: a stale `END`
  stops the pod immediately after boot.
- Start two more on-pod exact-identity guards (deadline and balance reserve) and record their PIDs as
  `external_guard_pid` / `second_external_guard_pid` in `/run/sub01-home-private/runtime-window.json`
  with `stop_guards_authenticated: true`; every launcher checks that file.

## 1. System and user

```
useradd -m -u 1001 -s /bin/bash unreal
apt-get install -y /workspace/sub01-home-private/device-runtime/public-debs/*.deb   # OpenJDK 17
apt-get install -y xvfb xauth x11-utils x11-xserver-utils xdotool python3-venv libvulkan1 vulkan-tools xserver-xorg-core
```

`/home/unreal/.sub01-private` (0700, uid 1001): `operator-token` (0600), `native-xauthority`, `xdg-runtime/`.

## 2. Display

Try NVIDIA Xorg on `:99` first (`tools/unreal_native_display.py` config with the pod's bus id).
If its log says `Failed to acquire modesetting permission` (the host does not give the container DRM
master; `/dev/dri/card*` owned by `nobody`), NVIDIA Vulkan cannot present to any window, Xvfb
included: the Game shows "Cannot find a compatible Vulkan device that supports surface presentation".
Then run the Game with `-RenderOffScreen` instead of `-windowed -NoBorder -WinX=0 -WinY=0`. Frames come
from the Game's own viewport capture; the X11 viewer and XTest input are unavailable on such a host.

## 3. Backend

- Base: `device-runtime/source/device-source-current.tar.gz`, then the overlays in time order, then
  the repo HEAD runtime files (top-level modules, `computer/`, `games/`, `scripts/`, the bridge).
  The base archive alone lacks `home_geometry_profile.py`, and without it the Game never binds.
- `.venv` from `requirements-server.txt`.
- `games/minecraft/node_modules` → symlink to `/workspace/sub01-home-private/minecraft-prepared/source/games/minecraft/node_modules`.
- `games/minecraft/bin/java` → symlink to the installed OpenJDK 17 (`downloads.json` points there).
- Launcher: `launchers/device-runtime-launch-<date>.py {pc,backend,bridge}` (from
  `minecraft-policy-refresh-*/device-runtime-launch-current.before.py`, POD changed). The **bridge also
  needs `HOME_NATIVE_BATHROOM_CORRIDOR_PROFILE=5ffac2406e66`**: the Game ignores every live command
  without `native_geometry_profile`, and with `HOME_NATIVE_REQUIRED=1` the brain then waits forever
  for an arrival that never comes.

## 4. Game

- `ln -s /workspace/sub01-private-derived-cache/ZenData /home/unreal/.config/Epic/UnrealEngine/Common/Zen/Data`
  before the first launch, or the Game boots a cold, empty Zen store.
- Launch the reviewed playable revision with the `launch_private_normal_game.py` arguments. Leave out
  `-Sub01StreamerVisual` for the walking home: that mode returns before the native control is read.
- `{"revision":N,"mode":"live"}` in `native-control.json` binds the pawn to the brain.
- `tools/native_home_settings_relay.py --deadline-epoch <END>` keeps the Tokyo hour and room lamps in
  sync; operator captures go through `capture-request.txt`.

## Checks

`/api/home` → `native_consumer.bound: true, physical_ready: true`; the Game log shows
`SUB01_LIVE_HOME_REACHED node=... floor=1` along the route and `SUB01_SEAT_TRANSITION_READY roles=23`.
