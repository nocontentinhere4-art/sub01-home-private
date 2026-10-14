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

## What the adapter does each live tick

- **Inputs, all from existing live fields:**
  - command identity = epoch | sequence | activity;
  - the seat is wanted only at the `desk` node with an empty path and a desk activity;
  - typing is wanted for use_computer / research / chart;
  - freshness (≤ 3 s), privacy, blocked, chair measured and its revision (the exact chair-report
    text);
  - the bound roles;
  - arrival at the approach point (< 12 cm, on ground) and the heading error;
  - the requested clip playing on the hands instance and its time (the contact profile's actually
    evaluated time while typing);
  - the receipt, from the live `FirstPersonBody` world transform via `Sub01SeatReceipt`.
- **Movement:** `AddMovementInput` toward the approach point (the audited mesh anchor minus the
  mesh offset, or the cushion fallback); a bounded turn in place at 103°/s; otherwise
  `StopMovementImmediately`. The live loop's walking code is gated by
  `!SeatOut.MovementInput && path` → stop and return. A seated body never walks off.
- **Animation:** after `Tick` picks the posture clip, `ApplySeatAnimation` overrides it with
  the requested seat clip. Playback restarts only when `ClipSerial` changes. A serial-guarded
  proxy hook starts the clip at `ClipStartSeconds` (mid-sit get-up) and disables looping for
  the transitions. While seated, the camera follows the captured Head bone, and it is restored
  on standing.
- **Verification:** `NativeSeatVerified = SeatOut.ContactVerified` is the only assignment.
  `SeatOut.PCFocusAllowed` false forces focus off. The existing ACK lease and PC-command guard
  remain in place.

## The state machine (`FSub01SeatTransition`)

Standing → Aligning (turn in place) → SittingDown (StandToSit, 2.233 s) → SeatedIdle
(Sitting) → ToTyping (SitToType, 1.2 s) → Typing (DeskTyping) → StandingUp (SitToStand,
2.067 s) → Standing. Refused carries a reason: ChairUnmeasured, Private, Stale, Blocked,
RoleMissing, ClipUnavailable or ChairChanged.

- **Contact** is verified only while Typing, the audited family. It holds for at most 3 s after
  the last passing receipt and is cleared by a command or chair change.
- **A receipt** requires accepted evidence: per-patch worst gap, median and coverage in band;
  finite values; the same mesh, clip, family and chair; a pose time inside the audited range;
  within 2 cm in 3D, 3° of heading and 0.1% of scale.
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
