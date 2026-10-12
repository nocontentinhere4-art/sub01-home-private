# Inhabited first-person home

This private repository adds a functional home to the SUB-01 brain server. Work stays on localhost; deploying it requires a separate explicit owner instruction. `HOME_ENABLED=1` activates it at `/` and `/house`; `/room-classic` remains available. The default stays disabled until the visual and production checks are complete. `HOME_ENTRYPOINT=0` keeps the legacy front page while the live home can be checked at `/house` on the same brain server.

The same server owns his activity, position, PC, Pong game, phone notes and journal. Watching the home does not create another brain, browser, operating system or game. Follow mode receives a compact 5 Hz state feed, interpolated by the renderer. Explore mode moves a visitor camera without moving SUB-01. Bathroom occupancy replaces the entire render with a privacy scene, including while a spectator explores elsewhere.

## Rooms and movement

A two-level home contains office, kitchen, living area, wooden staircase, bedroom, bathroom, balcony and an opening front door with an entrance terrace. Continuous waypoints map his existing needs and brain-guided activity selection into the house. New gated activities are Linux computer use, wall-TV Pong and a bathroom break. An optional operator intent is a nudge under the same needs/sleep rules, never a forced brain verdict.

## Devices

- PC: an actual shared v86 x86 Linux guest (see `computer/NOTICE.md`), and the existing guarded real-browser screen. Files persist in a VM snapshot. The initial computer agent chooses from bounded guest commands; it cannot yet use arbitrary desktop applications.
- TV: real local Minecraft Java survival world, controlled through Mineflayer and streamed as a read-only first-person image. See `games/minecraft/README.md` for its limits, EULA gate and pinned dependencies. Shared server physics for Pong, plus a view of the existing brain-voted live chess game. His motor and attention groups affect the left controller; scoring feeds simulated reward/salience back into the brain. This controller is not evidence of comprehension or consciousness. A viewer can challenge the right paddle with bounded inputs.
- Phone: clock, activity journal, notes, messages/brain impulses, existing guarded browser, and a view of the existing music selection. These are functional web apps, not an emulated mobile OS.

`SUB01_ADMIN_TOKEN` protects terminal input, notes, lamp/curtain settings and operator intents. Public Pong input is rate limited and finite/bounded. No production secrets enter the emulator, public state or browser assets. `home.json` and `computer.bin` live in the existing persistent data directory. Node.js is added to the container for the VM.

## Materials and performance

Asset source/license/hash metadata is in `web/house/assets/manifest.json`. Scanned Poly Haven CC0 furniture and 1K PBR materials replace procedural lounge furniture and flat surfaces. Two diffuse maps have neutral colour variants; geometry remains original or CC0. Three.js includes its MIT license. The room is a single WebGL scene, with one cached shadow map, an actual indoor HDR lighting capture, 512px prebuilt mobile variants, a small prefiltered environment, instanced skyline and a capped pixel budget. Fixed architecture is batched by compatible materials/attributes. This is an improvement toward the X reference; matching its Unreal architectural rendering remains an open visual target.

## Verification

`python -m pytest tests/test_home_world.py -q` checks every waypoint edge against rendered furniture/wall colliders, all node-to-node routes, continuous movement/replanning, bathroom privacy, new activity selection and persistence. `python tools/check_home_vm.py` boots the real guest, writes a file, saves/restores and verifies it after restart. Browser checks must cover desktop and phones, PC, Pong, notes, impulses, stairs, bathroom entry/exit and performance after all assets load.

Baseline main at the start of this branch has unrelated failing tests. A full local run returned 1842 passed, 64 skipped, 9 failed. Six of those failures were reproduced with the original `live_server.py`, `life.py` and Dockerfile restored (legacy desk-rule, audience/decider, sleep replay, dated neurogenesis expectation and GPU label). Two clip failures are macOS subprocess resource-limit errors; the remaining spiking websocket test reset its connection. They must not be represented as a green full suite.

## Offline contact lighting

An earlier accidental public home deployment was rolled back. The private build is tested on localhost, not a production rollout. The public home routes were removed and its temporary operator credential revoked. Do not deploy from this repository. Local checks confirmed the brain feed, Pong, Linux guest, operator commands and real isolated browser screen. Photographic Tokyo window layers reuse the existing room assets and credits. Windows, scanned cushions and a desk lamp include 512px phone variants. Spiking growth preserves formed-synapse source IDs when rebuilding its connections.

A CPU ray-traced contact-occlusion atlas adds depth to fixed architecture without a post-processing pass. The geometry atlas is about 4 MB; its approximately 1 megapixel grayscale JPEG uses about 4 MB of GPU memory (a 512px mobile variant is prebuilt). Dynamic doors and devices keep their original geometry. Matching world bounds reject outdated baked parts. The fallback remains usable if the optional atlas fails.

To rebuild, export the house with the local-only `?bake=1` button, rename `out/home-bake-source.png` to `.glb`, and install `xatlas`, `pygltflib`, `numpy` plus the npm packages `three@0.180.0` and `three-mesh-bvh@0.9.2` in a tooling directory. Run `prepare_home_lightmap.py SOURCE.glb web/house/assets/lighting/architecture.glb`, then `HOME_BAKE_MODULES=/path/to/tooling node tools/bake_home_contact.mjs web/house/assets/lighting/architecture.glb`. Convert its PGM to the full/lite JPEGs with Pillow. The export filename is only an accommodation for the existing local snapshot helper; it contains GLB bytes. This is ambient contact lighting, not a claim of full global illumination or Unreal quality.


## Current indirect lighting and Minecraft checks

The default local renderer now loads `gi-architecture.glb` plus day/night HDR indirect-light maps. Their manifest records 32 Cycles samples and four diffuse bounces, with mobile variants. Direct shadows and dynamic doors remain handled by the live renderer; this is baked indirect illumination, not a claim of reference-quality Unreal rendering. `?ao` uses the earlier contact-only fallback.

The October 12 local Minecraft check confirmed world startup, player connection, wood collection, individual block placement, actual TV frames, pause/disconnect on a game switch and inventory persistence after restart. The support-block refusal appeared in the real event ledger. The focused Python checks returned 16 passed, and the spatial check verifies an escape vector that increases distance from a threat. A controlled live hostile trial, sustained game learning and a full house acceptance pass remain open. The UI uses English throughout.


## Arrival motion and shutdown

Walking now brakes ahead of corners and seated destinations, retaining momentum on straight segments. The route regression checks continuous movement and low speed on final approach; the focused home/game/growth checks returned 17 passed. Visitor acceleration/braking checks remain consistent at 30/60 fps. A live route sampled 40 states with bounded walking speed.

The main task now waits for child cleanup after cancellation before closing the event loop. A local SIGTERM test exited with code 0, and Minecraft logged Saving players, Saving worlds and All dimensions are saved before the next successful startup. The VM worker also gets its cleanup interval. Reference-level visual quality remains an open target.


## Experimental forecasting (not controlling the live home)

TimesFM 2.5 was tested in an isolated Python environment, with the pinned official 200M checkpoint. Install `tools/brain_forecast_requirements.txt`, then run `tools/test_brain_forecast.py` for the existing QC-passed fMRI records. For a local simulated-brain trial, use the house environment to run `tools/collect_brain_forecast.py`, then the forecast environment to run `tools/test_brain_forecast.py --live`. No brain recording is uploaded; only model weights are downloaded. Raw traces, weights, plots and reports stay under ignored `data/timesfm/`.

The fMRI trial used four recordings, seven network means and three forecast origins each (84 forecasts). TimesFM MAE was 0.5652 versus 0.7034 for last-value persistence, 0.5554 for the context mean, and 0.5344 for AR(8). The local live trial used one 150-second, 4-Hz trace across 13 networks, with three origins and a 60-second horizon (39 forecasts). MAE was 0.01975 for TimesFM versus 0.02549 persistence, 0.01852 context mean and 0.01847 AR(8). Overlapping windows are not independent. These tests do not justify switching the brain to TimesFM or claiming behavioral foresight or consciousness. More recordings across activities and intervention conditions are needed.


## Physical bedding geometry

The bedroom now uses pre-settled Blender cloth for its duvet and foot throw, plus sleeping pillows derived from the existing CC0 Poly Haven throw_pillows_01 geometry. The second layer collides with the settled duvet. Materials reuse the existing linen maps. Full geometry is about 1.5 MB, with a 628 KB lightweight variant; no cloth solver runs in the browser. The procedural bedding remains a loading-error fallback. Runtime checks loaded physical/physical-lite and preserved 63 matched indirect-light parts at about 47–48 fps on this Mac; this is not a general phone benchmark. The current proof is `docs/screens/home/private-physical-bedding.jpg`.

The lighting importer also matches unchanged world-space bounds and element counts when furniture changes shift sequential IDs. It rejects ambiguous or changed shapes rather than deforming them. A new complete bake can improve light on the replaced cloth later. Rebuild with Blender in background mode running `tools/build_home_bedding.py`; sources and generated-file hashes are in `web/house/assets/bedding/bedding.json`.


## Bathroom overlay privacy

Privacy now closes and clears an already open computer/phone/TV panel, releases held Pong controls, hides device launchers and stops panel-frame refreshes. It covers both SUB-01 entering the bathroom and a visitor camera entering the privacy bounds. Follow/Explore remain available for navigation. The live check opened the PC, nudged a bathroom visit and observed one privacy draw call, an empty hidden panel, hidden device controls, and no device opened by E. On leaving, the computer panel could be opened again. Proof: `docs/screens/home/private-bathroom-overlays-censored.jpg`. This is presentation privacy; it does not revoke operator/API access or censor unrelated brain telemetry.
