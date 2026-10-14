# Native seat transition: integration proposal (not applied)

Module: `tools/native_seating/Sub01SeatTransition.h`, which is engine-free and compiled by
`tests/test_native_seat_transition.py`. It adds a typed, fail-closed seat state that follows
the real CharacterMovement capsule and the captured owner clips. It never moves the
capsule while a sit clip plays, never places the actor, and never reports contact on its
own. No runtime generator, bridge or staging file is changed by this commit.

## Evidence it uses

| Fact | Source | Value |
|---|---|---|
| StandToSit duration, hips travel | `inventory_native_seating.py` on `room_mx_stand_to_sit.glb` (unchanged 65-bone owner) | 2.233 s; hips 37.857 cm back and 16.3 cm down |
| SitToStand duration, hips travel | `room_mx_sit_to_stand.glb` | 2.067 s; hips 35.113 cm forward |
| Cushion | `unreal_chair_surface_audit.py` → `private-audit/native-chair-surface.json` | measured triangles and bounds, one component, no errors |
| Seat contact | `unreal_audit_seat_contact.py` → `native-seat-contact.json` (+ `native-seat-correction.json`) | per-patch, two-sided, probe only |

The tests tie the header constants to the inventory. With the authored cushion centre
(200, −190) and seated heading −90°, the clip-derived approach point is (200, −227.86). That
is within 4.5 cm of the reviewed diagnostic anchor (−232.3), which cross-checks it. The real
value must come from the measured cushion, not from these numbers.

## Phases (`ESub01SeatPhase`)

`Standing` → `Aligning` (turn in place, no translation) → `SittingDown` (StandToSit,
movement input off) → `Seated` (Sitting loop) → `StandingUp` (SitToStand, movement input
off) → `Standing`. When the seat is wanted but cannot be taken, the phase is `Refused`,
with one of these reasons: `ChairUnmeasured`, `Private`, `Stale`, `Blocked`,
`ClipUnavailable`.

- **Interrupted while sitting down** by a command change: it stands up from the matching
  point of the captured get-up (`ClipStartSeconds = (1 − sit progress) × 2.067 s`).
- **Command change while seated**: it plays the full get-up. Movement returns only when the
  get-up ends. A new seat command during a get-up re-sits afterwards, through the clips.
- **Sit clip never starts** (0.5 s): the body never moved, so the machine returns to
  `Refused`/`ClipUnavailable`, movement is allowed, and it won't retry for that command.
- **Get-up clip never starts**: movement stays off, because a seated body must not glide.
- **Privacy or a stale command while seated**: the body stays seated, focus is off and
  nothing moves.
- **Contact**: `ContactVerified` only in `Seated`, from a fresh in-band receipt (≤ 3 s) for
  the current command. `PCFocusAllowed` additionally requires public and fresh state.

## Hook points (for the runtime owner to apply)

1. **`tools/unreal_live_home_runtime.py`, `UpdateLiveHome`**, after the path is empty at
   `desk`:
   - add one final approach leg to `Sub01SeatApproachPoint(cushion centre, seated yaw)`,
     with the same `AddMovementInput` and the 12 cm / 20 cm floor arrival gate. Read the
     cushion centre from the chair report, not a constant;
   - every tick, fill `FSub01SeatInputs` from the existing fields: `LiveHomeCommandSequence`
     plus the activity as `Command`, `LiveHomeFresh`, `LiveHomePrivate`, `LiveHomeBlocked`;
   - when `MovementInput` is false, skip `AddMovementInput` and call
     `StopMovementImmediately()`;
   - when `TurnInPlace` is true, apply only the bounded yaw from
     `tools/first_person_yaw.py` (already integrated).
2. **`tools/unreal_home_hands_runtime.py`**: add roles `StandToSit`, `Sitting` and
   `SitToStand` bound to `/Game/Sub01Hands/Seating/SUB01_<role>` (from
   `unreal_import_seating_fbx.py`, same USkeleton).
   - Start them at `ClipStartSeconds`.
   - Report the instance's accumulated time as `ClipSeconds`, and `ClipPlaying` only when the
     playing sequence is the requested one.
   - The mesh stays attached to the capsule, and the in-place hips travel carries the body
     onto the seat.
3. **Receipt**: `ReceiptInBand = Sub01SeatPoseMatchesAudit(evidence, capsule X/Y, yaw,
   Sitting playing)`.
   - `FSub01SeatEvidence.AuditInBand` comes from an accepted `native-seat-contact.json` for
     that exact anchor and heading. The renderer supplies it as a measured report, not a
     flag.
   - `ReceiptCommand` is the current command, and `ReceiptAgeSeconds` is the time since the
     check last passed.
4. **`NativeSeatVerified = Out.ContactVerified`**. This is the only assignment. The existing
   sender then reports `seated` with `chair=desk_chair`. The existing `NativeFeedbackSeatReady`
   ACK lease and `NativePCCommand` guard keep PC focus off until the backend acknowledges.
   `Out.PCFocusAllowed` is an additional local condition, not a replacement.

## Not claimed

The module is not applied, and nothing here is native runtime evidence. Seat contact stays
unverified until the measured report and a runtime pose match both exist. Not covered here:
the backrest (watch mode), clearance for the thighs under the desk, the chair frame, and
the visual blend quality between Walk and StandToSit.
