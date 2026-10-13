# Private SUB-01 home — Codex / Claude coordination

Updated 2026-10-13. This file describes the new private home; the inherited docs/HANDOFF.md describes the older public room and is not the current deployment plan.

## Goal and boundaries

Build the real functioning first-person home, not a promotional video. Primary reference: https://x.com/SimbasJungles/status/2109095401273938072. Ground-floor entrance, wooden stairs/loft, bathroom privacy, actual PC/phone/TV interactions and eventual brain-controlled activities. English UI. Keep the fictional character separate from the MRI donor; do not claim consciousness.

Everything remains private. No public deployment, Railway change or edits to subzerone.live/city.subzerone.live. Heavy work belongs on the existing authorized Runpod server, not the owner's overheating Mac. No additional paid pods. Budget maximum $10; existing automatic stop deadline 2026-10-13 18:16 UTC (20:16 Europe/Rome). Do not extend it. Do not touch the separate brain pod. Credentials stay out of Git and issue comments.

## Ownership

Codex owns Blender assembly, Unreal/native module, server execution, budget guard, first-person rig/contact verification and integration. Current local changes include home.js body hooks; do not overwrite them from an older cloud checkout.

Claude owns its separate browser camera-effects module/performance review and can propose PC/phone/TV interaction bridge improvements. Work on a separate branch and report exact modified paths, commits, tests and remaining limitations in the private coordination issue. Coordinate any home.js edits before integration. Do not substitute recorded video for working devices. Subtle camera effects must preserve physical lighting and readable interfaces.

Codex integrates reviewed commits. Neither agent merges over the other's uncommitted work. Use the private issue for handoffs and PRs for code review; distinguish proposals from results actually executed and verified.

## Actual verified state

- Private origin: nocontentinhere4-art/sub01-home-private; previous baseline main 5fe413e.
- Official Unreal 5.8.3 downloaded/extracted on Runpod; Blender 4.0.2 installed there.
- Full house assembled into /workspace/sub01-home-private/assembled/house.blend and house.glb, with actual queen bed, espresso machine and photographed coffee table.
- Native Unreal module compiled successfully after FPoseLink SetLinkNode correction. Timed actual-player screenshot code subsequently compiled successfully.
- ActualHome map imported and saved in Unreal: 233 placed mesh components, zero imported lights. Authored browser sun/fixtures must therefore be installed explicitly by setup, using the exact source recipe.
- Current setup/collision/camera and first actual runtime render remain in progress. No accepted runtime screenshot or browser-streaming proof yet.
- Correct ReferenceT rig uses original node reference pose; a different inverse-bind pose is not automatically a defect. Canonical-A derivatives are not accepted. Typing/walking/texting clips remain disabled until actual contact and first-person visual checks pass. No verified mouse capture.
- Blender scene captures are geometry/material evidence only, not proof of Unreal navigation or working devices.

## Evidence required before calling it ready

Actual runtime screenshots; physical routes through stairs/doors without clipping; camera/hand/contact checks; real device actions with privacy; brain activity wired to those actions; private browser streaming and acceptable frame time. Passing an importer or producing a pretty render alone does not complete the goal.
