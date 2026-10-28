# Kimi consultation (2026-10-23): Vagon input on the owner's Cloud Computer

Model kimi-k3.1-pro through tools/ask_kimi.py on the pod. Three rounds: the input problem with the diag facts and two
frames (`q-vagon-input.txt`, 330 s), a code review of the diff after the first fixes (`q-vagon-input-review.txt`; the
first attempt ran out of tokens while reasoning, the second used 64k, 693 s), and a review of the final diff
(`q-vagon-input-final.txt`). The answers are advice to weigh; what was adopted is listed at the end. Measured facts and
the resulting behaviour are in docs/streamer/VAGON.md A6.

## 1. The input problem (before the live measurements)

_kimi-k3.1-pro, 330 s, 28213 completion tokens._

The WebRTC statistics establish a healthy **media** path, not an input path. The only positive input result is that `Meta` reached Windows. The YouTube click/type test is inconclusive because remote focus was never established.

### A. Input capture and transport

Vagon’s exact implementation cannot be determined from the supplied facts. A conventional absolute-mode remote-desktop client usually has:

- **Keyboard:** `keydown`/`keyup` listeners on `window` or `document`, or occasionally on a focusable stream/input element. Mapping may use `event.code`, `event.key`, legacy `keyCode`, and modifier state.
- **Mouse/wheel:** listeners on the `<video>`, its container, or a transparent input surface. Clients normally consume `pointerdown/up` or `mousedown/up`, moves, and `wheel`; they need not rely on the `click` event.
- **Coordinates:** absolute mode maps through the video rectangle and rendered frame size. Pointer lock is generally needed only for relative-motion/game mode, not ordinary desktop clicking.
- **Activation:** a client may gate forwarding on its own “control started” state, in addition to browser focus/user activation. `navigator.userActivation` being true does not prove that Vagon’s gate is open. Likewise, the mere existence of `requestPointerLock` is normal Chrome API surface, not evidence Vagon uses it.

Measure `document.pointerLockElement` and `document.fullscreenElement`, and log `pointerlockchange`/`fullscreenchange`. Do not request pointer lock or keyboard lock yourself until you know Vagon expects them.

Input would commonly travel over an SCTP WebRTC data channel—sometimes reliable/ordered for keys and control, lower-latency for mouse—but WebSocket or another transport is also possible. **Forty-eight bytes received does not argue against data-channel input:** input is predominantly outbound, and the remote side may send almost nothing back.

To identify the transport, inspect listeners with CDP `DOMDebugger.getEventListeners`, and install wrappers before Vagon loads:

```js
const originalSend = RTCDataChannel.prototype.send;
RTCDataChannel.prototype.send = function (data) {
  console.debug(
    'DC-TX', this.label, this.readyState,
    data?.byteLength ?? data?.size ?? data?.length
  );
  return originalSend.apply(this, arguments);
};
```

Also log channel labels/options and inspect WebSocket sends. Compare counters around exactly one key press and one mouse click. Instrument every new peer connection; do not cache channel state across Vagon reconnects.

### B. The dim layer and the session end

The definite **host-page UI** is:

- The collapsed Vagon handle and “Click to Open” tooltip.
- The expanded Vagon toolbar.
- The session-ended screen with **Retry / Return to Dashboard**.
- The dashboard/rate-session UI.

The YouTube modal and Windows Start menu are remote pixels inside the video, not host DOM.

The uniform dim with a bright Vagon handle is **consistent with a Vagon backdrop between the video and toolbar**, but it is not proof. Other possibilities are a CSS opacity/filter on the video or an ancestor, or dimming already present in the encoded Windows image. There is no standard Chrome behavior whereby `Escape` inherently dims a video. Escape can, however, exit pointer lock or fullscreen, and Vagon could respond to that transition with a resume/menu backdrop. Whether that happened is unknown because pointer-lock state was not measured.

For a coordinate-based Playwright click:

- If a backdrop is the top hit-test element and accepts pointer events, the click goes to that host element, not the video.
- If it has `pointer-events:none`, input can pass through.
- A swallowed click alone cannot explain Windows stopping; session termination would require a host disconnect/stop handler or an independent lifecycle/network event.

Your video scaling does **not** explain observation 6. Ignoring negligible letterboxing:

```text
remoteX = (760 - 0.39) × 1920 / 1918 ≈ 760.4
remoteY = 1056 × 1080 / 1079         ≈ 1057.0
```

Thus, if forwarded with no interfering menu, it was a Start-button click. Why the session ended about two seconds later cannot be determined from these observations; auto-stop, disconnection, and a host action remain possible.

### C. Why `Control+Escape` can fail while `Meta` works

`Ctrl+Esc` normally opens Start if delivered intact to Windows. Likely failure points are:

- Vagon intercepts `Escape` for its own UI or pointer-lock handling.
- The Escape event is forwarded but the Control down/up state is lost or mapped incorrectly.
• The client has an explicit Meta/Windows-key mapping but incomplete chord handling.
- A very fast chord exposes ordering or throttling bugs.

Logging `key`, `code`, `keyCode`, modifiers, event target, and outbound transport messages for both chords will distinguish these. `press()` returning successfully only means CDP dispatched the input.

### D. The “15 minutes” setting

An idle/auto-stop setting is plausible, but the label alone does not prove it.

Synthetic CDP input has no universal activity semantics. It may count if Vagon measures browser input events, forwarded input messages, or Windows input; it may not count if Vagon measures some other connection or activity signal. Video decoding, `hasFocus()`, and user activation do not prove activity. The later stop therefore neither confirms nor refutes a 15-minute idle timer.

### E. Safe runner recipe

1. **Reacquire state after every connect/retry:** current visible video, current hit-test surface, focus, pointer lock, and fullscreen state. Do not reuse elements from an earlier peer connection.

2. **Hit-test immediately before clicking**, using `document.elementsFromPoint(x, y)`, and log the top several elements with tag/id/class. Accept only:
   - the stream `<video>` itself; or
   - the exact input surface/container recorded on a verified clean stream, using a stable selector and matching geometry.

   Do **not** accept arbitrary `body/html`, a full-viewport ancestor, or a transparent div merely because it covers the stream. The video appearing below an unknown overlay in the hit stack is not sufficient. Before keyboard batches, sample the centre and several interior points as well as checking for an open host dialog/menu.

3. **Make one Playwright/CDP click after connect**, not `el.click()` or synthetic JS events, at a screenshot-verified inert location. On the supplied clean desktop, **`(1800, 900)`** is empty wallpaper. Avoid the handle with margin—approximately `x=680–790, y=0–100`—and avoid the taskbar. There is no universally safe centre click when YouTube or another application is open. Re-hit-test after moving the mouse and before pressing the button.

4. **Then establish keyboard focus:** bring the page to front and focus the known focusable input surface; otherwise your existing video fallback is reasonable:

   ```js
   video.tabIndex = -1;
   video.focus({ preventScroll: true });
   ```

   This also works with ordinary window/document listeners through bubbling. Focusing `body` adds little and can miss video-specific handling. If the click activates pointer lock, stop and reassess rather than assuming absolute coordinates still apply.

5. **Verify remote focus visually before typing.** DOM hit-testing cannot see the YouTube modal or other remote Windows dialogs. A successful click dispatch is not a successful remote focus.

6. **Remove the blind key preamble.** Do not routinely send `Meta`, `Ctrl+Escape`, `Escape`, `Ctrl+A`, or `Backspace`; the latter two are especially unsafe without a known remote text target. Never click **Power** unless stopping is intended. Leave **System, Display settings, Files, Fullscreen**, and device/permission controls alone during ordinary streaming. On an unexplained dim/backdrop, abort input and dismiss it only through an identified host-page close/resume control—do not click through blindly.

## 2. Code review of the first fix

_kimi-k3.1-pro, 693 s, 46811 completion tokens._

1. **bug — Key actions fail open when stream focus is not established.** `_vagon_keys_ready()` returns `focused`, but every caller ignores it; `VAGON_FOCUS_JS` can also fall back to focusing `document.body`. After a stale probe or stream removal, text and shortcuts can therefore go to the Vagon page itself, bypassing both the hit-test safety and the Ctrl+A fix. **Fix:** in connected Vagon mode, do not use the body fallback; succeed only when `best && document.activeElement === best`. Before every key/type/navigate/back action, require:
   ```python
   if not await self._vagon_keys_ready(box):
       raise ActFailed("the stream did not take keyboard focus; observe again")
   ```
   Add focus-false and no-stream tests for all four paths, asserting no keyboard calls. A blocked hover with successful stream focus may still proceed.

2. **risk — The new `preventDefault()` runs too early and can break Vagon forwarding.** The listener runs on the video, before the player’s root/document listeners. Those listeners now see `defaultPrevented === true` for Control, Ctrl+A, Tab, etc.; if the player ignores already-prevented events, those inputs stop reaching Windows. The diagnostics also become self-measuring: `hooks.key.prevented` now counts SUB-01’s cancellations, and the test’s `[5, 4]` expectation codifies that confusion. **Fix:** on the measured page, cancel host defaults from a late window-bubble listener, registered after the diagnostic bubble listener and restricted to keydowns targeted at the current stream. This lets Vagon’s handlers run first while still cancelling the subsequent browser default. Test with a document handler that forwards only unprevented events, and verify live that `dc_out` still rises for Control and Ctrl+A.

3. **risk — The hit test has a time-of-check/time-of-use gap.** The `_vagon_lock` does not stop page JavaScript. In particular, `hit → mouse.move → click` allows the move itself to open a hover toolbar/menu before the click; scroll has the same problem. The `ok` predicate is right for measured `video#player`, but it is checked too early. **Fix:** retain the initial check, then repeat it after the move and immediately before clicking or starting the wheel burst; refuse if the result or stream identity changes. Add a test whose second hit returns a host control. If “never press the host” must be an absolute guarantee, an armed in-page capture-phase dispatch guard is needed—another evaluate still leaves a smaller race.

4. **risk — Arbitrary page text can now enter snapshots and logs.** Both `brief()` implementations read `innerText`/`aria-label`/`title`; the diag stores this for active/covering elements, and `_vagon_hit()` puts it into `blocked` events. On a focus-failure path involving a host contenteditable, this can include typed text. `innerText` on `body` can also force layout and process the whole page merely to retain 40 characters. **Fix:** keep fixed classifications and element metadata, but remove arbitrary text from persisted diag responses and events. Add a privacy test using a unique typed secret and assert it is absent from the complete serialized diag and event log—not merely `"Meta"` from the hook counters.

5. **bug — The diag rate limit and follow-up schedule are race-prone.** `diag_now()` checks freshness before acquiring `_vagon_lock`, so concurrent stale requests queue up and each performs a forced snapshot. Additionally, connection establishment backdates `last_diag`; an immediate request can bypass the two-second gap, while an early manual snapshot rewrites that field and can suppress the intended eight-second follow-up for roughly 60 seconds. **Fix:** use separate `last_diag_at` and `next_connected_diag_at` fields, and repeat the freshness check after acquiring the lock. Test two concurrent `diag_now()` calls and an immediate post-connect request.

6. **bug — A valid data-channel label can pollute `Object.prototype`.** With label `"__proto__"`, `R.dc_out[k]` resolves to `Object.prototype`; `o.n++` and `o.bytes += ...` then write properties onto it. **Fix:** use `Object.create(null)` plus own-property checks, or a `Map` converted to a plain object only for diagnostics. The browser test should also perform actual send/receive operations; currently it verifies only that `send` was wrapped.

7. **nit — The pre-key hover is redundant on Vagon, and failed attempts are not once-per-session.** A refused hover leaves `_vagon_hover` unchanged, so every subsequent key repeats the hit test and logging, potentially including a five-second timeout. Since Meta worked with DOM focus and no preceding mouse event, **fix:** use focus-only before Vagon keys and retain pointer movement for click/scroll, or add a retry backoff if hover support is kept for other clients. The `Control+Escape → Meta` alias and the absence of an activation click are both supported by the live measurements.

## 3. Review of the final diff

_kimi-k3.1-pro, 327 s, 25723 completion tokens._

No blocking findings in the supplied diff.

1. **risk — `_vagon_hit` still has fail-open exits.** A frame without `evaluate` returns `None`, and a malformed/non-dict evaluation result also permits the input. Real Playwright frames provide `evaluate`, so this is not a demonstrated live failure, but the safety check should not depend on that assumption.  
   **Fix:** replace the missing-`evaluate` return with `ActFailed`, and after evaluation require `isinstance(hit, dict) and hit.get("ok") is True`; reject every other result. Give the test doubles an explicit `VAGON_HIT_JS` implementation instead.

2. **risk — delayed hover UI remains outside the post-move check.** The second check runs immediately after `mouse.move`; a menu opened by a timer or transition can appear afterward. Likewise, only the first of six wheel events is preceded by a hit test. This is a residual race, not a measured current-Vagon failure.  
   **Fix:** after the move, wait a defined hover interval such as `0.1` seconds, rerun `_vagon_hit`, and click immediately after success. For scrolling, rerun `_vagon_hit(x, y, "scroll")` before each wheel step and abort on failure.

3. **risk — a subframe hit test cannot see ancestor-frame overlays.** If `_vagon_frame` is ever a child frame, its `document.elementFromPoint()` can report the stream while a toolbar/dialog in the parent frame actually covers that page coordinate. The material does not establish that the current Vagon page uses this configuration.  
   **Fix:** if subframe streams are unnecessary, refuse hit testing outside the main frame. Otherwise, first verify in the main frame that the top element at the unsubtracted `(x, y)` is that stream frame’s owner element, with no ancestor overlay, then perform the existing in-frame check.

4. **nit — diagnostic byte counts are not always bytes.** `size()` uses JavaScript string `.length`, counting UTF-16 code units rather than UTF-8 payload bytes; both wrappers also increment before the native `send`, so failed sends are counted as outbound.  
   **Fix:** use a cached `TextEncoder` for strings (`encoder.encode(data).byteLength`) and update counters only after the native `send` returns successfully—or rename the counters to make clear that they count attempts.

## Adopted / rejected

From round 1 (all checked against live measurements first):
- Adopted: count outbound data-channel/WebSocket sends (input travels on the channel labelled `control`), track pointer
  lock/fullscreen transitions, re-hit-test right before a click, accept only the stream element itself as a click target
  (the live page has `video#player` on top everywhere), never press the toolbar (Power, Display settings, Files...).
- Not needed: the "one click after connect at an inert point". Measured: the Windows key opened Start with only the DOM
  focus on the video and no mouse event at all; a click would land in a remote window.
- Answered by measurement instead of speculation: the dim was the HOST page's select-all tint (Ctrl+A not prevented by
  the player), not a Vagon backdrop; Ctrl+Escape and Ctrl+A failed because Vagon's keyboard layer drops a key that
  follows Left-Control within 15 ms (its AltGr detection), not because of Escape handling or mapping.

From round 2 (all seven findings adopted):
1. Keys fail closed without the stream focus (VAGON_FOCUS_JS true only for the stream element; ActFailed otherwise).
2. The host-default cancel moved to a late window-bubble listener restricted to the stream target, so the player sees
   events untouched and the `prevented` counter measures only the player.
3. The hit test runs before and after the pointer move (`_vagon_point`), for clicks and the wheel.
4. Element summaries carry only aria-label/title, never innerText (a test types a secret into a focused contenteditable).
5. `diag_now` re-checks the gap under the lock; the connected schedule has its own `_vagon_next_diag`.
6. `dc_out` keyed by own properties only (a `__proto__` label cannot pollute Object.prototype).
7. No hover before keys (focus only, as measured).
The round-2 remark that the Control+Escape -> Meta alias was supported became moot: the root cause (the 15 ms window)
was found and fixed with a held chord, and the alias was removed.

From round 3 ("no blocking findings"; all four hardening items adopted, then deployed and re-verified live):
1. `_vagon_hit` fails closed: a frame that cannot be checked, or any answer but a dict with `ok: true`, is a refusal; the
   unit-test fakes answer the hit test explicitly.
2. The second hit test runs `VAGON_HOVER_S` (0.1 s) after the pointer moved, and the wheel point is re-checked before
   every one of the six steps (a refusal mid-scroll stops the remaining steps).
3. For a stream inside an iframe, the parent document must also have that iframe on top at the point (real-browser test
   with a parent-page dialog over the embed).
4. Outbound counters are updated after the native `send` returned, with UTF-8 byte sizes (real loopback data channel in
   the test).
