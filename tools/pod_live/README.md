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
