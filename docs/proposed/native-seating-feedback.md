# Native physical seating and feedback: gap audit and next-step patch (proposal)

Status: audit only, nothing applied. The current diagnostic movie
(`tools/run_unreal_native_window_recording.py` with `-Sub01DiagnosticSeat`) is a
static pose diagnostic, **not** autonomous PC use. `BeginLiveHome` refuses to
start while the diagnostic seat is active (`tools/unreal_live_home_runtime.py:29`).

## What exists

| Step | Backend | Native |
|---|---|---|
| Decide desk activity | `home_world.py:83-88` (`use_computer`, `research`, … → `desk`) | polls `GET /home/state` (`unreal_live_home_runtime.py`) |
| Walk to desk node | simulated path | real CharacterMovement; `SUB01_LIVE_HOME_REACHED` at XY<12cm, floor<20cm (`unreal_live_home_runtime.py:91-93`) |
| Sit | `seated += dt*0.65` timer (`home_world.py:379-381`) | **none**: `SUB01_LIVE_HOME_BOUND … seated actions not accepted` |
| Seated pose | — | only `-Sub01DiagnosticSeat`: `DisableMovement()` + fixed mesh at `(203.9,-232.3,-.6)` (`unreal_hands_diagnostic.py:38-56`), ~157cm from the native desk node `(200,-75)` |
| PC focus | `activity_ready()` needs `seated==1` (`home_world.py:311-316`) | `SetOperatorFocus(true)` as soon as the path is empty at `desk` (`unreal_live_home_runtime.py:85`), no seat check |
| Feedback to backend | `activity_arrived()` (`live_server.py:1091`) trusts the timer | **none**: the state bridge is one-way; no endpoint takes native arrived/seated/blocked |

## Missing links, in order

1. The backend `seated` value is a timer, not a physical result.
2. There's no native approach from the desk node to the chair (there's no chair point or tolerance in the graph).
3. There's no native sit transition (no face-desk turn, sit clip or blend, or capsule/collision change).
4. There's no physical seat confirmation (no chair-cushion trace, no hip-height check, no log marker).
5. PC focus turns on before (and without) any seat check.
6. There's no native → backend channel for `arrived` / `seated` / `blocked`.
7. No test runs these states end to end. Current tests match source strings or the backend simulation.

## Next-step patch (small, ordered, each gated)

1. **Seat target, data only.** Add `SEATS = {"desk": {"approach": ..., "hip": ..., "face_yaw": ...}}`
   next to `NODES` in `home_world.py`. Measure the values from the chair collider that
   `tools/home_asset_audit.py` already keeps; the diagnostic pose puts the chair near UE `(203.9, -232.3)`. Add a parity test like
   `tests/test_unreal_native_route.py` (source metres → UE cm).
2. **Native seat state machine** in `tools/unreal_live_home_runtime.py`
   (proposed, Codex/root-owned): `Walking → Approach → Turning → Lowering → Seated`.
   - `Approach`: CharacterMovement input to the approach point (same 12cm/20cm gate). There's no `SetActorLocation`.
   - `Turning`: reuse the bounded yaw from `tools/first_person_yaw.py` until it's within 2°.
   - `Lowering`: play the existing sit clip, keep the capsule, then `SweepSingleByChannel` down from the hip socket.
     Accept only a hit on the chair actor within 4cm of `hip.z`. Log `SUB01_LIVE_HOME_SEATED chair=<actor> hipErrCm=…`
     or `SUB01_LIVE_HOME_SEAT_REFUSED reason=…`.
   - `SetOperatorFocus(true)` only in `Seated`.
3. **Feedback channel.** The native side sends a loopback-only, admin-token `POST /home/native_state` with
   `{epoch, node, phase: walking|arrived|seated|blocked, chair}`. `live_server` stores it with a 3s freshness window.
   `HomeWorld.activity_ready()` requires `native.phase=="seated"` for the same epoch **only when a native consumer is bound**,
   so the browser-only mode keeps the timer. A blocked report cancels the activity rather than letting the timer complete.
4. **Tests (CPU).** Cover the endpoint (auth, loopback, stale-epoch drop, privacy), the `activity_ready` gating with and without a
   bound native consumer, and the native source contract (state order, no teleport, focus only after `SEATED`).
   Acceptance stays runtime: a live-home recording that shows `REACHED desk → SEATED → focus` from backend decisions alone,
   with `-Sub01DiagnosticSeat` **absent**.

Out of scope here: fingers, body pose retargeting, floor fix, privacy rules, backend actor positions.
