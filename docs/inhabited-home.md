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

Asset source/license/hash metadata is in `web/house/assets/manifest.json`. Scanned Poly Haven CC0 furniture and 1K PBR materials replace procedural lounge furniture and flat surfaces. Two diffuse maps have neutral colour variants; geometry remains original or CC0. Three.js includes its MIT license. The room is a single WebGL scene, with cached full-mode sun/pendant shadow maps, an actual indoor HDR lighting capture, 512px prebuilt mobile variants, a small prefiltered environment, instanced skyline and a capped pixel budget. Fixed architecture is batched by compatible materials/attributes. This is an improvement toward the X reference; matching its Unreal architectural rendering remains an open visual target.

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


## Browser availability state

The isolated browser can be alive but have no permitted/current page after failed searches. Previously its public state could stay idle (away from the screen) even when SUB-01 was seated and researching. It now reports waiting when an active screen has no current page, and the home panel uses that reason. This does not fabricate a live page or relax robots, overlays, source cooldowns or rate limits. The local check confirmed waiting in the API and UI while the real Linux guest was separately ready from its saved snapshot. The browser service was healthy, both page statuses were empty, and a YouTube-key-unavailable note was present. No current desk frame was available in that check. Further work is needed on useful activity selection when sources do not answer. Proof: `docs/screens/home/private-browser-waiting.jpg`.


## Operator page navigation

The Browser tab now has a public-address field, routed through authenticated `/api/home/browser` and the isolated service `/navigate`. It uses existing URL, private-session, robots, heavy-page, wall and host/rate checks. Explicit operator revisits bypass only the seven-day novelty preference, not those checks. Bathroom occupancy blocks this action. Opening a page updates the shared screen and reading input; automatic browsing resumes after the 30-second opening interval. The panel labels the actual on-screen title independently of the typed address.

The local UI test opened the official Python tutorial and captured it on the desk monitor and PC panel (`docs/screens/home/private-browser-python.jpg`). The URL/auth/privacy contract and existing screen/guard checks returned 73 passed. This gives direct navigation when automatic searches fail; it does not guarantee every website is available.


## Phone navigation and narrow layout

The phone Browser app now has the same authenticated public-address navigation as the PC, targeting the separate phone context. Its current-page title comes from the phone screen status. Operator access is available in a collapsible section above content, and the address controls precede the tall page image so they remain reachable at 390 px. The local desktop browser viewport check opened the W3C CSS overview in the phone context and showed it in the phone app. The Python tutorial failed to load in that check, so this is not a claim that every address works. Operator interaction was tested while the character was asleep; it was not an autonomous choice by SUB-01.

The URL/auth/bathroom regression also verifies phone targeting. The viewport override was reset after inspection. Proof: `docs/screens/home/private-phone-browser-mobile.jpg`; physical-phone performance remains unverified.


## Entrance terrace movement

The visitor can use the full terrace width beyond the doorway throat, while its side and far rails bound the walking area. Both planter pots have collision bounds. A wooden threshold bridges the entrance and terrace. The entrance frame has no window mullion across the passage.

The real localhost UI check walked from the bed entry onto the landing, down the complete staircase, through the opening door, across the terrace from x=0.91 to x=3.09 at z=4.80, and back indoors using W/A/S/D and drag controls. SUB-01 remained asleep in bed throughout. The renderer retained 63 matched indirect-light parts and showed about 45–48 fps on this Mac while active. The terrace helper check and all nine HomeWorld tests passed. Proof: `docs/screens/home/private-terrace-exit.jpg`. The exterior currently ends at this terrace; an explorable street is not implemented.


## Responsive bathroom screen

The rendered privacy screen now paints at the viewport aspect ratio, with bounded texture resolution and a wrapped caption. Canvas GPU storage is disposed and re-uploaded after a dimension change; merely flagging the resized canvas for update left the old texture stretched in the actual browser check. The scene remains replaced, so the privacy message appears in captured frames too.

The localhost visitor test opened the PC panel and walked into the upstairs bathroom: the panel closed and device controls disappeared. After resizing from 1920×828 to 390×844, the privacy text remained proportionate and readable. Resizing back and walking out restored the device controls. This checks a narrow desktop-browser viewport, not performance on a physical phone. Proofs: `docs/screens/home/private-bathroom-responsive-desktop.jpg` and `docs/screens/home/private-bathroom-responsive-mobile.jpg`. Related HomeWorld, device API and browser API checks: 12 passed.


## Recessed kitchen sink

The kitchen's flat black sink placeholder has been replaced with a recessed basin, metal rim, drain and curved tube faucet. One extruded stone countertop has an actual hole and no seams between separate slabs. The base cabinet is lower beneath the basin so it does not fill the cavity. A small unshadowed work light below the upper cupboard follows the existing shared lamp setting. This is a visual fixture; running water, washing and cooking interactions are not implemented.

The actual localhost visitor walked downstairs and along the narrow sofa/stair aisle to inspect the kitchen. The new geometry rendered at about 46–48 fps on this Mac. Switching the protected shared lamp setting off darkened the worktop and switching it back on restored it. Existing geometry retained 61 matched indirect-light parts; the changed cabinet/countertop rejected their old bake and still need a new bake. Nine HomeWorld tests and the movement/interaction JS checks passed. Proof: `docs/screens/home/private-kitchen-recessed-sink.jpg`.


## Interior changes in baked batches

The previous bake guard checked total element count and outer bounds. A changed cupboard inside the large dark-wood batch retained both, so loading the bake restored its old top and filled the recessed sink with wood. The guard now compares world-space vertex positions in both directions, allowing UV seam duplication, vertex reordering and 0.3-mm export rounding. The changed batch is rejected while unchanged parts retain their lighting. A geometry regression reproduces the same-bounds/same-count interior edit.

The live localhost renderer retained 60 matched indirect-light parts and displayed the open metal basin and drain instead of the old wooden top, at about 48 fps on this Mac. Nine HomeWorld tests and the new shape regression passed. Proof: `docs/screens/home/private-kitchen-bake-corrected.jpg`. A new bake remains needed for changed furniture; vertex positions alone do not verify triangle connectivity for hypothetical rewiring using exactly the same vertices.


## Updated indirect lighting and workflow reference

The actual current house was exported through its local-only bake button. The exporter now waits for physical bedding, caps exported material images at 512 px to stay below the existing 64-MB local snapshot limit, and reports success/failure. This does not change runtime texture resolution. Physical duvet, throw and pillows register stable receiver IDs and finish loading before the light-map importer runs.

A fresh 903×1234 atlas contains 71 receivers. Blender Cycles CPU calculated day and night diffuse indirect light with 32 samples and four diffuse bounces; validated HDR files and their lighter variants replace the earlier bake. The source hash, output hashes and measured bake statistics are in `web/house/assets/lighting/indirect-bake.json`. Previous generated versions remain in ignored `out/lighting-v2/previous/`. Lighting URL versions invalidate the old browser cache.

The real localhost full renderer applied 71 parts; forced lite mode applied 69 and loaded physical-lite bedding without logged errors. Full mode showed about 47 fps on this Mac. Two differing simplified cloth parts keep direct/environment lighting in lite mode instead of accepting a mismatched full-mesh bake. Proof: `docs/screens/home/private-bedding-indirect-v2.jpg`. Physical-phone performance and reference-level visual fidelity remain unproven.

Workflow reference read in Chrome: https://x.com/SimbasJungles/status/2109295930021208144 . The author describes scripted Blender-to-Unreal construction, repeated fixed-camera comparisons, emphasis on cinematic lighting, and profiling on an RTX 4090. We can adopt scene iteration and profiling while adapting the effects to the requested local browser. Sunbeam-selective dust and atmospheric shafts remain work to implement and measure; motion blur is not added by this bake.


## Sunlit dust experiment

A bounded additive point layer uses 500 particles in full mode and 100 in lite, in a single draw without a texture or shadow pass. Each vertex projects toward the sun onto the west/front window apertures. Particles outside those volumes become transparent; the bathroom bounds are excluded. The layer is disabled with closed curtains, low sun or an exterior camera. Geometry still uses depth testing. This is an approximation: furniture does not cast shadow volumes onto the particles, and no volumetric shaft or fog scattering pass has been added.

Local-only `?light=morning`, `noon`, `evening` or `night` renders a labeled lighting study. It changes only renderer/window lighting; the brain, phone clock, sleep and activity state retain their live time. Default rendering continues to use the simulation clock. The real localhost morning check compiled without logged errors and configured 500 particles with open curtains. Closing curtains set the effect to off; the live night view remained off even after opening them. Curtains were restored closed. The views showed about 46–48 fps on this Mac. Particle visibility remains subtle and visual tuning is incomplete. Proof of the morning room lighting, not a prominent shaft effect: `docs/screens/home/private-morning-light-study.jpg`.


## Lounge passage and stair-foot route

The sofa and its cushions moved 20 cm west; the plant moved toward the front window to clear the sofa corner. Its contact patch and collision bounds follow the move. The shared character seat offset now places his seated camera at the sofa's new center. A lounge gate keeps TV routes in front of the staircase foot before turning toward the sofa; the former front-to-sofa diagonal cut the first stair tread at ground height. The sofa now links to the kitchen gate through the west aisle.

A regression samples every graph edge and rejects ground-height paths through the stair tread rectangle. All ten HomeWorld tests passed. After a graceful local restart, the brain restored 505,000 neurons, 1,039 formed synapses and 110 learned decisions. The actual visitor walked downstairs and through the sofa/stair passage at about x=-0.52 to the kitchen without hitting the sofa collider, at approximately 47–49 fps on this Mac. SUB-01 remained asleep; the autonomous TV route is verified by the world tests rather than a live awake walk in this check. Proof: `docs/screens/home/private-lounge-passage.jpg`. The changed furniture/contact placement needs a fresh light bake; aligning the sofa's facing direction with the TV remains a visual/layout follow-up.


## TV-facing lounge layout

The sofa now faces the west-wall TV and is centered on its z=0.1 sightline. Its 2.5-m length is measured along the rotated z axis; the furniture loader retains x-axis sizing by default for other assets. The coffee table sits between sofa and TV, while the rear aisle stays open for kitchen access. Cushions, rug, contact patches and collider bounds follow the layout. The shared standing TV node is (-0.45,1.65,0.1); the seated camera becomes (-1.8,1.3,0.1) and looks toward the wall screen without a sideways head turn.

All ten HomeWorld tests passed, including ground routes avoiding stair treads and the restored sofa-seat sightline. Movement and interaction JS checks passed. In the actual localhost UI, a visitor walked down from the bedroom, along the aisle and looked across the sofa/table toward the centered TV, at about 46–48 fps on this Mac. The local backend was gracefully restarted for the updated shared seat/node logic. SUB-01 remained asleep, so this is visual/layout and offline world evidence rather than a live awake game session. Proof: `docs/screens/home/private-sofa-facing-tv.jpg`. Updated furniture placement still requires a fresh indirect-light bake.


## Personal view controls

The View panel adjusts vertical view angle (50–90°, default 64°) and pointer look speed (50–200%, default 100%). Preferences persist per browser with validated bounds and recover from malformed or unavailable storage. Reset view restores the defaults. These settings affect the viewer camera, not the shared brain or house state. Escape closes the panel, including from its focused sliders.

Opening any panel clears visitor movement and held controls; movement keys and canvas dragging are ignored while the panel is open, apart from the existing Pong paddle arrows. The View button is hidden by bathroom privacy alongside the device controls.

The real localhost UI set 80°/80%, reloaded and read those same values, then restored 64°/100%. The panel fit a 390×844 desktop-browser viewport. In Explore mode, holding W for 1.5 seconds with the panel open left the position exactly [-1.2,4.65,-2.9]; Escape closed it. Ten HomeWorld checks and preference, movement and held-control JS checks passed. Physical-phone gesture quality is still unverified. Proofs: `docs/screens/home/private-view-controls-desktop.jpg`, `docs/screens/home/private-view-controls-mobile.jpg`.


## Indoor direct shadows

The lounge pendant now uses a downward spotlight with a 1024-pixel cached shadow map, a broad soft cone and a small depth bias. This gives direct furniture/floor shadows even at night, when the sun light is off. The other ceiling and desk/bed lamps retain their previous unshadowed fill. Sun shadows are enabled only while the sun is above its intensity threshold. Forced lite mode now disables runtime shadow mapping altogether and retains the precomputed indirect maps and live unshadowed lighting.

The actual localhost night renderer reported pendant shadow mode, showed furniture shadows on the rug/floor, and displayed approximately 46–48 fps on this Mac. Forced lite reported indirect-only and loaded without logged errors. Ten HomeWorld checks, bake-shape, view-control and interaction JS checks passed. Proof: `docs/screens/home/private-lounge-indoor-shadows.jpg`. Shadow maps remain cached between the existing invalidation events; moving-door shadows can lag until the next refresh. The changed lounge layout and spotlight still need a new indirect bake.


## Current lounge bake and moving-door shadows

A new 899×1234 day/night Cycles atlas was generated from the TV-facing lounge and downward pendant spotlight, restoring lighting for all changed contact patches and furniture shapes. Full mode applied all 71 receivers; forced lite applied 69 and reported indirect-only without logged errors. File sizes and SHA-256 hashes were checked against the updated manifest. Raw exports, intermediates and rollback copies are now explicitly excluded from Git by `out/lighting-v*/`.

Cached door shadows now request updates at most 8 Hz during motion, followed by a final settled-pose update. Leaving bathroom privacy forces a room-shadow refresh, so rendering the privacy scene cannot consume the last room update. The rate helper is checked at 30/60 Hz and does not request updates for stationary doors. This supersedes the earlier moving-door shadow lag noted above.

The live localhost visitor walked downstairs and approached the front door: the door refresh-request counter went from 0 to 8 during opening, then to 17 during closing and remained at 17 afterward. The room displayed about 47 fps on this Mac. Ten HomeWorld tests, the bake-shape guard and shadow refresh checks passed. Proof: `docs/screens/home/private-lounge-lighting-v3.jpg`. This is browser-room evidence; reference-level Unreal fidelity and physical-phone performance remain open checks.


## Device persistence and clean local restart

An operator-controlled integration check woke the main simulation through the existing authenticated wake endpoint and suggested Minecraft. Hunger took priority first. At the current nighttime hour, the desk/game gate gives console play no score, so this check does not establish a new live Minecraft session; a separate daytime integration run remains needed. The wake was an operator intervention, not a spontaneous brain decision.

The operator wrote `/root/sub01-home-check.txt` inside the real v86 Linux guest and read it after graceful server restarts. Its original text survived and the actual Linux panel showed the recovered file. The file lives only in the guest snapshot, not a host mount. Raw before/after data is under ignored `data/home-device-check/`; proof is `docs/screens/home/private-linux-file-restored.jpg`.

The first restart surfaced an address-in-use failure. The local launcher now waits up to eight seconds for a prior listener to release its port and reports a clear bounded failure if another server retains it. The server now always closes its sites/viewer sockets and cleans up its HTTP runner, including startup failures after runner setup. Viewer closure and request shutdown are bounded. On a live shutdown with the corrected code, port 8798 was immediately bindable; the following startup returned HTTP and a ready guest, and the file was read again. Fifteen targeted lifecycle, port, world and device API checks passed. The running local brain restored 510,000 neurons and its saved learned decisions.

## Isolated daytime Minecraft integration check

The private launcher now supports distinct loopback Minecraft server/viewer ports through SUB01_MC_SERVER_PORT and SUB01_MC_VIEW_PORT. Defaults remain 25569/8803; the declared daytime fixture uses 25570/8805 with HTTP 8804 and separate data. Invalid/equal privileged ports are rejected; server.properties must still bind to 127.0.0.1 and the selected port. `scripts/prepare_home_daytime_check.py` refuses existing destinations and copies learned/grown brain state without modifying the main data directory. Its test verifies the valid legacy Life console place and port isolation.

The real fixture was started at Tokyo 13:00 with a fed body and an operator-initialized console activity, explicitly labeled DAYTIME DEVICE TEST in the browser. This tests the integration, not spontaneous choice of the console. The full cortical/spiking runtime reported 510,000 neurons and 51,497,139 synapses. Actual Minecraft frames appeared on the room TV and game panel, with collected oak/birch logs and soil, successful resource actions, and recorded feedback. The room displayed about 47 fps on this Mac at the first TV view; this is not a phone benchmark.

The UI rejected an unauthenticated game change. After local operator authentication, selecting Chess paused Minecraft and disconnected its player. Selecting Minecraft reconnected to the same world with inventory retained. A final switch to Chess again returned active=false, connected=false, busy=false. The isolated process then handled SIGTERM, saved state, and exited 0. The main localhost house remained separate on 8798. Life labels now say a game rather than incorrectly naming Pong when another game is selected.

Proofs: `docs/screens/home/private-minecraft-daytime-tv.jpg` and `private-minecraft-daytime-panel.jpg`. Eighteen targeted fixture/Minecraft/home-world/API tests passed; the real-player spatial regression and worker syntax checks passed. Open game limitations observed in this run: some block placements had no valid destination or were refused by the server, and some wood approaches timed out. These failures remain recorded feedback, not successful construction. Hostile encounter behavior and broader visual/performance targets are still unproven.

## Minecraft placement uses the actual surrounding world

The player previously always tried the cell east of its feet, even when that cell was occupied, unsupported, or intersected its body. Placement now scans nearby loaded cells at up to two horizontal blocks and one vertical block from the feet. It requires an empty cell, a full solid block underneath, a visible support, bounded eye-to-face reach, and no overlap with the player's 0.6 m wide / 1.8 m high volume. A generation check after equipping prevents initiating placement after the console is put away. This is a primitive block-building behavior, not a general planner.

Focused spatial checks cover occupied eastern cells, missing chunks, air without support, hidden support, and fractional player positions crossing a neighboring cell. Worker syntax and five Minecraft Python checks passed. The existing isolated daytime fixture was restarted with the full 510,000-neuron runtime and its persistent world; no main data was changed. Six placement completions with reward 0.2 were recorded in the real worker between timestamps 1791828446 and 1791828507, with visible blocks on the TV. This is a successful live integration sample, not a guarantee that every future placement succeeds. Proof: `docs/screens/home/private-minecraft-building.jpg`. Resource approach timeouts remain observed and require a separate reach/path improvement.

## Minecraft resource reach and approach

Resource collection previously always requested a 3D path to the log's Y coordinate, then measured reach from the feet. Elevated visible logs already within the official Mineflayer eye-height digging reach could therefore cause needless path timeouts. The worker now prioritizes visible reachable logs, uses `canDigBlock` and `canSeeBlock`, and skips walking when collection is already possible. Otherwise, resource approach uses GoalNearXZ; it still must find a real safe path, and collection rechecks reach, visibility, unchanged resource type and supporting-ground protection afterward. Putting away the console during the approach cancels collection.

The focused asynchronous resource regression covers skipping approach for a reachable elevated log, horizontal-only approach for a remote log, cancellation during movement, occlusion, changed blocks and ground support. Both Minecraft JS regression suites, worker syntax and seventeen Minecraft/HomeWorld/API Python checks passed. The full-brain isolated daytime fixture was restarted against its persistent world. In the observed live sample beginning at 1791828681.518115, the actual worker recorded eight mine_wood completions, six explore completions and four place_block completions with four item-collection events and no failure in that bounded sample. This does not prove every terrain/path is solved. The TV panel showed live play, inventory and health/food, at about 46 fps on this Mac. Proof: `docs/screens/home/private-minecraft-resources.jpg`. The isolated test was stopped gracefully with state saved, leaving the main house on 8798. Broad visual fidelity, physical-phone performance and hostile encounter verification remain open.

## Interior finishes and physically lit artwork

The original framed print planes used an unlit MeshBasicMaterial, so they stayed bright when lamps were switched off. They now use rough nonmetallic MeshStandardMaterial and receive shadows. The actual private bedroom was checked from the same visitor position with lights on and off, then the lamp setting was restored on. Proofs: `docs/screens/home/private-bedroom-finishes.jpg` and `private-bedroom-lights-off.jpg`.

Original narrow two-part baseboards now finish the existing ground-floor/loft wall faces, with the entrance and bathroom openings left clear. Twenty pieces are one instanced draw call, without additional textures, runtime simulation or lighting passes. They do not change the existing room colliders and are not part of the precomputed indirect bake. The runtime diagnostic reported interiorTrim=20 and all 71 prior indirect receivers applied. About 46–48 fps was observed on this Mac in the bedroom; broader device performance remains unproven. JS syntax and diff checks passed. The sleeping pillows still appear angular/upright in this view and require a separate geometry/orientation correction; this view is not claimed as reference-quality completion.

## Scanned sleeping pillows aligned to the mattress

The previous cushion reused the inclined pillow01 scan and estimated thickness from axis-aligned bounds. Its imported quaternion pose also survived assigning Euler angles, producing pointed upright geometry. Sleeping pillows now use the pillow02 CC0 scan, a right-handed principal-axis alignment and explicitly reset XYZ rotation mode. Their thickness is vertical, 15 cm, with a 5 mm lowest-point clearance above the mattress. Imported custom split normals are cleared after geometry alignment. The main bedding builder uses the same alignment helper for future rebuilds.

The one-time repair tool replaces only pillow nodes/accessors in the existing GLBs, preserving the existing cloth vertices and faces exactly instead of re-exporting all cloth. Both full and lite variants were checked for finite geometry, dimensions, mattress clearance, unchanged cloth and matching manifest hashes. Sizes are about 1.7 MB / 0.77 MB; backups remain ignored under out/pillow-before. Python/JS syntax and diff checks passed.

The real localhost camera loaded physical bedding and showed the pillows flat from the previous bedroom angle, with about 47 fps on this Mac. The lighting importer applied 69 unchanged parts and correctly rejected the two changed pillow shapes; their indirect light remains a fallback until a fresh bake, so contact/indirect lighting still needs work. Proof: `docs/screens/home/private-bedroom-pillows-aligned.jpg`. This corrects pose and geometry, not the broader reference-fidelity or physical-phone completion gates.

## Editable Blender scene and current indirect light v4

`tools/prepare_home_blender.py` creates a packed, metric editable Blender scene from the actual localhost GLB export, with a bedroom comparison camera and reference notes. The generated project is `out/home-editable/sub01-home.blend` (about 61 MB), intentionally ignored and private. This is an editing starting point; the browser implementation remains authoritative until modeled furniture is exported and integrated. The selected modern oak-bed reference is https://www.muji.eu/products/double-platform-bed-frame-oak-18913 ; no manufacturer geometry is included or claimed.

A fresh Cycles CPU day/night indirect bake from the current scene includes aligned pillows, physically lit print surfaces and the baseboard occluders. The atlas has 74 receivers at 900×1234, 32 samples and four diffuse bounces. Both packers confirmed finite nonnegative nonempty light values; installed file sizes/hashes were checked against the manifest, with rollback copies retained under ignored out/lighting-v4/previous. Cache versions were updated for the geometry and HDR maps together.

The main localhost bedroom loaded physical bedding with 73 matched indirect receivers and about 47–48 fps on this Mac. One atlas receiver did not match and remains fallback; its identity still needs investigation. Therefore this is not claimed as all-receiver completion or reference-level fidelity. Proof: `docs/screens/home/private-bedroom-lighting-v4.jpg`. The bake-shape regression and JS/diff checks passed. Physical-phone performance and the next reference-based furniture replacement remain open.

## Reference-built Blender oak bed integrated in the actual house

`tools/build_home_bed.py` models an original adapted oak platform bed in Blender using the MUJI oak platform-bed page and photographs as a construction/style reference (https://www.muji.eu/products/double-platform-bed-frame-oak-18913). The manufacturer lists a 147×202×5.5 cm double platform; our 170×222 cm frame is adapted to the existing mattress/collision envelope, not claimed as an exact product replica or supplied manufacturer CAD. It has beveled rails, fourteen slats, four cylindrical legs, a central support, posts and an oak headboard. The packed editable source is `web/house/assets/bed/bed.blend`, alongside the original-geometry GLB and dimensions/source/hash metadata. Existing CC0 scanned wood maps are reused with a browser albedo grade toward light oak; that grade is preserved when indirect lighting is assigned.

The browser loads the roughly 340 KB joined frame as one oak mesh, hides the two old block-shaped frame/headboard fallbacks, retains the existing mattress and cloth, and waits for the bed before exporting/baking. A load failure leaves the previous geometry usable. Geometry checks proved finite vertices, dimensions inside the unchanged 1.75×2.3 m bed collider and floor-to-headboard height under .951 m. Manifest hash validation and ten HomeWorld tests passed, plus Python/JS/diff checks.

Actual localhost visitor movement stayed beside the bed at x≈−1.2 and eye height 4.65, moving from z≈−3.22 to −1.55 without entering its collider. The runtime reported bedFrame=blender-oak and about 46–48 fps on this Mac. Proof: `docs/screens/home/private-blender-oak-bed.jpg`. Seventy-one unchanged indirect parts still apply; the new frame uses runtime/environment lighting and needs a fresh indirect bake. The separate generated whole-house Blender export still predates this furniture replacement and will need regenerating when the furniture pass is settled. Physical-phone performance and reference-level fidelity are still open.

## Correct bounds for rotated light-bake receivers

The remaining pillow rejection came from rotating its local axis-aligned bounding box, which expands the bounds beyond the actual rotated scanned surface. The bake matcher now caches bounds from transformed vertices, together with the existing exact point-cloud check. This restores valid lighting without weakening shape validation or rerunning Cycles. Local-only diagnostics now list rejected bake IDs/reasons.

The actual localhost full room applied 72 receivers (previously 71 after the bed replacement); Pillow_1 is no longer rejected. Only the two obsolete static batches changed by the new bed remain rejected, as expected until the furniture-pass bake. Existing shape-guard checks, JS syntax and diff checks passed. Proof: `docs/screens/home/private-bedroom-rotated-bake-fixed.jpg`. Subsequent furniture changes should be grouped before recalculating light rather than baking after every small edit.

## Grouped bedroom furniture and lighting pass

The bedroom now uses the CC0 Poly Haven side_table_01 scan (https://polyhaven.com/a/side_table_01) at 50 cm height, instead of a solid block. Downloaded source files were MD5-verified and recorded with SHA-256/source/license in the asset manifest. Its measured fitted width/depth are approximately .499/.409 m; a .51/.42 m visitor collider covers it. The new Blender bedside lamp has a brass base/stem/socket, bulb and open double-sided linen shade; original editable source, geometry and hash metadata are in assets/bedside-lamp. Its GLB is about 78 KB. Materials reuse the existing linen/brass maps. The oak frame now clones/shares existing wood textures instead of uploading a duplicate set.

The lamp replaces its placeholder in the existing interaction list. Switched emissive materials, including clones receiving lightmaps, now follow lamp state. The light is positioned at the new bulb height and reduced to 3.5 intensity to avoid overexposing the nearer tabletop. On the actual full localhost room, lights-off produced bedsideEmission=0 with the bulb/room dark, and lights were restored on. No captured warning/error was returned. Source/lightmap loading waits for the bedroom models before applying or exporting.

One combined 80-receiver 975×1234 Cycles day/night bake includes the bed frame, nightstand and lamp. The shared home_material_grades.py helper applies the same light-oak power/tint grade in both the baker and editable Blender scene. Both bakes logged one graded oak material and BAKE_DONE; their packers validated finite nonnegative/nonempty data and installed hashes/sizes match the manifest. The generated whole-home Blender editor file was refreshed and logs successful save plus the same grade. The actual full renderer applied all 80 receivers with rejectedBakes=[] at about 46–47 fps on this Mac. Proofs: private-bedroom-furniture-pass.jpg and private-bedroom-furniture-lights-off.jpg under docs/screens/home.

A 390×844 desktop-browser lite check loaded the scanned nightstand, Blender lamp/frame, physical-lite bedding and indirect-only shadows; the English phone home panel fit the viewport. New table texture variants were verified at <=512 px. This is viewport/render evidence, not a physical-phone benchmark. The general lite builder now skips lighting assets handled by the dedicated lightmap packer; unused generated copies were preserved outside shipped assets. Twelve HomeWorld/API tests plus bake-shape/view-control JS checks and Python/JS/diff checks passed. Overall reference-level visual fidelity, actual phone-device performance and remaining whole-house completion gates stay open.

## Named game impulses and confirmed delivery

Phone impulses now recognize explicit Pong/Minecraft requests instead of treating "play Minecraft" as music or leaving a Pong request on the previously selected game. The request adds a short-lived preference only: activity remains unchanged on receipt. When the life controller starts a console session, an available nonexpired request is accepted and HomeWorld consumes it once. The consumed choice persists across restart, so it cannot undo a subsequent operator game change. Operator selection clears queued/accepted preferences only after authorization. Unconfigured Minecraft requests are ignored; game soundtracks still route to music. Pending preferences expire after one simulated hour and appear on the phone home screen as a suggestion awaiting his decision.

The impulse form now waits for chat_ack: rejection, timeout or disconnect retain the text; acceptance clears only the submitted text and displays confirmed receipt. A full-runtime restart preserved the private state and restored 510,000 neurons, 51,497,387 synapses and 176 learned decisions. In the real Chrome phone UI an empty impulse was rejected; "play Minecraft" received a positive acknowledgement and appeared as pending while the character continued using his phone. This verifies receipt/preference, not spontaneous gameplay in the nighttime main instance. Proofs: private-impulse-rejected.jpg and private-console-suggestion-pending.jpg in docs/screens/home.

Eighty-three targeted console/Minecraft/HomeWorld/API/music/day-routine tests passed. Further targeted checks cover preference serialization, authorized operator override and HTTP lifecycle; Python/JS/diff checks passed. The source and main runtime remain private/localhost. Whole-house visual fidelity and physical-device completion gates remain open.

### House arrival synchronization — 2026-10-12

Browser screens, Wikipedia fallback, chess turns, activity music and chat replies now wait for the actual HomeWorld destination. The legacy room route finishing early no longer permits a device activity while the first-person actor is still crossing the house. Background music remains allowed during walking. Activity durations still use the legacy Life clock; this change gates device execution, not that clock. The correction is saved in the private repository and requires restarting the local server to load it.

Validation: 93 tests passed across home arrival routes (bedroom/desk in both directions), screens, music and HomeWorld. No public service or deployment changed.
