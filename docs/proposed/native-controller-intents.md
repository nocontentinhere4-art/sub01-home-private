# Private held-controller game link (source only)

`SUB01_BRAIN_CONTROLLER=1` selects bounded semantic controller commands from the existing actual `play_console` game policy. It remains OFF by default. This does not establish a seat, grip, rendered thumb motion, or movable stick/button geometry. The current prop is a single mesh; semantic ACK state is not visual press synchronization.

The existing native seat feedback must be required, fresh, seated at the known `sofa`, and match the actual HomeWorld `sequence`, activity and target. Additionally the current native process must atomically publish `/home/unreal/.sub01-private/native-controller-grip.json`, owner1001/mode600, at most4096bytes. Accepted receipts expire after750ms and require:

- `schema: "sub01-native-controller-v1"`, `mode: "live"`, `privacy: false`, `activity: "play_console"`, `node: "sofa"`, `chair: "sofa"`.
- `captured_utc`, actual `native_pid` and `/proc` `native_start_ticks`, current backend `epoch` and integer `route_sequence` (matching HomeWorld.sequence), and the real currently painted `frame_id`.
- `seat_verified: true` and `grip_verified: true` only from actual native contact checks. Neither API payloads nor timer seating establish these facts.
- `assembly_asset` and `source_sha` matching operator-reviewed startup registration `SUB01_CONTROLLER_ASSEMBLY` and `SUB01_CONTROLLER_SOURCE_SHA`; absence rejects input.
- Exact original owner `/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner` and Gaming capture `/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming`, finite `capture_time` in0..5.0334seconds.
- `contact_review_sha` matching registered `SUB01_CONTROLLER_CONTACT_REVIEW`, the reviewed genuine capture/assembly/contact witness. No registration exists merely because the mesh was imported.

Brain intents map to forward/back and bounded look for explore/escape, real cursor mining/placement for resource decisions, and actual inventory consumption for eat. The worker receives existing correlated `operator_input` packets, with250ms control expiry and at most0.035radian turn increments. A100ms pump renews controls only while physical evidence and the two-second current intent remain valid. Missing/stale/private/disconnected evidence releases controls and clears semantic state.

`input_receipt.controller_state` reports actual applied keys/look and the worker's real pending operation. The Python adapter accepts only matching consumer/event/input IDs, monotonic ACKs and the same physical owner. Pose fields are semantic stick/button state from that ACK, expire after250ms, and return to neutral on release. Late rejected, duplicate or superseded replies cannot restore a press. Finger and body animation is unchanged. Native visual button/stick segmentation and runtime sofa/grip/gameplay proof remain pending.
