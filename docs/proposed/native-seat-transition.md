# Native seat transition: implementation and how to apply it

Files owned by this work:
- `tools/native_seating/Sub01SeatTransition.h`: an engine-free state machine and receipt rules.
- `tools/unreal_seat_transition_runtime.py`: the evidence builder, the C++ adapter and
  `install()`.
- Tests: `tests/test_native_seat_transition.py`, `tests/test_unreal_seat_transition_runtime.py`.

No runtime generator, bridge or staging file is edited. `install()` is applied by the runtime
owner to already staged sources, after the renderer's measured reports exist. Without it, the
live home is unchanged.

## Apply (server, after the measured reports)

```
# 1. measured inputs (server editor)
unreal_chair_surface_audit.py     -> private-audit/native-chair-surface.json
unreal_audit_seat_contact.py      -> private-audit/native-seat-contact.json (+ native-seat-correction.json)
# 2. evidence (any Python; refuses unless the contact report is accepted)
python tools/unreal_seat_transition_runtime.py <UE project dir>   -> private-audit/native-seat-evidence.json
# 3. after stage_unreal_home_runtime.stage(project):
python -c "import sys;sys.path.insert(0,'tools');import unreal_seat_transition_runtime as a;a.install_module('<project>/Source/Sub01HomeLab')"
```

The seating clips must already be imported to `/Game/Sub01Hands/Seating/SUB01_{StandToSit,Sitting,SitToType,SitToStand}`
by `unreal_import_seating_fbx.py`, on the same owner USkeleton. A missing role makes the
machine refuse to sit, or keeps him seated without the PC.

If the contact report is out of band, there is no evidence file. Sitting still works from the
measured cushion alone (approach = cushion centre + the captured hips travel of 37.857 cm), but
`ContactVerified`, `NativeSeatVerified` and PC focus stay false. Apply the proposal in
`native-seat-correction.json`, re-measure, and rebuild the evidence.

## Integration prerequisites (exact)

Everything below is source or server-side data; no step here was run.

1. **Floor:** the offline seat audit must use the measured collision floor (2.5001 cm), not
   `FLOOR_CM = 0.0`. The renderer is correcting this. The live measurement does not depend on
   it, because it uses `CharacterMovement->CurrentFloor` (the walkable floor actually under the
   capsule).
2. **Chair report:** `private-audit/native-chair-surface.json` needs `errors: []` and the
   cushion's `sections[].vertices_world_cm` plus `cushion_surface.triangle_indices`, from the
   real chair triangles. Its exact text is the chair revision, so re-measuring invalidates all
   evidence.
3. **Placement corrections first:** apply the renderer's relative chair, body and keyboard
   correction (from the measured seat geometry and the ~1 cm right-hand reach deficit). Then
   re-run in this order:
   - `unreal_audit_seat_contact.py`;
   - `tools/unreal_seat_transition_runtime.py <project>` (evidence);
   - the keyboard skinned-contact audit, which writes the contact profile's `body_cm`/`body_yaw`.
4. **Same body transform:** the seat evidence `body_cm`/`body_rotation_pyr` and the contact
   profile's `body_cm`/`body_yaw` must describe the same body transform. The arm profile is
   applied only while the live body is at the profile's transform, within 0.05 cm and 0.05°.
   Away from it, the raw DeskTyping clip plays, with no arm override.
5. **Body attachment:** the live seat uses the capsule-attached rendered body (Walk attachment,
   `WalkMeshOffset`, `HandsMeshRotation`). It never uses the camera-attached `DeskMeshOffset`
   posture or the diagnostic `SetWorldLocationAndRotation`. `SeatLiveBody` refuses any other
   attachment, so with it there is no transform and no receipt.
6. **Editor build:** the live measurement calls `AnalyzeCapturedSeatSkin`, which is
   `WITH_EDITOR` only because it reads the imported model. The private live home runs on the
   editor binary. In a packaged build it returns an error, and contact stays unverified.
7. **Staging:** apply `install_module()` after `stage_unreal_home_runtime.stage()`, the
   contact-profile runtime and the skin-contact native module. The anchors must be unique; a
   missing anchor refuses the whole install.

## Arrival and receipts

- **Walking:** CharacterMovement input brings the capsule to within 12 cm of the approach
  point. The 12 cm gate only starts Aligning; it authorizes nothing.
- **Aligning, with an audited anchor:**
  - The view turns at up to 103°/s toward the audited body heading, measured on the rendered
    body.
  - The rendered body settles horizontally toward the audited body XY:
    `MoveUpdatedComponent` with a sweep, at most 0.25 cm and 15 cm/s per tick, 15 cm in total,
    and no Z change.
  - A blocking or penetrating hit ends the settle. There is no depenetration and no sliding.
  - It sits once the body is within 0.05 cm and 0.05°: a precise arrival.
  - A blocked settle, or one past 3 s, still sits, but not as a precise arrival.
  - Without an anchor (cushion fallback) there is no settle and never a precise arrival.
- **Height:** Z is not settled. While walking, CharacterMovement keeps the capsule 1.9–2.4 cm
  above the floor, so arrivals differ in height by up to 0.5 cm. An offline receipt (fixed
  transform) therefore rarely applies.
- **Receipt sources:** either one gives a receipt.
  - **Offline evidence:** applies only at its exact audited transform.
  - **Live measurement (the practical one):** while typing, at 5 Hz, `AnalyzeCapturedSeatSkin`
    measures the actually evaluated component pose at the actual body transform, against the
    audited cushion and the walkable floor. The result is stamped with that transform, the
    evaluated clip serial and the time. It is accepted only for 0.25 s, the same serial and the
    same transform within 0.05 cm and 0.05°. A later displaced arrival is never covered.
  - **Live measurement gates:** all five patches in band, no invalid influences, and facing skin
    in every patch. Each result is logged as `SUB01_SEAT_LIVE_MEASUREMENT` when it changes.

## What the adapter does each live tick

- **Inputs, all from existing live fields:**
  - command identity = epoch | sequence | activity;
  - the seat is wanted only at the `desk` node with an empty path and a desk activity;
  - typing is wanted for use_computer / research / chart;
  - freshness (≤ 3 s), privacy, blocked, chair measured and its revision (the exact chair-report
    text);
  - the bound roles;
  - arrival at the approach point (< 12 cm, on ground) and the heading error;
  - playback as the hands proxy actually evaluated it: `SeatEvaluatedSequence`,
    `SeatEvaluatedSerial` and `SeatEvaluatedTime`, recorded in `Evaluate` and published in the
    next `PreUpdate`. It is never the requested `TargetSequence` and never a wall clock. A clip
    counts as started only when the evaluated sequence is the requested one under the requested
    serial. The same sequence still evaluating under an older serial is not a start;
  - the receipt, from the live `FirstPersonBody` world transform (location, pitch/yaw/roll,
    `GetScale3D` X/Y/Z) via `Sub01SeatReceipt`.
- **Movement:** `AddMovementInput` toward the approach point (the audited mesh anchor minus the
  mesh offset, or the cushion fallback); a bounded turn in place at 103°/s; otherwise
  `StopMovementImmediately`. The live loop's walking code is gated by
  `!SeatOut.MovementInput && path` → stop and return. A seated body never walks off.
- **Animation:** after `Tick` picks the posture clip, `ApplySeatAnimation` overrides it with
  the requested seat clip. Playback restarts only when `ClipSerial` changes. The character
  hands the proxy the serial itself, with its sequence, start and looping. After the target
  switch, the proxy applies them once, as soon as `Current` holds that sequence. This happens
  even when the sequence did not change, for example Sitting requested again. The proxy then
  reports that serial back with what it evaluated. DeskTyping keeps the measured contact
  profile's own start and non-looping. While seated, the camera follows the captured Head bone, and it is restored
  on standing.
- **Verification:** `NativeSeatVerified = SeatOut.ContactVerified` is the only assignment.
  `SeatOut.PCFocusAllowed` false forces focus off. The existing ACK lease and PC-command guard
  remain in place.

## The state machine (`FSub01SeatTransition`)

Standing → Aligning (turn in place) → SittingDown (StandToSit, 2.233 s) → SeatedIdle
(Sitting) → ToTyping (SitToType, 1.2 s) → Typing (DeskTyping) → StandingUp (SitToStand,
2.067 s) → Standing. Refused carries a reason: ChairUnmeasured, Private, Stale, Blocked,
RoleMissing, ClipUnavailable or ChairChanged.

- **Contact** is verified only while Typing the evaluated DeskTyping start, from this tick's
  receipt. Nothing is held over. A body moved off the audited transform loses contact on that
  tick, and so does a changed command or chair.
- **A receipt** requires accepted evidence: per-patch worst gap, median and coverage in band;
  finite values; the same mesh, clip, family and chair; a pose time inside the audited range.
  It also requires the audit's own transform, to numeric noise: within 0.05 cm in 3D, 0.05° on
  each of pitch, yaw and roll, and 0.01% on each scale axis. Those tolerances are far below the
  contact gates (soles 0 to +1 cm). The evidence carries `body_rotation_pyr` and
  `body_scale_xyz`. `unreal_audit_seat_contact.py` now writes them, and for older reports they
  are derived from its fixed `Rotator(yaw)` at unit scale.
- **Re-auditing at the live pose:** the walking arrival gate is 12 cm, so a receipt passes
  only if the audit was made at the exact live seated transform. On entering Typing, the
  character logs `SUB01_SEAT_LIVE_BODY cm=[…] pyr=[…] scale=[…]`. Re-run the contact audit
  posed at that transform, then rebuild the evidence. Until then `NativeSeatVerified` stays
  false, which is intended.
- **Alignment** refuses Blocked and a changed chair.
- **Never sits** without the sit and stand-up roles.
- **Failure handling:** a sit or bridge clip that never starts fails closed; a get-up that never
  starts keeps movement off.

## Not claimed

None of this is native runtime evidence until the editor build, the measured reports, and a
viewport and log check of `SUB01_SEAT_PHASE` exist. The visual blend between the captured
clips is unmeasured. That matters in particular for the 7 cm hip difference between the end of
StandToSit and the start of SitToType. The backrest, thighs-under-desk and chair-frame
clearance are not covered.
