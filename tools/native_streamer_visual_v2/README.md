# `-Sub01StreamerVisual` v2: curated desk animation driven by the streamer agent

The installers patch the pod module sources in place: string anchors each found exactly once, all or nothing, atomic
writes, CRLF/LF kept, JSON report with before/after sha256, refusal of a second run by marker.
`install.py` (`// SUB01_STREAMER_VISUAL_V2`) builds v2; `install_face_camera.py` (`// SUB01_STREAMER_VISUAL_V2_FACE`)
goes on top of it (`face` camera, desk guard); `install_pin_fix.py` (`..._PINFIX`) on top of that, `install_no_pin.py`
(`..._NOPIN`) next, `install_seat_fix.py` (`..._SEATFIX`, the one that actually seats him: below), then
`install_stream_pass.py` (`..._STREAMPASS`), `install_cam2.py` (`..._CAM2`), `install_mouth.py` (anywhere on v2),
`install_pose_fix.py` (`..._POSEFIX`, needs the stream pass and the mouth layer), `install_v21_fixes.py` (`..._V21`, on the
full v20 stack: build v21, game m) and `install_v22.py` (`..._V22`, on v21: the in-game monitor feed, persistent bridge
textures, cam2 exposure; it also edits the PC and device bridges and creates `Sub01PersistentTexture.h`).
`install_v23.py` (`..._V23`, on v22: the live-tunable look corrections, below).
Same R9 gate, spectator camera and ghost views as v1; no new AnimGraph.

## What v2 does
- **Events**: v1 (`...event.v1`, source `human_vagon_observation`) is unchanged (frozen R9_Sitting at 0.7 s, gaze, nod
  on each new event). v2 (below) is accepted next to it with the same uid/mode/pid/start-ticks/expiry/sequence checks.
- **Clips** play through the AnimInstance's Previous/Current players and 0.24 s crossfade. A fresh loop starts at the
  phase (24 samples) whose hands are closest to the last evaluated hands. At most one state change per 0.6 s (latest
  wins); `reacting` applies at once. Missing clip or other skeleton: `SUB01_STREAMER_VISUAL_CLIP_MISSING <path>`, frozen R9.
- **Liveliness** (deterministic, bounded): breathing 0.6 deg at 0.22 Hz on Spine1/Spine2; sway <= 1.5 deg on the gaze;
  `talking` adds <= 0.9/0.6 deg; entering `reacting` nods once. `intensity` scales sway and nod. No face rig: no lip sync.
- **Drift guard** (chair empty in `mouse`/`idle`). The instance keeps RootMotionFromMontagesOnly: these players never
  extract root motion, so a clip's root track lands in the pose. With the pin fix each clip keeps its OWN placement: bones
  above the pelvis take the clip's locals at 0 s (frozen R9: 0.7 s) and the pelvis stays within 8 cm / 25 deg of the
  clip's own reference (references blend in a crossfade). The pelvis-vs-R9 audit (Desk7 loops: 116 cm, yet seated
  correctly) is a log line only. `mouse` plays the sitting loop: AuthoredReach is excluded.
- **PC monitor**: refreshed by the bridge's own 0.5 s timer, no focus needed; the per-tick unfocused
  `SetOperatorFocus(false)` (a `/pc/session` POST per frame) now runs only when something is focused.
- **Receipt** keeps every v1 field; adds `schema_version`, `state`, `requested_state`, `base_clip`, `clip_time`,
  `intensity`, `breathing`, `camera`, `camera_blend`, `camera_fov`, `face_camera_blend`, `face_camera_aim_source`,
  `desk_offset_before_pin_cm` (pelvis drift from the clip's own reference), `clip_audit_done`; `clip` names the clip actually playing.

| state | clip (`/Game/Sub01Hands/Cinematic20261022/...`) | playback |
|---|---|---|
| idle, reading, talking, reacting, mouse | `Desk7_f696.../SupportedWebsite` | loop, hand-matched phase |
| typing | `Desk7_1da8.../SupportedDeskTyping` | loop, hand-matched phase |

`talking` adds the speech cadence, `reacting` the nod. (`Reach_c8ac.../AuthoredReach` is loaded and audited, never played.)

| `camera` | framing | FOV |
|---|---|---|
| `spectator` (default, and when the event is > 2 s old) | authored v1 view (334,-209,151) -> (214,-289,116), untouched while held | 65 |
| `monitor` | pivot -70 facing +45 right +45 up = (275.2,-232.6,161), aimed at the monitor centre (217,-367.67,114.75) | 65 |
| `face` (seat fix) | webcam at eye level in front of the screen: bounds centre +6 up, 2 towards him, 12 to his left = (204.9,-368.8,120.75), aimed at the mean Head bone of 1 s (else body +120) | 65 |

Every switch blends over 1 s. The facing is the body axis that points at the monitor: +Y for this import.

## Event v2 (`/home/unreal/.sub01-private/streamer-visual-event.json`, uid 1001, mode 0600, tmp + rename)
```json
{"schema":"sub01.private-streamer-visual-event.v2","source":"streamer_agent","native_pid":N,"native_start_ticks":N,
 "captured_utc":T,"expires_utc":T+1.5,"sequence":S,"state":"reading","gaze_yaw_deg":0,"gaze_pitch_deg":-4,
 "nod_strength":0,"intensity":0.5,"camera":"face"}
```
`native_pid`/`native_start_ticks` come from `streamer-visual-receipt.json`. `sequence` is an integer that keeps
increasing for the whole game process (epoch ms). Freshness: `now - captured_utc` in [-0.1, 2], `expires_utc >= now`,
`0 < expires - captured <= 2` exactly: one clock read, +1.5. Required: `state`, gaze (+-20/+-10), `nod_strength` 0..1.
Optional: `intensity` 0..1 (0.5), `camera` (`spectator`), `source_frame_id` (<= 128 chars). Stale events: idle, spectator.

Manual check on the pod (stop the agent first; Ctrl-C ends it; the camera returns to spectator 2 s later). The game accepts
only a growing `sequence` per game process and the agent counts from 0 per agent process: never hand-write a
time-based sequence (`CC_SEQ=<epoch ms>`) into a game the agent will drive afterwards, it blocks the agent until the
game is relaunched (`camera-check.py` continues from the receipt's `event_sequence` by default, which is safe):
```bash
sudo -u unreal python3 - face <<'EOF'   # or: monitor / spectator
import json, os, sys, time
P = '/home/unreal/.sub01-private/'; r = json.load(open(P + 'streamer-visual-receipt.json'))
while True:
    t = time.time(); e = {"schema": "sub01.private-streamer-visual-event.v2", "source": "streamer_agent", "native_pid": int(r["native_pid"]),
        "native_start_ticks": int(r["native_start_ticks"]), "captured_utc": t, "expires_utc": t + 1.5, "sequence": int(t * 1000),
        "state": "reading", "gaze_yaw_deg": 0, "gaze_pitch_deg": -4, "nod_strength": 0, "intensity": 0.5, "camera": sys.argv[1]}
    fd = os.open(P + 'streamer-visual-event.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600); os.fchmod(fd, 0o600)
    os.write(fd, json.dumps(e).encode()); os.close(fd); os.replace(P + 'streamer-visual-event.tmp', P + 'streamer-visual-event.json'); time.sleep(.5)
EOF
```

## Install and build on the pod
```bash
M=<project>/Source/Sub01HomeLab ; cp -a "$M" "$M.before-face"     # installers keep no backup
python3 tools/native_streamer_visual_v2/install.py --source "$M" --dry-run            # only on pre-v2 sources
python3 tools/native_streamer_visual_v2/install_face_camera.py --source "$M" --dry-run  # only on v2 sources
python3 tools/native_streamer_visual_v2/install_pin_fix.py --source "$M" --dry-run      # only on v2+face sources
python3 tools/native_streamer_visual_v2/install_no_pin.py --source "$M" --dry-run       # only on v2+face+pinfix sources
python3 tools/native_streamer_visual_v2/install_seat_fix.py --source "$M" --dry-run     # only on the full stack above; then without --dry-run
python3 tools/native_streamer_visual_v2/install_stream_pass.py --source "$M" --dry-run  # only on the seat-fixed stack
python3 tools/native_streamer_visual_v2/install_cam2.py --source "$M" --dry-run        # only on the stream-passed stack (v20)
python3 tools/native_streamer_visual_v2/install_mouth.py --source "$M" --dry-run        # on v2 alone or on any stack above
python3 tools/native_streamer_visual_v2/install_pose_fix.py --source "$M" --dry-run    # after the stream pass AND the mouth layer (v20)
python3 tools/native_streamer_visual_v2/install_v21_fixes.py --source "$M" --dry-run  # on the full v20 stack (v21); keep backups OUTSIDE Source/ (a copy with a Build.cs breaks UBT)
python3 tools/native_streamer_visual_v2/install_v22.py --source "$M" --dry-run        # on v21 (v22): also the bridges + the new Sub01PersistentTexture.h
python3 tools/native_streamer_visual_v2/install_v23.py --source "$M" --dry-run        # on v22 (v23): Sub01HomeLab.h/.cpp and Sub01HomeHands.h/.cpp only
/workspace/sub01-private-recovered-engine/Engine/Build/BatchFiles/Linux/Build.sh Sub01HomeLabEditor Linux Development \
  -Project=<project>/Sub01HomeLab.uproject      # previous builds: ~27 min with 2 workers
```
Launch with `-Sub01StreamerVisual` (not `-Sub01AuthoredCinematicReview`), `SUB01_PC_ORIGIN=http://127.0.0.1:8832`,
`SUB01_ADMIN_TOKEN`. Logs: `SUB01_STREAMER_VISUAL_V2_READY`, `..._FACE_READY`, `..._DRIFT_GUARD`, `..._DRIFT_REFERENCE`,
`..._CLIP_AUDIT`, `..._MOUSE_AS_SITTING_LOOP`, `..._STATE a -> b`, `..._FACE_CAMERA`. With `install_no_pin.py` (build v14)
the guard only measures (`DRIFT_GUARD ... applied=0`): both the R9 pin (v11) and the per-clip guard (v13) moved the body
out of the chair on the pod, while the clips alone sit on the authored transform. Offline checks only (stub
compile + logic runs): `tests/test_native_streamer_visual_v2.py`; the spine pitch axis and the visual result need the pod.

## Seat fix (`install_seat_fix.py`, `// SUB01_STREAMER_VISUAL_V2_SEATFIX`, builds v15/v16, games f/g 2026-10-23)
Why the chair was empty: the Desk7 loops are authored ~1.15 m behind R9's station in component space (loop pelvis at
0 s (-0.058,-92.651,73.049), R9's pelvis at 0.7 s (0.075,22.727,64.214); the (0.908,6.407,88.529) line in the
`DRIFT_REFERENCE` log is the pre-v2 base clip, not R9) and these players never extract root motion. On top of that
`ACharacter::bUseControllerRotationYaw` turned the root (and the attached mesh) to every `SetControlRotation` look: the
receipt's `body_world` yaw read -146.31 (the spectator look) instead of the authored 165.4, and each camera switch (v11,
v13) turned the body again. The fix never touches bones:
- per clip, once, the proxy computes the component-space `D` with `clipPelvis(reference) * D = R9Pelvis@0.7` (translation
  exact, rotation = the yaw twist of `R9 * clip^-1`, the clip's own pelvis tilt stays) and publishes it every evaluation,
  blended with the crossfade weight from the previous clip's `D` (the frozen R9 gives the identity);
- the character sets the mesh relative transform to `D * (authored relative)` when it changes by > 0.01 and restores
  the authored one when v2 ends; `bUseControllerRotationYaw=false` at v2 start; `BoundsScale=4` on the body (the pose is
  ~1.2 m from the offset component origin, the fixed ref-pose bounds were frustum-culled by the face camera: empty chair
  in its frames while the spectator camera showed him).
- Measured in game g: offset for both Desk7 loops 115.7 cm / 0.9 deg; `pelvis_world` (208,-311,70.4) = R9's pelvis on
  the authored transform (the chair); `head_world` ~(203,-333,118) in `reading` (he leans in, ~35 cm from the screen).
- Face camera: a fixed webcam at EYE LEVEL just in front of the screen, bounds centre (217,-367.67,114.75) + 6 up,
  2 towards him, 12 to his left (over his head: the monitor is wider than his seat) = (204.9,-368.8,120.75), aimed at
  the mean Head bone of 1 s (the loops sway the head ~5 cm) once per selection after the seat offset has settled (else
  2 s), FOV 65, pitch ~-5. With the 25 cm pull-back and the posture layer below: head-to-camera ~61 cm, a frontal face
  with the hall, stairs and window behind him (games i/j frames). From above the monitor (up >= 22) the reading loop's
  bowed head shows mostly hair; behind the screen plane (forward <= -8) the light bar cuts the lower frame; at eye level
  the camera cannot go further back than the screen glass, so FOV is the only width lever. Live tuning without a
  rebuild: `/home/unreal/.sub01-private/streamer-visual-face-tuning.json` (uid 1001, mode 0600,
  `{"schema":"sub01.private-streamer-visual-face-tuning.v1","sequence":N,"up_cm":6,"forward_cm":2,"side_cm":-12,
  "aim_drop_cm":0,"fov_deg":65,"seat_back_cm":25,"seat_side_cm":0,"desk_props":1,"posture_lean_deg":-10,
  "posture_head_deg":8}`, values clamped, applied when `sequence` grows; `/home/unreal/face-tune.py <up> <forward>
  <side> <drop> <fov> [back [seat_side]]` writes the camera/seat keys, `clear` removes it); the compiled defaults are the
  verified framing (pull-back and posture default to 0: the tuning file carries the recommended values).
- Pull-back knob (`seat_back_cm` 0..40, `seat_side_cm` -20..20, `desk_props` 0/1 in the same tuning file; compiled
  default 0, recommended 25): him and the keyboard move together away from the monitor along the body facing, composed
  with the clip offset on the mesh component (restored when v2 ends), logged as `SUB01_STREAMER_VISUAL_SEAT_BACK
  cm=...`. The keyboard on the pod level is the `R15Part*` pack split into ~107 small StaticMeshActors (body, keycaps,
  knob, feet) in the zone X 188..245 / Y -348..-320 / Z 66..96; those (half extents <= 25/12/8 cm) and any actor named
  mouse/keyboard with a static mesh follow (`SUB01_STREAMER_VISUAL_DESK_PROP_CANDIDATE ... follows=1`); the CHAIR
  follows too: every chair-sized static mesh (half extents <= 60/60/80) around the authored pelvis (X 170..260,
  Y -322..-250, Z -10..100; on the pod level the 14 `full-home_node_*` parts: seat/back/base 246..252 and the armrests
  184..187, 236..238; `SUB01_STREAMER_VISUAL_CHAIR_CANDIDATE ... follows=1`, `..._DESK_PROPS found=107 chairParts=14
  moved=121 delta=...`). The desk parts (`SUB01_RealLinea140_*`), the mat (R15Part0000/0016), the rug, the clock (X 253)
  and the macro pad (X 182) never move. The glowing mouse is not a static-mesh actor in that zone, so it stays on the
  mat ~25 cm ahead of his right hand. The tuning file is polled every 0.5 s whenever v2 runs (not only in `face`).
- "Sit up" posture layer (`posture_lean_deg`, `posture_head_deg`, -20..20 each, compiled default 0, recommended
  -10 / +8): the lean is split over Spine1/Spine2 as local pitch (the breathing axis), the head pitch is added to the
  gaze/nod offset (the mouth layer's head emphasis stays separate), both eased at 12 deg/s; logged once per change as
  `SUB01_STREAMER_VISUAL_POSTURE leanDeg=... headDeg=...`; receipt `posture_lean_deg` / `posture_head_deg` (applied).
- Receipt adds `seat_offset`, `seat_offset_cm`, `seat_offset_yaw_deg`, `seat_offset_applied`, `seat_offset_settled`,
  `pelvis_world`, `head_world`, `face_camera_location`, `face_camera_aim`, `face_camera_tuning_sequence`, `camera_world`,
  `body_bounds`, `seat_back_cm`, `seat_side_cm`, `desk_props_moved`, `desk_props_delta`, `chair_parts`,
  `posture_lean_deg`, `posture_head_deg`. Logs: `SUB01_STREAMER_VISUAL_SEAT_FIX_READY`, `..._SEAT_OFFSET` (per clip), `..._FACE_RIG` (66 Mixamo
  bones, only Neck/Head/HeadTop_End near the face, 0 morph targets: no jaw or visemes to drive), `..._FACE_CAMERA`.

## Stream pass (`install_stream_pass.py`, `// SUB01_STREAMER_VISUAL_V2_STREAMPASS`, build v20)
On top of the seat fix; everything live from the same tuning file. Defaults follow the reviewed hands recipe
(`docs/streamer/kimi/posture.md` section 3). The engine headers it needs are included at the TOP of `Sub01HomeLab.cpp`:
`StartStreamerVisualV2` (which creates the key light) precedes the appended methods, and the first v20 build failed on an
incomplete `USpotLightComponent` (log kept as `build-v20-failed-spotlight-include.log`).
- **Hands IK**: an own two-bone solve in the proxy (no AnimationCore node) on `LeftArm/LeftForeArm/LeftHand` and the
  right chain, in component space after breathing/posture and before the head offset: the upper arm turns by the minimal
  rotation onto the new elbow, the forearm is carried with it and then bent at the elbow (no forearm roll), bone lengths
  kept, the hand's local rotation untouched, slerp-blended by an alpha eased over 0.3 s. The bend plane is the clip's,
  pulled towards an elbow pole (down 1, back 0.5, out 0.3 in his frame) by `elbow_pole` (default 0.5). Targets are WRIST
  positions on the keyboard body (the widest follower of the keyboard pack, at its bounds centre): `hand_span_cm` 20
  apart (recipe 18-22), `hand_back_cm` 13 towards him from the keyboard's centre line, `hand_height_cm` 4.5 above the
  desk (the keyboard's bottom; recipe 4-5). In `mouse` the right wrist goes `mouse_back_cm` 7 behind the mouse prop if the
  level has one (any actor with a primitive in X 225..256 / Y -346..-318 / Z 70..96, half extents <= 12/12/8, not the
  keyboard/desk packs; `SUB01_STREAMER_VISUAL_MOUSE_CANDIDATE`/`..._MOUSE_PROP found=`; it then follows the pull-back)
  else to the tuning point `mouse_x/y/z` (default 237,-333,82; a merged mouse does NOT follow the pull-back); the left hand
  stays planted. A goal jump > 2 cm glides in `hand_move_s` 0.25 on a `hand_arc_cm` 4 arc (eased); smaller drift (props
  following) is tracked. Finger curl: `finger_curl_deg` (default 0 = the clip's) added to the proximal (x1) and middle
  (x1.2) phalanges of index..pinky about the local axis `finger_curl_axis` (0/1/2, default 2), scaled by the alpha; the
  measured flexion is logged first so the recipe's 20-35 / 25-40 deg can be checked before turning it on. Keys:
  `hands_ik` 0/1, `hand_height_cm`, `hand_span_cm`, `hand_back_cm`, `hand_move_s`, `hand_arc_cm`, `elbow_pole`,
  `finger_curl_deg`, `finger_curl_axis`, `mouse_back_cm`, `mouse_x/y/z`. Log `SUB01_STREAMER_VISUAL_HANDS target=left:...
  right:... reach=L/R alpha= elbow=L/R fingers=L mcp/pip R mcp/pip ...` (on target change and every 10 s); receipt
  `hand_left`/`hand_right` ("<target> <wrist-to-target cm>"), `hands_alpha`, `elbow_left_deg`/`elbow_right_deg` (interior,
  recipe 85-100), `finger_curl_deg_measured`, `mouse_prop`.
- **Desk-work base**: `desk_base` 1 (default) plays the typing loop in every state but `reading`; `chair_back_cm` -1
  (default) moves the chair with the seat pull-back, 0..40 by its own distance.
- **Typing posture**: `typing_lean_deg` / `typing_head_deg` (defaults -6 / +15) added to the seat fix's posture
  targets while the typing loop plays, same 12 deg/s easing.
- **Body look**: `forced_lod` (default 1 = LOD0 forced) and `hide_slot` (a material slot hidden at LOD0, -1 = none)
  applied on change; `SUB01_STREAMER_VISUAL_BODY_LOOK forcedLod= lods= materials=[i:name,...]` logs the body's slots once
  so the hoodie collar can be matched to a slot (then `hide_slot` tests it live); receipt `hide_slot`, `forced_lod`.
- **Key light**: a movable SpotLight (candelas, 4500 K, cones 25/45 deg, 300 cm, no shadows) created at v2 start, 25 cm
  above the monitor centre, 6 cm towards him and the face camera's side offset to his left, aimed at the face camera's
  head mean (else the Head bone sampled every 2 s); `key_light` 0..1 scales 2500 cd (0 hides it), `key_light_temp_k`,
  `key_light_up_cm`. Log `SUB01_STREAMER_VISUAL_KEY_LIGHT`; receipt `key_light`.
- **Perf**: `SUB01_STREAMER_VISUAL_PERF fps= ms= max_ms= gpu_ms= gpu_samples=` every 30 s (the wall clock between ticks;
  the RHI GPU frame time sampled once per tick, -1 when the RHI reports none); receipt `fps`, `frame_ms`, `frame_max_ms`, `gpu_ms`. Launcher `launch-streamer-game-20261023l.py` runs
  `t.MaxFPS 60` (owner: 60 fps everywhere).

## Cam 2 (`install_cam2.py`, `// SUB01_STREAMER_VISUAL_V2_CAM2`, build v20)
On top of the stream pass; only `Sub01HomeLab.h/.cpp` change. A second camera from behind him, at the same time as the
webcam (the main view), written as MJPEG to a FIFO for ffmpeg (`-f mjpeg -i /home/unreal/.sub01-private/streamer/cam2.mjpeg`).
- At v2 start: a `USceneCaptureComponent2D` (final colour LDR, persistent view state, the view camera's post-process
  settings, no motion blur, no depth of field, manual captures only) and a 1280x720 BGRA8 render target; the FIFO is created with `mkfifo`
  0600 when absent (an existing path that is not this uid's FIFO disables cam2 with a reason; it is never replaced).
- Game thread: when the timer is due (`cam2_fps`, default 60; half a frame of tolerance, at most one capture per tick)
  ONE render command (the readback) and `CaptureSceneDeferred()` (`cam2_deferred` 1, default: rendered with the frame's
  main view, no mid-tick render-state flush, so each readback reads the PREVIOUS capture) or `CaptureScene()` (0: its own
  capture); nothing waits on the GPU.
- Render thread: a ring of 3 `FRHIGPUTextureReadback`; the fence is polled (`IsReady`), the newest finished copy locked,
  its rows copied (row pitch honoured), unlocked and handed to one background JPEG encode at a time (`cam2_quality` 85);
  older finished copies, frames arriving while an encode runs and captures with no free slot are dropped and counted.
- Writer (background): `O_WRONLY|O_NONBLOCK` (no reader = ENXIO, frame dropped, reopen after 1 s), pipe buffer 1 MiB, a
  frame is written only when the pipe has room for all of it (FIONREAD; a frame larger than the pipe only on an empty
  pipe), a short write's rest is finished before any newer frame (a frame counts when its last byte is in), EINTR retried,
  SIGPIPE blocked for the write and never left pending (reader gone: fd closed, its unfinished frame dropped, reopened
  later): while a reader stays connected the stream is ordered whole JPEGs, never interleaved; a new reader starts on a
  frame boundary. Copies taken before a pause (`cam2` 0) are dropped, never shown after it (`dropped_stale`); an open
  error other than "no reader" is reported as `open_errno` in `cam2.json`.
- `cam2.json` next to the FIFO every second (`sub01.streamer-cam2-status.v1`: fps, capture_fps, target_fps, frames,
  captured, encoded, dropped_no_reader/full/busy/slots, reader, last_frame_utc, width, height, quality, fov, location,
  rotation, encode_ms, kb_per_frame). Logs: `SUB01_STREAMER_VISUAL_CAM2 started=1 fifo=... location=... reason=-` at
  start, `SUB01_STREAMER_VISUAL_CAM2 fps= capture_fps= target_fps= frames= reader= game_ms_per_capture=
  game_ms_per_frame= readback_ms= encode_ms= kb= dropped_...` every 30 s, `..._CAM2_PLACED` on a placement change. The
  GPU cost of the extra view is the difference in `SUB01_STREAMER_VISUAL_PERF gpu_ms` with `cam2` 1 vs 0.
- Tuning keys: `cam2` 0/1, `cam2_x/y/z` (default 334,-209,160: the spectator point raised to 1.6 m, behind him and to his
  right), `cam2_yaw/pitch` (default -132.5/-20.1: aimed at (214,-340,95), his back, the keyboard and the monitor),
  `cam2_fov` 70 (horizontal), `cam2_fps` 1..60, `cam2_quality` 40..95, `cam2_deferred` 0/1. Receipt: `cam2_on`, `cam2_fps`,
  `cam2_capture_fps`, `cam2_frames`, `cam2_reader`, `cam2_reason`.

## Pose fix (`install_pose_fix.py`, `// SUB01_STREAMER_VISUAL_V2_POSEFIX`, build v20)
On top of the stream pass AND the mouth layer (cam2 before or after); the visual QA of build v19
(`docs/streamer/VISUAL-QA-20261023.md`). Pod order for v20: stream pass, cam2, mouth, pose fix.
- **Offsets about HIS axes** (QA bug 3): on this Mixamo import `FRotator(Pitch)` post-multiplied into the local rotation of
  Spine1/Spine2/Head turned the bones about their long (twist) axis (the sit-up twisted the torso, the nod was a shake,
  gaze pitch turned the head). The proxy now reads his frame from the pose every evaluation (lateral = right thigh - left
  thigh, flattened; else -X; up = Z; forward = lateral x up) and turns each bone in component space about its own pivot:
  `local' = parent^-1 * Delta * parent * local`. Spine channel = the lean (posture_lean + typing_lean, FORWARD degrees,
  negative = sit up) spread Spine 0.5 / Spine1 0.3 / Spine2 0.2 with a gain adapted every frame so the measured
  Hips-to-Head inclination change equals the command (Kimi's acceptance: +10 -> 10 +- 1), then breathing on Spine1/Spine2.
  Head channel over Neck 0.4 / Head 0.6: pitch (gaze, nod, talking cadence, `posture_head_deg`, `typing_head_deg`, the
  mouth emphasis as 2 deg nose DOWN; nose UP positive) and yaw (gaze, sway, `head_yaw_deg`; to his RIGHT positive).
  **After this build: set `posture_head_deg` back to ~0 and move the QA's +14 (a yaw stop-gap) to `head_yaw_deg`.**
- **Loop seam** (QA bug 2): within `loop_fade_s` (default 0.5, at most 25% of the clip) of a desk loop's end, Previous
  keeps the end while Current restarts at 0 through the state-change crossfade, faded over that time; counted in
  `loop_seams`.
- **Face camera aims once** (QA bug 7): the Head bone is tracked every tick while v2 runs (any camera) as an exponential
  mean (tau 5 s); the first selection aims at once (>= 2 s of samples, else after 2 s), the aim is kept across camera
  switches and re-aimed only after a tuning change (from a fresh mean; on screen it eases from the old aim over 1 s). Log
  `..._FACE_CAMERA ... meanSeconds= ... kept until the tuning changes`.
- **Seat yaw** (QA bug 8): `seat_yaw_deg` (-30..30, default 0; positive turns him to his right) about the seated pelvis
  (R9's, published by the proxy) on the mesh component, between the clip offset and the pull-back; the chair parts turn with
  him about the same vertical. He faces ~17-24 deg left of the monitor: try +17.
- **Chair fit** (QA bug 4): `chair_fit` 1 (default): the chair parts >= 3 cm behind and reaching >= 15 cm above the pelvis,
  within 20 cm sideways (not the armrests), are the backrest; their real surface is traced at sacrum height (Hips + 6 cm,
  `LineTraceComponent` from in front of him backwards; the bounds' front is the fallback) along his facing and compared with
  the sacrum (pelvis bone - facing * `sacrum_back_cm` 11) and the whole chair moves along the facing until the backrest
  stands `backrest_gap_cm` (1; recipe 0-2) behind it: passes 1 s apart after the seat settles, at most 4 per tuning change,
  clamped to +-25 cm, the chair gliding there at 60 cm/s. Log `SUB01_STREAMER_VISUAL_CHAIR_FIT pass= method=trace|bounds
  backrest= parts= sacrum= backrestFront= gapCm= chairFitCm=`.
- Log `SUB01_STREAMER_VISUAL_POSE leanCmd= leanMeasured= gain= headPitch= headYaw= seatYaw= loopSeams= bodyRight=` every 10 s;
  receipt `lean_measured_deg`, `lean_gain`, `head_yaw_deg`, `seat_yaw_deg`, `loop_seams`, `backrest_gap_cm`, `chair_fit_cm`,
  `backrest`, `face_aim_mean_s`. Tuning keys: `head_yaw_deg`, `seat_yaw_deg`, `loop_fade_s`, `chair_fit`, `sacrum_back_cm`,
  `backrest_gap_cm`.

## Mouth layer (`install_mouth.py`, `// SUB01_STREAMER_VISUAL_V2_MOUTH`)
Goes on v2 alone or on v2 plus any of the layers above, in any order: its anchors are v2 lines no other installer edits.
The voice server publishes `<streamer-dir>/mouth.json` (`sub01.streamer-mouth.v1`, 25 Hz while speaking, `open` 0..1
from the RMS of the audio being played; docs/streamer/VOICE.md). The character polls
`/home/unreal/.sub01-private/streamer/mouth.json` at most 30 Hz (regular file of the game's uid, not group/other
writable, <= 512 bytes, `utc` within 0.5 s; anything else = closed, logged once as `SUB01_STREAMER_VISUAL_MOUTH_FILE_REJECTED`
when the file exists but is foreign) and bridges the samples to the frame rate (30/s). Name-table scan of
`AnatomicalOwner_Skeleton.uasset` / `AnatomicalOwner.uasset` (2026-10-23): 65 Mixamo bones (Hips, Spine, Spine1, Spine2,
Neck, Head, HeadTop_End, shoulders/arms/hands with four finger bones each, legs/feet/toes), no jaw, mouth or facial
bone, no morph target (only the engine's `MorphTargets` property names). So the proxy adds `2 deg * open` of Head pitch as
emphasis in the same local-pitch convention as the gaze and the nod (flip the constant in the installer if the head rises
on speech), composed with the gaze offset; a skeleton with a `Jaw` / `jaw` / `JawRoot` bone (or one ending in Jaw) gets
`12 deg * open` on that bone instead. This is not lip sync: real mouth movement needs a face rig (jaw bone or visemes)
on the body mesh. Receipt: `mouth_open`, `mouth_energy`, `mouth_file_fresh`, `mouth_id`, `mouth_rig` (`head_only` |
`jaw_bone` | `none`); `facial_animation_or_lipsync` stays false. Log: `SUB01_STREAMER_VISUAL_MOUTH_READY rig=...` once.

## v21 fixes (`install_v21_fixes.py`, `// SUB01_STREAMER_VISUAL_V2_V21`, build v21, game m2)
On the full v20 stack; only `Sub01HomeLab.h/.cpp` change. Decided with Kimi (`docs/streamer/kimi/native-v21-perf.md`), code
reviewed by Kimi (`docs/streamer/kimi/native-v21-review.md`; game m ran the pre-review build, game m2 the reviewed one).
- **Why 15 fps** (game l, measured): the container's cgroup allows 10.2 CPUs (`/sys/fs/cgroup/cpu.max` 1020000/100000) of 48
  visible; the whole container was throttled in 100% of the 100 ms periods and SMT siblings were shared. Pinning alone (no code):
  everything on cores 0-9 -> 23 fps; game + Xvfb :99 on 0-5, the rest on 6-9 -> 40-42 fps with cam2 on, 53 fps with cam2 off.
  Launcher `launch-streamer-game-20261023m.py` starts the game on cores 0-5 with `-corelimit=6`;
  `scripts/streamer_cpu_partition.py` (run as uid 1001: root has no CAP_SYS_NICE here) pins Xvfb :99 with it and the rest on 6-9.
- **PERF** adds `game_ms render_ms rhi_ms swap_ms render_wait_ms game_wait_ms` (the engine's per-frame cycle counters, swap = present)
  over `perf_window_s` (default 10); receipt `perf_*`.
- **Live console**: `/home/unreal/.sub01-private/streamer-visual-console.json` (uid 1001, 0600, <= 2048 bytes)
  `{"schema":"sub01.private-streamer-visual-console.v1","sequence":N,"commands":["r.Foo 1"]}` runs once per growing sequence;
  grammar: `<cvar>` (query: the log shows its value) or `<cvar> <number>` under `r. sg. fx. a. foliage. grass.` or the exact
  `t.MaxFPS`, or exactly `csvprofile start|stop|frames=<n>` (CSV in `Sub01HomeLab/Saved/Profiling/CSV`); <= 8 commands of <= 96
  chars; log `SUB01_STREAMER_VISUAL_CONSOLE ... handled= value=`; receipt `console_applied/refused/last`. Helper on the pod:
  `sudo -u unreal python3 /home/unreal/tmp/v21/console.py "r.Shadow.RadiusThreshold 0.05"`.
- **cam2** renders only for a reader (v20 captured and encoded every frame and dropped it at the writer): a 1 s non-blocking open
  probe on the game thread is the only opener and hands the fd to the writer; no reader = a pause (the director's tap keeps a
  reader, so with the director running cam2 always renders). cam2.json `idle_no_reader`, `lite`. `cam2_lite` 1: no
  AO/SSR/contact shadows/volumetric fog/lens flares/particles, `cam2_view_cm` cull distance, LOD factor 2. cam2 now shows him:
  a scene capture has no view owner, so his `bOnlyOwnerSee` primitives are made visible to every view at cam2 start
  (`SUB01_STREAMER_VISUAL_BODY_SEEN onlyOwnerSeeCleared=N`).
- **Key light**: the house's exposure is set for very dim light (game l: 1.25 cd already clipped his face). New keys, ignored by v20:
  `key_cd` (candelas, compiled default 0.15, 0 = off), `key_soft_cm` 20, `key_radius_cm` 160, `key_body_only` 1 (the light on
  lighting channel 1, his primitives on 0+1: its direct light never reaches the chair, desk or walls; Lumen's bounce is not
  masked); cones 30/55. The v20 `key_light` level is ignored. Measured on game m (face camera, talking, skin median in a 110 px
  box on the face): 0.04 cd -> 152, 0.06 -> 183, 0.08 -> 199, 0.15 -> 203, none clipped: the tuning file carries `key_cd` 0.04.
- **Chair fit**: every chair part logged once in his frame (`SUB01_STREAMER_VISUAL_CHAIR_PART`). On game m every chair part lay IN
  FRONT of his pelvis (the backrest `full-home_node_249`, 40 x 20 x 45 cm half-extents 20/10/22.5, 7 cm in front of it: the chair
  cut ~29 cm into him, QA bug 4), which is why v20 never found a backrest. The backrest is now the tall, central, near (in front
  or behind, <= 40 cm), THIN part; its surface is traced at sacrum height, else its bounds' front; the fit clamp is +-40 cm. The pose fix's rotation
  record in the desk-prop scan (inside a `//` comment since v20) is a statement again (the chair turns with `seat_yaw_deg`).
- Typing head: `typing_head_deg` 15 with `posture_head_deg` 0 keeps his eyes on the screen (game l frames); unchanged.

## v22 (`install_v22.py`, `// SUB01_STREAMER_VISUAL_V2_V22`): monitor feed, persistent textures, cam2 exposure
On v21; edits `Sub01HomeLab.h/.cpp`, `Sub01PCBridge.h/.cpp`, `Sub01HomeDeviceBridge.h/.cpp` and creates `Sub01PersistentTexture.h`
(refused if it exists with other content, or if `native_cinematic_pc.inc` binds `PCFrame` itself). Designed with Kimi
(`docs/streamer/kimi/native-v22-design.md`), code reviewed by Kimi (`docs/streamer/kimi/native-v22-review.md`).
- **In-game monitor feed**: the supervised `monitor` service (`scripts/streamer_monitor_feed.py`: x11grab of the Vagon desktop, 1280x720
  JPEGs back to back, its own privacy gate with neutral grey frames during a cut, which are ordinary frames here) writes
  `<streamer-dir>/monitor.mjpeg`. ONE background task at a time opens it `O_RDONLY|O_NONBLOCK|O_NOFOLLOW` (only this uid's FIFO
  with no group/other bits; never created or replaced by the game), reads what is there (<= 8 MiB per pump), cuts whole JPEGs by
  walking their markers (an EOI byte pair inside a segment never ends a frame; garbage, a cut frame, a reserved marker or a frame
  > 4 MiB = resync on the next SOI) and queues the newest frame of each read (ring: 64 frames / 16 MiB). It then plays out at most
  ONE frame per pump: the newest one read at least `monitor_delay_s` (0.75) ago AND before the start of the PC bridge's newest
  completed public confirmation of the connected desktop (a frame read after the runner locked cannot be shown while the lock
  lasts, even before the game notices); that one is decoded (ImageWrapper JPEG -> BGRA, size checked from the header first,
  <= 1280x1024). The game thread takes it (a pointer swap), uploads it into ONE persistent texture (B8G8R8A8 sRGB, never
  streamed, one mip, created once per size and cleared opaque black, cleared again when the source rect changes;
  `UpdateTextureRegions` of the 1280x720 rect at the PC bridge's own layout offset, the heap copy freed in the cleanup callback;
  skipped while 3 uploads are still pending on the RHI) and binds it through the PC bridge. Pumps run at `monitor_fps`
  (default 60, a cap; 30 is the pod fallback if the render thread suffers). Progress = a new upload < `monitor_stale_s` (2.0)
  ago; none (a dead feed), `monitor_feed` 0 or a closed gate = the bridge's own picture again and the texture blanked
  (`monitor_feed` 0 also closes the FIFO, so the sidecar stops ffmpeg).
- **Privacy gate** (fail closed, in the bridge AND the character, every tick): the bridge allows the feed only while it is public (no
  `Private`, `LocalPrivacy`, `PrivacyDesired`, not the read-only cinematic browser) and its last poll's confirming `/pc/state` read
  (started < 1.5 s ago) said `pc_mode` "vagon", `vagon.connected` AND `vagon.phase` "connected" (the sidecar's own rule: the host
  page's login/dashboard can come with `connected` still true) and an available `graphical` display: before the remote desktop is
  connected the runner itself shows only a neutral picture (the owner's login/account pages), which a raw x11grab would bypass. So
  with `SUB01_PC_ORIGIN=8832` (the old bundled Chromium runner, `pc_mode` chromium) the feed stays OFF; it needs the 8838 origin.
  Every "PCFrame" binding of the bridge goes through `ShowFrame` -> `SelectMonitorFrame` (the MID only on a change: its 0.5 s poll
  never fights the feed); `ClearPrivateState` drops the feed at once, the poll timer re-selects even while a poll hangs, a feed
  frame the character stops renewing for 1 s is dropped, and the bridge's `EndPlay` first calls `ReleaseMonitorFeed` (the MID goes
  back to the terminal canvas, or to no texture without one, and no feed texture stays referenced). The character starts a new
  epoch on every gate or bridge privacy-generation change (`SUB01_STREAMER_VISUAL_MONITOR_FEED_GATE open= epoch= reason=`, at most
  one line per second; the closed reason is refreshed every 0.5 s while closed): bytes read while closed are discarded, queued and
  decoded frames of another epoch are never uploaded, and the first 0.25 s of FIFO data after a reopen is discarded.
- **Acceptance window** (Kimi's review: there is no literal zero-window guarantee). The MID binding is cached: a gate that closes
  only because time passes (the 1.5 s confirmation growing old, a hung backend) is unbound at the next game-thread routing decision,
  i.e. the character's next tick (it renews or drops the feed every tick) or else the bridge's 0.5 s poll timer; a game-thread
  hitch delays both while the render thread keeps showing the bound texture. A real privacy or Vagon change also takes the poll's
  detection time. The sidecar's own gate (commit 8634ff9: grey frames at once on a privacy cut) covers that detection latency;
  the confirm-after playout keeps frames read after the runner locked off the screen. Not covered (no per-frame privacy in the
  stream): frames captured between a private page appearing and the sidecar's or the runner's privacy signal.
- **Lifetime**: the FIFO descriptor belongs to the pump task; it is closed by `monitor_feed` 0, by a read error, or when the
  character is destroyed (the task holds the feed by a shared pointer, so destruction may finish on the worker). The character's
  `EndPlay` is defined in the cinematic sources outside this installer, so v22 does not hook it: after `EndPlay` the descriptor stays
  open until garbage collection purges the character (a map load forces that purge); supporting an in-process level restart
  would first need that `EndPlay` cleanup (Kimi's condition). The pending-upload count (3) is feed-only
  backpressure, not a global memory bound: PC/device uploads do not check it, and a feed `Clear` plus `Update` can briefly reach 4.
- **Sizes**: the sidecar sends 1280x720 mjpeg at `-q:v 5` (a few hundred KiB a frame), inside the decoder's 1280x1024 and the
  scanner's 4 MiB limits; a larger `--size` would make every frame fail decode (`decode_failed=` counts it) and the feed fall back.
- **No per-frame UTexture2D in the bridges**: the PC bridge's `CreateTexture2DFromImage` (one texture per VGA frame) and the device
  bridge's `ImportBufferAsTexture2D` (one per phone/TV frame) became one persistent texture per screen and size, updated in place
  (`Sub01PersistentTexture::Ensure/Update/Clear`, every slot a `UPROPERTY` of its owner); `GraphicalFrame` / `Images` keep their
  meaning (what is shown; emptied on privacy).
- **cam2 exposure** (cam2 copies the webcam's post process; the house's histogram volume is EV100 -3..+3 with the default bias 1, and
  cam2's white walls clipped): `cam2_exposure` 0 = as copied (v21), 1 = automatic exposure (`AEM_Histogram` forced, even if the
  copied method were manual) with `cam2_ev_bias` (default) plus the EV100 range `cam2_ev_min..cam2_ev_max` while min <= max
  (default min > max: the volume's range stays), 2 = manual (`AEM_Manual`, physical camera exposure off: the bias is then the
  absolute log2 scale, +4 matches the webcam at its EV100 -3 clamp with bias 1, +2 is two stops darker) at `cam2_ev_bias`; modes
  1/2 force the capture's post-process weight to 1; mode 0 restores exactly what was copied. Applied on change, logged
  `SUB01_STREAMER_VISUAL_CAM2_EXPOSURE mode= bias= range= ... copied: ...`. The main camera is not touched. Default: mode 1, bias
  -1.0 (2 EV below the house's compensation, all else equal; Kimi confirmed the arithmetic and did not ask for manual -3, which
  would be 7 stops darker than the webcam); calibrate on rendered frames (auto +1/-1, manual +4/+2).
- Tuning keys (their own V22 line in the tuning reader): `monitor_feed` 0/1 (1), `monitor_fps` 1..60 (60), `monitor_delay_s` 0.5..3
  (0.75), `monitor_stale_s` 0.5..10 (2.0), `cam2_exposure` 0..2 (1), `cam2_ev_bias` -8..8 (-1), `cam2_ev_min` / `cam2_ev_max` -10..20
  (0 / -1 = not set). Logs: `SUB01_STREAMER_VISUAL_MONITOR_FEED started ...`, every 5 s `SUB01_STREAMER_VISUAL_MONITOR_FEED fps=
  decoded= dropped= stale= in_fps= shown= bound= allowed= open= epoch= confirm_age_ms= content_age_ms= queued= queued_kb= pending=
  dropped_older= dropped_epoch= dropped_overflow= dropped_untaken= rejected= upload_busy= decode_failed= resyncs= discarded_kb=
  decode_ms= decode_max_ms= upload_mib_s= textures= bridge_textures= target_fps= delay_s= stale_s= reason= window_s=`,
  `..._MONITOR_FEED_GATE`, and `..._MONITOR_FEED_BOUND` / `..._MONITOR_FEED_FALLBACK` on changes. Receipt: `monitor_feed_on/bound/
  allowed/open/fps/in_fps/target_fps/delay_s/stale_s/shown/decoded/dropped/upload_busy/stale/resyncs/epoch/queued/gate_reason/age_ms/
  textures/reason`, `pc_bridge_textures`, `cam2_exposure`, `cam2_ev_bias`, `cam2_ev_min`, `cam2_ev_max`.
- Offline only (stub, not Unreal): the reader against a real FIFO (gate, quarantine, newest frame, playout and confirm-after, one
  pump in flight, one texture, resync, bounded ring, pending-upload cap, no-progress fallback, `monitor_fps`, `monitor_feed`,
  foreign paths), the JPEG scanner, the persistent texture (AddressSanitizer), the patched bridge's own gate methods (phase,
  `EndPlay` release with and without a terminal canvas) and the exposure modes: `tests/test_native_streamer_visual_v2.py`. Not
  established offline (Kimi's list): a UE 5.8 compile, an RHI smoke test (first creation, subregion upload, rect change, borders,
  sRGB look, deferred cleanup, GC while uploads are pending), ImageWrapper on the sidecar's real JPEGs, rendered exposure. The
  engine APIs to check against UE 5.8 are listed in the review note.

## v23 live look corrections (`install_v23.py`, `// SUB01_STREAMER_VISUAL_V2_V23`, on v22)
For "he has to look real" (`docs/streamer/STATUS-20261024.md`, `docs/streamer/kimi/photos-20261024.md`). Design reviewed with Kimi
(`docs/streamer/kimi/native-v23-design.md`). ONE build, then live iteration on frames: every correction is a key of the same
tuning file (`sudo -u unreal python3 /home/unreal/tune.py key=value`, polled every 0.5 s). Every compiled default skips its code path
(no light created, nothing scanned or moved, no extra transform): the tests compare the proxy pose and the character side at the
defaults with the v21 build bit for bit. Edits `Sub01HomeLab.h/.cpp` and `Sub01HomeHands.h/.cpp` only; never the PC/device bridges,
the monitor feed or the cam2 code (v22). The shared tuning reader gets one delimited block (`// ..._V23 TUNING` ... `TUNING END`) right
after the `Field` lambda; the receipt fields go after the `face_aim_mean_s` line.

| key | range | default (= today) | what it does |
|---|---|---|---|
| `pelvis_pitch_deg` | -20..20 | 0 | hip hinge: Hips about his lateral axis, forward degrees (negative = sit up); each thigh keeps its orientation |
| `shoulder_drop_deg` | -10..20 | 0 | clavicles turned down (relaxed, not hunched shoulders) |
| `shoulder_back_deg` | -10..20 | 0 | clavicles retracted |
| `neck_back_deg` | -15..20 | 0 | chin tuck: neck back, head forward by the same angle (head over the shoulders, face angle kept) |
| `neck_share` | 0..1 | 0.4 | the Neck's share of the head channel (rest on Head); 0 keeps the neck skin with the hood ring |
| `neck_girth` | 0.9..1.2 | 1 | experiment: radial Neck scale across its long axis, children compensated exactly; skipped unless the Neck->child offset lies on one local axis (alignment >= 0.95, published) |
| `elbow_min_deg` | 0..150 | 0 | guard: the wrist target slides forward along the keyboard axis (same height, 0..15 cm) until the elbow opens to this; a target behind the shoulder is declined (slide -1), within 5 cm ahead of it the slide fades in |
| `elbow_pole_back` / `elbow_pole_out` | -0.5..1.5 | 0.5 / 0.3 | the elbow pole's back and outward weights (down stays 1) |
| `hand_orient` | 0..1 | 0 | hands turned so the fingers follow the keyboard axis, knuckles level, palm down (from bone positions) |
| `hand_yaw_in_deg` / `hand_pitch_deg` | -30..45 / -30..60 | 12 / 10 | inward yaw and downward pitch of the fingers (used when `hand_orient` > 0) |
| `finger_bend_deg` | 0..60 | 0 | index..pinky bent towards the palm, x1.0/1.2/0.6 on phalanges 1/2/3, additive on the clip |
| `mouse_scan` | 0/1 | 0 | adopt the RGB mouse if exactly one primitive component is plausible (registered, visible static-mesh leaf, not simulating); it glides with the keyboard pull-back; 0 glides it back and restores its mobility |
| `hand_on_mouse` | 0/1 | 0 | the right hand on a found mouse in `idle` and `reading` |
| `key_side_cm` / `key_up_extra_cm` | -80..80 / -40..60 | 0 / 0 | the key light moved off the webcam axis (positive side = his right) |
| `key_specular` | 0..1 | 1 | specular of the key, fill and rim (only if highlights clip) |
| `fill_cd`, `fill_front_cm`, `fill_side_cm`, `fill_up_cm`, `fill_temp_k` | 0..2, 0..120, -100..100, -40..80, 2500..8000 | 0, 40, 45, 0, 5000 | a fill spot between him and the monitor (0 cd = none) |
| `rim_cd`, `rim_back_cm`, `rim_side_cm`, `rim_up_cm`, `rim_temp_k` | 0..2, 20..150, -100..100, -20..120, 2500..10000 | 0, 60, 30, 40, 6500 | a rim spot behind him (0 cd = none; its own placement, positive side = his right); cam2 sees it on his back |
| `chair_scale` | 1..1.3 | 1 | the chair widened laterally about the seated pelvis |
| `chair_back_extra_cm` | -10..30 | 0 | the chair moved away from his back after the fit (the fit leaves it out) |
| `chair_side_cm` | -15..15 | 0 | the chair sideways (only for a measured asymmetric overlap) |

Eases: posture 12 deg/s, hand angles 30 deg/s, weights (neck share, poles, hand orientation) 1/s, girth and chair scale 0.2/s, chair
60 cm/s, key offsets and fill/rim positions 30 cm/s, fill/rim intensity 0.02 cd/s, the mouse 30 cm/s (only `key_specular` applies at
once); a v1 event eases everything back to the defaults. Fill and rim use the key's lighting channel (`key_body_only`), softness and radius.
Logs: `SUB01_STREAMER_VISUAL_V23 state= clipTime= tuningSequence= ... neckAxisAlign= incline= headAheadCm= elbow= slideCm= residualCm= elbowBackCm=
orientErr= tipsAboveKeysCm= mouse= chairScale= chair=` at once on a tuning change and every 10 s while any key is off its default;
`SUB01_STREAMER_VISUAL_V23_LIGHTS` (positions, cd) on a tuning change; `..._V23_MOUSE_CANDIDATE path= ... plausible=` and
`..._V23_MOUSE found=`. Receipt: `v23_<key>`, `v23_changed`, `v23_incline_deg`, `v23_head_ahead_cm`, `v23_slide_*`, `v23_residual_*`,
`v23_elbow_back_*`, `v23_orient_err_*`, `v23_tips_above_keys_*`, `v23_tips_min_above_keys_*`, `v23_neck_axis_align`, `v23_mouse`, `v23_chair_extra`,
`v23_chair_scale_applied`.

Live session (Kimi's order; lock the webcam/cam2 exposure first; one step at a time, judged on frames and the receipt):
0. baseline frames (webcam, cam2, spectator) and the receipt;
1. pole test: `elbow_pole_back=0 elbow_pole_out=0.45` (does the cam2 elbow fan move?);
2. reach test, old pole: `elbow_pole_back=0.5 elbow_pole_out=0.3 hand_back_cm=5`;
3. elbow combined: `hand_back_cm=5 elbow_min_deg=90 elbow_pole_back=0 elbow_pole_out=0.45` (if the fan survives at 90-95 deg, it is the
   hoodie's weights, not the IK);
4. posture: `pelvis_pitch_deg=-10 typing_lean_deg=-14 shoulder_drop_deg=3 shoulder_back_deg=2 neck_back_deg=5`; judge `v23_incline_deg`
   (target <= 5 deg); if still high `pelvis_pitch_deg=-12 typing_lean_deg=-16`;
5. hands: `hand_orient=1 hand_yaw_in_deg=12 hand_pitch_deg=10 finger_bend_deg=8 finger_curl_deg=0`, then `hand_height_cm` in 0.25 steps
   on `v23_tips_above_keys_*`; `hand_span_cm=24` if they still overlap;
6. neck seam: `hide_slot=4`, `hide_slot=5`, then `hide_slot=-1`; `neck_share=0` (0.10-0.15 if yaw looks rigid); `neck_girth` 1.05, at
   most 1.10;
7. chair: `chair_scale=1.08 chair_back_extra_cm=2` (then 1.12 / 4);
8. key and fill: `key_side_cm=-55 key_up_extra_cm=10 fill_cd=0.01 fill_side_cm=45 fill_up_cm=0 fill_temp_k=5000`;
9. rim, optional: `rim_cd=0.006 rim_back_cm=60 rim_side_cm=30 rim_up_cm=40 rim_temp_k=6500`;
10. mouse: `mouse_scan=1` alone (the log must show `found=1`, the mouse moves with the keyboard); then `hand_on_mouse=1`.
An approved set is kept as the tuning file's preset; the compiled defaults stay "off" for rollback.
Mouth: no jaw bone, no facial bone, 0 morph targets on this body; real mouth movement needs visemes or a jaw rig on a re-imported head
(options ranked in the Kimi file). Not built.
