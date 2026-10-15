# Private PC action receipts — source candidate only

`tools/native_pc_bridge/Sub01PCActionTimeline.h` observes the existing native input queue. It has no network, dispatch, retry, input-payload buffer, pose solver or contact-readiness setter. Its bounded history is evidence, not a second command queue. Nothing is installed into the running Game.

## Actual existing path and concrete gaps

1. `Sub01PCBridge.cpp::SendGraphicalInput` checks graphical focus/privacy/token, pushes the JSON body into `GraphicalInputs`, then calls `PumpGraphicalInput`.
2. `TSub01GuestInputQueue::Begin` assigns a monotonically increasing native ticket only when dispatch starts. Requests are serialized. `Generation` invalidates asynchronous completions after private-state changes.
3. The current HTTP completion checks status 200 and `GraphicalInputs.Complete(Ticket)`, but does **not** parse the JSON response's `ok` boolean. The runner can return HTTP200 with `ok:false`; this is not a successful action receipt.
4. `scripts/home_pc_runner.py::graphical_input` returns `ok` after `home_computer.py::graphical_input` awaits `send`. That is worker stdin delivery, **not** guest consumption, rendered text, physical PS/2 make/break timing or hand contact. `computer/worker.cjs` emits no correlated per-input consumed ACK. Keyboard packets contain make AND break (plus modifiers) in one payload.
5. `unreal_home_hands_runtime.py` advances `Current` at `TargetRate`; its animation clock has no input ticket. `unreal_contact_profile_runtime.py` changes `Current` through `ContactRestartSerial` and can hard-set 3 seconds; this is not an actual typed-key receipt timeline. A free-running typing clip cannot establish that a finger pressed the accepted key.

## Exact future native-owner wiring contract

Keep the one existing `GraphicalInputs` queue and endpoint. Replace its item with a small wrapper containing the existing body, monotonic enqueue time, and action category; do not add unknown fields to the HTTP JSON. Preserve key/button metadata privately only if a later validated pose mapper needs it; never log typed text or credentials.

- After the existing queue accepts an item, retain its actual enqueue timestamp in that same item. At `Begin`, use its **real existing Ticket** and captured `Epoch=Generation` to call `Queued(Epoch, Ticket, Kind, originalEnqueueTime)` then `Sent(Epoch, Ticket, now)`. The helper explicitly permits historical enqueue time after the preceding request's ACK, while requiring nondecreasing enqueue ordering and monotonic send/ACK clocks. An observer-capacity failure must fail closed rather than silently generate an untracked animation.
- In the existing HTTP completion, first preserve the current `Epoch==Generation` and exact `Complete(Ticket)` guards. Parse a JSON object and require the boolean `ok` to be true in addition to HTTP200. Only then call `Acknowledged(Epoch, Ticket, now, TransportAccepted)`. Do not report `GuestConsumed` with today's runner. No worker transport/API change is included in this source candidate.
- Queue refusal, transport/parse/refusal failure, `ClearPrivateState`, `EndPlay`, privacy onset and **every focus loss** call `CancelAll(now)` immediately. Continue the existing neutral guest release/session pause separately. Its pending HTTP must not keep a visual button/finger held. Existing late callback guards stay intact; cancelled receipts cannot be resurrected by a later ACK.
- A real neutral release packet is classified `Release`. Its successful transport ACK timestamps `ReleasedAt` and releases any older acknowledged visual action. It does not retroactively manufacture guest-consumed timing.
- The game-thread hands owner may read `Sample(Generation, now, realPCFocus, privacy)` and publish a copied immutable sample to the animation proxy. The sample starts at the matched ACK, expires within 250ms, and is neutral before ACK or after focus/privacy/epoch/timeout loss. It never loops on its own and must not advance based on enqueue time or HTTP arrival order. Use the same monotonic `FPlatformTime::Seconds()` domain throughout.
- This is only a bounded event cue. Do **not** drive a supposed per-key contact pose until actual key coordinates, both-side reach, existing owner skin, real desk placement, finger approach/depression/release and recorded source motion have independent validation. The helper supplies no contact-ready flag. Current native gating remains false.

## Executed source verification

`tests/test_native_pc_action_timeline.py` compiles and executes the actual header with the actual queue header. It checks real queue ticket correlation, queued/in-flight neutrality, ACK identity/order/level, duplicate and late ACK refusal, historical enqueue timestamps, bounded expiry/history, neutral release, generation changes, immediate privacy cancellation, no resurrection, nonfinite/regressing clocks and zero capacity. `tests/test_native_pc_command_guard.py` remains unchanged and verifies existing physical seat/private-state restrictions. This is source verification, not native installation or actual hand contact acceptance.
