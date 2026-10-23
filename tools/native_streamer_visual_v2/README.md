# `-Sub01StreamerVisual` v2: curated desk animation driven by the streamer agent

The installers patch the pod module sources in place: string anchors each found exactly once, all or nothing, atomic
writes, CRLF/LF kept, JSON report with before/after sha256, refusal of a second run by marker.
`install.py` (`// SUB01_STREAMER_VISUAL_V2`) builds v2; `install_face_camera.py` (`// SUB01_STREAMER_VISUAL_V2_FACE`)
goes on top of it (`face` camera, desk guard); `install_pin_fix.py` (`..._PINFIX`) on top of that, `install_no_pin.py`
(`..._NOPIN`) next, `install_seat_fix.py` (`..._SEATFIX`, the one that actually seats him: below) last. Same R9 gate,
spectator camera and ghost views as v1; no new AnimGraph.

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
| `face` (seat fix) | webcam on the monitor: bounds centre +22 up, 2 towards him, 12 to his left = (205.1,-370.1,136.75), aimed at the mean Head bone of 1 s (else body +120) | 70 |

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

Manual check on the pod (stop the agent first; Ctrl-C ends it; the camera returns to spectator 2 s later):
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
python3 tools/native_streamer_visual_v2/install_mouth.py --source "$M" --dry-run        # on v2 alone or on any stack above
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
- Face camera: a fixed webcam on the monitor, bounds centre (217,-367.67,114.75) + 22 up + 2 towards him + 12 to his
  left (over his head: the monitor is wider than his seat) = (205.1,-370.1,136.75), aimed at the mean Head bone of 1 s
  (the loops sway the head ~5 cm) once per selection after the seat offset has settled (else 2 s), FOV 70, pitch ~-26.
  Verified frames (game g): `reading`/`talking` = face and shoulders slightly from above, chair and hall behind him;
  `typing` = mostly the top of his head (the typing loop hunches him into the camera). With his head 35 cm from the
  screen the owner's FOV 40-45 shows the face alone and the upper torso cannot be framed from the monitor. Live tuning
  without a rebuild: `/home/unreal/.sub01-private/streamer-visual-face-tuning.json` (uid 1001, mode 0600,
  `{"schema":"sub01.private-streamer-visual-face-tuning.v1","sequence":N,"up_cm":22,"forward_cm":2,"side_cm":-12,
  "aim_drop_cm":0,"fov_deg":70}`, values clamped, applied when `sequence` grows; `/home/unreal/face-tune.py <up>
  <forward> <side> <drop> <fov>` writes it, `clear` removes it); the compiled defaults are the verified framing.
- Receipt adds `seat_offset`, `seat_offset_cm`, `seat_offset_yaw_deg`, `seat_offset_applied`, `seat_offset_settled`,
  `pelvis_world`, `head_world`, `face_camera_location`, `face_camera_aim`, `face_camera_tuning_sequence`, `camera_world`,
  `body_bounds`. Logs: `SUB01_STREAMER_VISUAL_SEAT_FIX_READY`, `..._SEAT_OFFSET` (per clip), `..._FACE_RIG` (66 Mixamo
  bones, only Neck/Head/HeadTop_End near the face, 0 morph targets: no jaw or visemes to drive), `..._FACE_CAMERA`.

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
