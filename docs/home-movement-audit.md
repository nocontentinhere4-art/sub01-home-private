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

## Remaining concrete balcony gate

The upper front window is built at `(-2, 4.45, 3.85)` with a centre mullion at `x=-2`. Evaluating the actual source `floorAt`/`canWalk` with the registered numeric furniture blockers allows a visitor at upper-floor feet height 3 to move through `x=-2, z=3.8→4.05`. That crosses the visible solid centre mullion at `z=3.85`. The balcony currently has no explicit doorway opening or collision rule restricting passage through that facade.

The backend balcony waypoint at `x=-2.2` avoids the post, but that does not prevent the visitor collision. A follow-up should define a real balcony doorway and restrict visitor passage to that opening, with the same opening represented in the model and routing tests. This is a structural change to verify together with its lighting bake, rather than silently claiming that all collisions are solved.
