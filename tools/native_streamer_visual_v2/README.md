# `-Sub01StreamerVisual` v2: curated desk animation driven by the streamer agent

`install.py` patches the pod module sources in place (string anchors, each exactly once, all-or-nothing, atomic
writes, refuses a second install via the marker `// SUB01_STREAMER_VISUAL_V2`, keeps each file's CRLF/LF convention).
It edits `Sub01HomeLab.cpp/.h` and `Sub01HomeHands.cpp/.h` and only reads `Sub01PCBridge.h` (needs `HasOperatorFocus()`).
Nothing else changes: same R9 gate and authored body placement, same spectator camera, same ghost views, no new AnimGraph.

## What changes
- **Events**: v1 (`sub01.private-streamer-visual-event.v1`, source `human_vagon_observation`) behaves exactly as before
  (frozen R9_Sitting at 0.7 s, gaze, nod on each new event). v2 is accepted next to it with the same envelope checks.
- **Clips** play through the AnimInstance's existing Previous/Current players and its 0.24 s crossfade. A fresh loop
  starts at the phase (24 samples, measured once per clip on the clip itself) whose component-space hands are closest to
  the last evaluated hands. State changes are debounced to one per 0.6 s (latest request wins); `reacting` applies at once.
- **Liveliness** (additive in the proxy evaluation, like the head offset; deterministic in time, bounded): breathing
  0.6 deg at 0.22 Hz on `Spine1`, `Spine2` lagging 1.1 rad (bones found like `Head`: exact name, else name ending with it);
  head sway = smooth value noise <= 1.5 deg added to the gaze; `talking` adds <= 0.9/0.6 deg pitch/yaw cadence; entering
  `reacting` plays the v1 nod shape once (6 deg x nod_strength, 0.5 if 0). `intensity` scales sway and nod (x0.5..1).
  No blink, lip sync or expression: the mesh has no face rig.
- **Camera** (optional v2 `camera`): `spectator` = the authored v1 view, untouched. `monitor` = 1 s eased blend to
  pivot (214,-289,116) - 70 facing + 45 right + 45 up, aimed at the monitor bounds centre (217,-367.67,114.75). The
  facing is the body-transform axis (+-X/+-Y) that points at the monitor: +Y for this import (`HandsMeshRotation` yaw -90),
  giving about (275.2,-232.6,161), 17 deg down, 154 cm from the screen. A stale event (> 2 s) returns to idle + spectator.
- **Receipt** `sub01.native-streamer-visual-receipt.v1` keeps every field; adds `schema_version`, `state`,
  `requested_state`, `base_clip` (R9), `clip_fallback_frozen`, `clip_time`, `matched_start_seconds`, `intensity`,
  `breathing`, `camera`, `camera_blend`, `monitor_camera_facing_axis`; `clip` now names the active clip (R9 in v1).
- **PC monitor**: `USub01PCBridge` does not tick; a world timer (`Poll`, 0.5 s) fetches `/pc/state` + `/pc/frame.png`,
  so the texture refreshes in this mode without `SetOperatorFocus`. The branch already calls `UpdateNativePCPrivacy()`
  every tick. v2 only stops the per-tick `SetOperatorFocus(false)` when nothing is focused: it POSTed `/pc/session`
  and redrew the canvas every frame, competing with the frame fetches on the 8832 runner.

## Event schema v2 (`/home/unreal/.sub01-private/streamer-visual-event.json`)
```json
{"schema":"sub01.private-streamer-visual-event.v2","source":"streamer_agent","native_pid":N,"native_start_ticks":N,
 "captured_utc":T,"expires_utc":T+1.5,"sequence":S,"state":"typing","gaze_yaw_deg":0,"gaze_pitch_deg":-4,
 "nod_strength":0,"intensity":0.6,"camera":"monitor"}
```
- Owned by the game's uid (1001), mode 0600, regular file <= 4096 bytes, written by tmp + rename.
- `native_pid` / `native_start_ticks`: copy them from `streamer-visual-receipt.json` of the running game.
- `sequence`: integer, strictly increasing for the whole life of the game process (use e.g. epoch milliseconds).
- Fresh: `now - captured_utc` in [-0.1, 2], `expires_utc >= now`, `0 < expires_utc - captured_utc <= 2` exactly.
  Derive both from one clock read and use `+1.5`: a second `time.time()` or separate rounding makes `+2` exceed 2 (refused).
- Required: `state` in idle/reading/typing/mouse/talking/reacting, gaze yaw +-20, pitch +-10, nod 0..1. Optional:
  `intensity` 0..1 (default 0.5), `camera` spectator/monitor (default spectator), `source_frame_id` (<= 128 chars).

| state | clip (`/Game/Sub01Hands/Cinematic20261022/...`) | playback | extra |
|---|---|---|---|
| idle, reading | `Desk7_f696.../SupportedWebsite` | loop, rate 1, hand-matched phase | breathing + sway |
| typing | `Desk7_1da8.../SupportedDeskTyping` | loop, rate 1, hand-matched phase | breathing + sway |
| mouse | `Reach_c8ac.../AuthoredReach` | one play from 0, held on last frame | breathing + sway |
| talking | sitting loop | as idle | + speech cadence on the head |
| reacting | sitting loop | as idle | + one nod on entry (no debounce) |

All clips load with `LoadObject` at start and must use the body mesh's skeleton; otherwise the log says
`SUB01_STREAMER_VISUAL_CLIP_MISSING <path>` once and those states use the v1 frozen R9_Sitting (still crossfaded).

## Install and build on the pod
```bash
M=<project>/Source/Sub01HomeLab                 # holds Sub01HomeLab.*, Sub01HomeHands.*, Sub01PCBridge.h
cp -a "$M" "$M.before-streamer-v2"               # the installer keeps no backup; the report has before/after sha256
python3 tools/native_streamer_visual_v2/install.py --source "$M" --dry-run   # exit 0 = every anchor once
python3 tools/native_streamer_visual_v2/install.py --source "$M"
/workspace/sub01-private-recovered-engine/Engine/Build/BatchFiles/Linux/Build.sh Sub01HomeLabEditor Linux Development \
  -Project=<project>/Sub01HomeLab.uproject      # previous builds: ~27 min with 2 workers
```
Launch the game as before with `-Sub01StreamerVisual` (not `-Sub01AuthoredCinematicReview`, whose branch runs first),
env `SUB01_PC_ORIGIN=http://127.0.0.1:8832` and `SUB01_ADMIN_TOKEN` (without the token the monitor is never bound).
Log markers: `SUB01_STREAMER_VISUAL_V2_READY clips=N/3 facingAxis=+Y ...`, `SUB01_STREAMER_VISUAL_STATE a -> b`,
`SUB01_STREAMER_VISUAL_SCHEMA vN`. The 8832 runner must answer `POST /pc/privacy` with 200 or the screen stays hidden.

## Not verified without the engine
Real UE 5.8 compile (tests compile against a stub only), that the three clips share R9's root placement for the authored
body transform, that a local-pitch `FRotator` on Spine1/Spine2 bends the chest like the head-offset pitch nods the head,
and the visual result. Tests: `tests/test_native_streamer_visual_v2.py`.
