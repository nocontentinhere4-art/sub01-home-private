# Native renderer handoff — 13 October 2026

The current generated UE 5.8.3 native module compiled successfully on the authorized A40 server. The final incremental build took 237.80 seconds. This verifies compilation, **not first-person animation or house acceptance**.

The final run reached `SUB01_NATIVE_INIT_BEGIN` and `ASSETS_DONE` at 21:43:30 UTC, then `POSE_DONE` and `PC_DONE` at 21:43:45. No `SUB01_FIRST_ACTUAL_GAME_TICK`, new viewport PNG, or five-second recording was observed before the mandatory 21:45 stop. Both home pods were confirmed stopped at 21:45:25. The post-initialization first game tick/frame remains unresolved. Do not describe these changes as a finished, autonomous or visually accepted native house.

Implemented and compiled:

- Full-body Walk/Phone mesh attachment follows capsule yaw instead of camera pitch. Looking down no longer rotates the configured body origin through the floor. Genuine animation remains velocity driven; the existing controlled desk diagnostic keeps its world anchor.
- The opt-in live consumer authenticates to the validated loopback `8821/home/state` bridge. It plans through the actual home graph from the native node, moves using CharacterMovement input, and stops on stale state, bathroom privacy or blocked progress. It does not teleport the actor or change backend activity. Dynamic native doors, seated actions and held-phone placement are not accepted.
- Explicit private runtime controls can switch the controlled desk view to the physical entry pawn and request a real GameViewport screenshot. This switch is logged as a view-mode switch, not navigation. Its file is confined to the private rootfs directory; no arbitrary console or position commands are supported.
- Recording uses fresh output folders, real wall-clock frame durations, a separate warm tick rate and a keepalive option. It does not turn screenshot encoding throughput into a gameplay FPS claim. Credentials are read from the protected operator file into the environment, never command-line arguments.

The existing continuous 301-sample typing arm profile and its earlier 120 Hz audit are unchanged. The correction preserves captured finger motion and uses a conservative plane including key gaps; it is not whole-hand, bevel or side-contact acceptance. Finger aesthetics, genuine phone grip, live native action sequencing and the new video remain unverified.

Three live-consumer/generator checks, two full-body attachment regressions and four existing hands-binding checks pass locally. The compiled native controls have not received runtime acceptance.

The audit found a CPU quota of approximately 7.65 cores despite 96 visible CPUs, significant CPU throttling and host CPU pressure. Virtual `Committed_AS` was not evidence of RAM exhaustion: the memory audit found no OOM kills and mostly reclaimable file cache. Slow editor/module/derived-data initialization was observed, but no final root cause for the missing first tick was established.

Next acceptance should locate the precise post-BeginPlay stall, obtain one actual viewport frame, then verify genuine animation advancement and live physical route/privately censored device behavior. Preserve the actual timing/profile evidence; do not replace it with a cinematic or manually posed substitute.

Source-only follow-up after the stopped compute window adds an independent engine-frame hook, a game-world tick hook, explicit input-mode entry and final BeginPlay-return markers. These additions have not been compiled or run yet. They distinguish a constructor/initialization delay from an actor tick issue without changing focus or rendering behavior. The launcher now uses an explicit driver/display/loader environment allowlist plus the protected operator token; the new environment helper must accompany the launcher on the server.

The last compiled `PC_DONE` marker followed both PC configuration and the guarded live-consumer initialization, but preceded route-test initialization, player input-mode setup and the return from BeginPlay. Therefore that marker alone did not prove BeginPlay finished. Input-mode setup or subsequent engine initialization are candidates to instrument, not diagnosed causes.

The follow-up marker CPP compiled on the resumed A40 in 33.8 seconds (two actions). Actual UE5.8.3 source confirms `-ZenDataPath` / `UE-ZenDataPath` support (ZenServerInterface.cpp1018–1025/1059–1065); BaseEngine.ini confirms `UE-LocalDataCachePath`. The launcher now explicitly points both nonsecret caches into persistent `/workspace/sub01-unreal/cache`, with a successful write test as unreal. Engine-selected Zen readiness remains a runtime log check, not inferred from configuration.
