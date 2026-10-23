# `-Sub01StreamerVisual` v2: curated desk animation driven by the streamer agent

Two installers patch the pod module sources in place: string anchors each found exactly once, all or nothing, atomic
writes, CRLF/LF kept, JSON report with before/after sha256, refusal of a second run by marker.
`install.py` (`// SUB01_STREAMER_VISUAL_V2`) builds v2; `install_face_camera.py` (`// SUB01_STREAMER_VISUAL_V2_FACE`)
goes on top of it: the `face` camera and the desk root-motion guard. Same R9 gate, authored body placement, spectator
camera and ghost views as v1; no new AnimGraph.

## What v2 does
- **Events**: v1 (`...event.v1`, source `human_vagon_observation`) is unchanged (frozen R9_Sitting at 0.7 s, gaze, nod
  on each new event). v2 (below) is accepted next to it with the same uid/mode/pid/start-ticks/expiry/sequence checks.
- **Clips** play through the AnimInstance's Previous/Current players and 0.24 s crossfade. A fresh loop starts at the
  phase (24 samples) whose hands are closest to the last evaluated hands. At most one state change per 0.6 s (latest
  wins); `reacting` applies at once. Missing clip or other skeleton: `SUB01_STREAMER_VISUAL_CLIP_MISSING <path>`, frozen R9.
- **Liveliness** (deterministic, bounded): breathing 0.6 deg at 0.22 Hz on Spine1/Spine2; sway <= 1.5 deg on the gaze;
  `talking` adds <= 0.9/0.6 deg; entering `reacting` nods once. `intensity` scales sway and nod. No face rig: no lip sync.
- **Desk guard** (face patch; field report: chair empty in `mouse`/`idle`, `body_world` unchanged). The streamer branch
  never sets `RootMotionMode`, so the instance keeps RootMotionFromMontagesOnly: these players never extract root motion
  and a clip's root track lands in the pose unless the asset has `bForceRootLock`. Every v2 frame the bones above the
  pelvis take R9@0.7's locals and the pelvis stays within 8 cm / 25 deg of R9's. Each clip's pelvis is audited once
  (5 phases, `SUB01_STREAMER_VISUAL_CLIP_AUDIT` with the root-motion flags); > 25 cm / 25 deg = another station.
- **PC monitor**: refreshed by the bridge's own 0.5 s timer, no focus needed; the per-tick unfocused
  `SetOperatorFocus(false)` (a `/pc/session` POST per frame) now runs only when something is focused.
- **Receipt** keeps every v1 field; adds `schema_version`, `state`, `requested_state`, `base_clip`, `clip_time`,
  `intensity`, `breathing`, `camera`, `camera_blend`, `camera_fov`, `face_camera_blend`, `face_camera_aim_source`,
  `desk_offset_before_pin_cm`, `clip_audit_done`; `clip` names the clip actually playing.

| state | clip (`/Game/Sub01Hands/Cinematic20261022/...`) | playback | if the audit finds it off-desk |
|---|---|---|---|
| idle, reading, talking, reacting | `Desk7_f696.../SupportedWebsite` | loop, hand-matched phase | frozen R9 |
| typing | `Desk7_1da8.../SupportedDeskTyping` | loop, hand-matched phase | sitting loop |
| mouse | `Reach_c8ac.../AuthoredReach` | one play, held on last frame | sitting loop |

`talking` adds the speech cadence, `reacting` the nod. Before the audit is published only the pinned sitting loop plays.

| `camera` | framing | FOV |
|---|---|---|
| `spectator` (default, and when the event is > 2 s old) | authored v1 view (334,-209,151) -> (214,-289,116), untouched while held | 65 |
| `monitor` | pivot -70 facing +45 right +45 up = (275.2,-232.6,161), aimed at the monitor centre (217,-367.67,114.75) | 65 |
| `face` | monitor centre +28 up, 10 towards him = (219.5,-358.0,142.75), aimed at the Head bone (else body +120) | 42 |

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
python3 tools/native_streamer_visual_v2/install_face_camera.py --source "$M" --dry-run  # then without --dry-run
/workspace/sub01-private-recovered-engine/Engine/Build/BatchFiles/Linux/Build.sh Sub01HomeLabEditor Linux Development \
  -Project=<project>/Sub01HomeLab.uproject      # previous builds: ~27 min with 2 workers
```
Launch with `-Sub01StreamerVisual` (not `-Sub01AuthoredCinematicReview`), `SUB01_PC_ORIGIN=http://127.0.0.1:8832`,
`SUB01_ADMIN_TOKEN`. Logs: `SUB01_STREAMER_VISUAL_V2_READY`, `SUB01_STREAMER_VISUAL_FACE_READY`, `..._DESK_PIN`,
`..._CLIP_AUDIT`, `..._STATE a -> b`, `..._FACE_CAMERA`. Not verified offline: the clips' authored station (the audit
log says), the spine pitch axis, the visual result. Tests: `tests/test_native_streamer_visual_v2.py` (stub compile only).
