# First-person movement audit

Read-only audit during the cabinet/table lighting bake. No main actor state, rendering geometry or route state was changed by this audit.

## Verified checks

- `home_walk_check.mjs`: visitor acceleration/braking are bounded, diagonal speed is normalized, and 30/60 fps trajectories agree within the defined tolerance.
- `terrace_space_check.mjs`: the ground-floor entrance throat stays narrow around the door frame; the wider terrace is walkable inside its rail limits.
- 22 Python HomeWorld/arrival/settled-device checks passed. They cover waypoint edges against registered furniture blockers, safe ground routes around the staircase, continuous server movement, getting up before walking, persisted in-flight routes, bathroom privacy and device activation after completed seating.

These checks do not establish collision safety against every rendered mesh. In particular, waypoint tests sample registered static blockers, not arbitrary window/door mesh geometry.

## Corrected Explore regression

Repeated presses of Explore previously recreated a stand-up target at SUB-01's current seat even when the visitor was already exploring elsewhere. The unconstrained stand-up interpolation then returned the visitor directly through the house instead of following walkable surfaces.

The Explore handler is now idempotent while already exploring. The isolated handler regression test verifies that the first Follow→Explore action still starts a natural stand-up transition, while repeated Explore presses preserve a visitor on the entrance terrace even if SUB-01 is seated upstairs. Root performs the actual browser check.

Follow itself remains a viewing-mode switch: it interpolates the visitor camera back to SUB-01's first-person viewpoint. That transition is not a collision-checked physical journey and must not be presented as walking through the house. Actual actor movement and visitor walking are separate operations.

## Balcony gate found in the audit

The upper front window is built at `(-2, 4.45, 3.85)` with a centre mullion at `x=-2`. Evaluating the actual source `floorAt`/`canWalk` with the registered numeric furniture blockers allows a visitor at upper-floor feet height 3 to move through `x=-2, z=3.8→4.05`. That crosses the visible solid centre mullion at `z=3.85`. The balcony currently has no explicit doorway opening or collision rule restricting passage through that facade.

The backend balcony waypoint at `x=-2.2` avoided the post, but did not prevent the visitor collision.

The follow-up implementation replaces the fixed centre post with a 1.05-metre sliding doorway centred at `x=-2.2`. Fixed sidelight frames stay solid; the collision gate checks the actual moving leaf edge and the same 16-centimetre visitor clearance used by existing furniture blockers. Visitor or actor approach opens the leaf at a bounded sliding speed with acceleration/braking. Runtime door motion refreshes cached shadows. The gate applies only to the upper facade, preserving the ground-floor entrance.

`balcony_access_check.mjs` verifies the actual visitor `canWalk` function, closed/fixed glass rejection, usable open doorway, partial-opening clearance and the actual Python HomeWorld bed→balcony→desk route against door openness over time, including a conservative held 5 Hz actor feed. A GLB export/import round trip retains all eight fixed frame pieces while excluding the dynamic leaf from static bake geometry. The same isolated 3,124-byte static-frame GLB was imported by the actual Blender 4.2.23 runtime: eight mesh objects, no sliding leaf, `BALCONY_STATIC_BLENDER_IMPORT_OK`, exit 0. The export uses a shallow-resource scene clone, without moving or hiding the real door. Actual browser crossing, final lighting and view quality remain root verification gates.

Root subsequently verified actual Chrome crossing at visitor `[-2.1608,4.65,4.562]` with the leaf fully open, and a return inside. A fixed sidelight approach at `x=-.317` stopped at `z=3.584` with the leaf closed. The house-only photograph wrapper now masks glass tint/refraction/drop highlights and reflections only in the physically cleared doorway; the outside photograph and falling rain remain visible. Its mask follows the actual leaf openness and does not affect ordinary panes.

## Remaining exterior continuity

The balcony crossing exposed a significant visual mismatch: the photographed neighbourhood visible from inside is replaced by the existing generic, untextured box city outside. Successful physical crossing does not establish visual realism. The next exterior pass should reuse the same facade origins, textures, world-ray/depth projection and weather phases in lightweight exterior backdrops, with no glass overlays, so the balcony and entrance terrace remain coherent with their window views. This is a finite local exterior treatment, not a claim of a complete explorable city.

## Current follow-up evidence — 2026-10-13

Front hinged and bathroom sliding leaves now gate the actual visitor collision function with body clearance; both actor and visitor proximity open them. Dedicated harnesses include actual Python HomeWorld desk→park→desk and bed→bathroom→desk routes with a conservative held5Hz actor feed. Repeated current checks pass for bounded30/60fps walking, terrace boundaries and allthree door gates. These still do not prove collision safety against every arbitrary rendered furniture triangle.

Exterior no longer changes to the generic boxcity at the door: inside/outside share one attributed historical spherical residential Tokyo photograph, with nearby geometric pavement/gate. Distant street/buildings remain static photographic content; no complete freely explorable exterior world is claimed. Current visual audit found excessive60×60m near paving masking the image ground; the next bounded courtyard pass addresses it separately from movement bounds.

Fresh Phone-panel-open→bathroom-entry runtime acceptance captured actualwholeviewOCCUPIED, emptyhiddenpanel, zeroeditablecontrols and hidden device actions. Controlled bladder/nudge initialization applies only to isolatedQA; it does not demonstrate spontaneous need decisions, existing typed draft preservation, or held-key release. See docs/inhabited-home.md and private-bathroom-panel-censored.jpg for exact evidence.
