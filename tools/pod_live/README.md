# Pod: the native Unreal home in live mode (2026-10-23)

Scripts used on pod `sub01-windows-recovery-20261021` to switch the native home from the manual/cinematic
review game to a game that follows the private backend. All run as root and start the services as uid 1001.

| Script | What it does |
|---|---|
| `launch-live-game-20261023.py` | starts `UnrealEditor-Cmd … -game -Sub01CompletionSandbox -Sub01ManualView -Sub01LiveHome -Sub01NativeControl=…/native-control.json`, waits for the first world tick, writes `{"revision": n, "mode": "live"}` to the control file and waits for `SUB01_LIVE_HOME_BOUND` and the backend's `native_consumer.bound`. Status in `live-game-20261023/status.json`. |
| `patch_live_viewer.py` | copies of the read-only window viewer accept the `live` view mode (the original only served frames in `manual`); adds `--port`. |
| `start-live-viewer-20261023.py` | finds the game window by pid, starts the patched viewer (`--stop-old` ends the viewer of the previous game). |
| `start-pc-runner-20261023.py` | replaces the TV/phone-only device proxy on 8832 with `scripts/home_pc_runner.py` (serves `/pc/*` and `/devices/*`). Needs Node (found under `/workspace/sub01-home-private/streaming/node-v22.14.0-linux-x64/bin`) and the pinned v86 files (`computer/bootstrap.py`). |

Also done by hand that day: door modes set to `auto` through the bridge (`POST /home/controls`), and the bedroom TV
movie copied to `/home/unreal/runtime-tools/BigBuckBunny-720p.webm` (the game only checks that the file exists).

What the live game cannot do yet: sit at the desk or sofa and lie in bed. `ValidatedHandsPostures` lists only
`Walk` and `Idle`, the `/Game/Sub01Hands/Seating` clips are on another skeleton, and no `SeatedReviewManifest` /
`BedReviewManifest` is configured. The prepared station-motion integration (`animation-integration-v1`, never built)
targets exactly the running source; building it is a separate step.

## Ghost camera tour (spectator views)

The native module already has `FSub01GhostViews`: up to 4 scene-capture cameras that fly through the house with
collision, mirror his body as a poseable copy, and write `frame-<key>.png` (640x360) at the policy's rate. They are
off until root writes `/run/sub01-home-private/ghost-policy.json` for the exact game pid/start ticks.

| Script | What it does |
|---|---|
| `ghost-tour-start.py PID START_TICKS [hours]` | writes the policy (capacity 2, 10 fps, spawn at the aisle node), prepares `ghost-visitors/` and starts the pilot as uid 1001. |
| `ghost-pilot.py` | keeps one camera request alive, flies along the live node graph (stairs included) and saves 4 views per room into `ghost-tour-20261023/`. 44 frames in about 60 s on 2026-10-23. |

Bathroom privacy closes every ghost view (the game does that); a new camera spawns again at the policy spawn point.
