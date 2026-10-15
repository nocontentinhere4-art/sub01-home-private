# Existing-transport PC injected ACK — private source candidate

No live runner, VM, Game, guest snapshot or public service was restarted or modified. This candidate adds an optional correlation receipt to the existing `/pc/graphical-input` and existing worker stdin/stdout; it creates no endpoint, input dispatch queue, retry loop or new guest.

## Contract

Legacy requests without `native_receipt` preserve their existing boolean transport result. A new native caller may include:

`native_receipt = {input_id: existing GraphicalInputs Ticket, generation: captured native Generation}`

Both values must be positive exact integers <=2^53−1. This is opaque caller identity, **not ACK authority**. The runner validates it and strips it from the PS/2 payload. Any client `_receipt` field is also discarded. `Computer` generates a fresh server-owned random128bit correlation token, an internal generation and a1400ms deadline. The existing worker receives only that private envelope alongside the actual input.

The Python pending-future map is bounded32 and does not dispatch or queue commands. An ACK must match its exact unpredictable token, internal generation, exact subprocess stdout producer, operation-specific level and sane monotonic worker timestamps. Unknown/replayed/wrong-process/wrong-generation IDs cannot resolve it. Waiting is bounded1.5seconds; timeout, focus cancellation or worker loss refuses the receipt. No retries occur.

The actual worker emits `GuestKeyboardInjected` only after awaiting every real `vm.keyboard_send_scancodes` invocation in the existing ordered keyboard path; `GuestMouseInjected` means the real mouse bus/API function completed. Neither means the guest OS/application consumed the input, a character appeared, a UI target activated, a keycap moved or a finger made contact. The response echoes the original native Ticket/Generation from Python's pending context, not from the worker ACK.

A successful optional response has `ok:true`, matching `native_receipt`, `ack_level`, Python monotonic `queued_at`/`ack_received_at` and worker monotonic `worker_started_ms`/`worker_finished_ms`. Native must preserve its existing closure Ticket/Generation checks and additionally parse HTTP200 JSON `ok:true`, exact echoed identities and recognized level. HTTP200 `{ok:false}` must fail. The native owner owns this later C++ wiring; it is not applied here.

## Cancellation and held keys

Native focus loss cancels only pending correlated native requests through the existing stdio channel. Each cancellation packet is generated from an actual server pending entry. The worker validates its token/internal generation. Its keyboard task stops, including a pending API Promise, within its deadline/cancel signal. Cleanup releases only keys that task originally acquired; an already-held key from another task is not released. Incomplete extended prefixes are cleared only when owned by the cancelled task. Existing privacy/idle pause and shutdown still intentionally cancel all keyboard tasks and release all held keys before stopping the VM. Late ACKs cannot revive cancelled futures or visual cues.

The worker uses its original keyboard ordering chain; the new receipt helper only observes/cancels existing tasks. A bounded correlation refusal never falls back to an uncorrelated accepted input. Current global transport/private-state protections remain in place.

## Executed verification

Tests execute the **actual worker source** with a stub V86 object and its real keyboard/protocol modules. They show no ACK before a held API Promise resolves, a positive matching ACK after real make/break invocation, scoped cancellation of a hung call, negative ACK on API failure, duplicate/token/generation/deadline refusal and preservation of another task's held Ctrl key. Python protocol tests verify that pipe drain alone cannot resolve success, exact subprocess/token/generation/operation correlation, no replay, pending-capacity bound, native identity validation, timeout-specific cancellation, focus cancellation and immediate broken-pipe refusal without stale framebuffer pixels. HTTP tests validate optional metadata stripping/echo and preserve legacy/privacy behavior. No VM boot is needed for these source tests.

Live `GuestKeyboardInjected`/`GuestMouseInjected` is still **unverified** until root reviews the candidate and authorizes a saved-state-safe rollout followed by actual browser input/frame checks. Hand contact/readiness remains false.
