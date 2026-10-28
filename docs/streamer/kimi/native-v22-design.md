# Native v22: Kimi's design review (2026-10-24 ~16:10 UTC) and what was applied

Model `kimi-k3.1-pro`, 1187 s (a first attempt at 24k tokens ran out while reasoning; rerun at 60k). Question:
`q-native-v22-design.txt`; attached: the current pod `Sub01PCBridge.h/.cpp`, `scripts/streamer_monitor_feed.py` (the version
before commit 8634ff9), and the frames `photos/20261024/now-cam2.jpg` and `now-webcam.jpg`.

## Kimi's answer (verbatim)

## Overall verdict

The persistent-texture and background-decode design is sound. I would not unconditionally enable the feed yet, for two reasons:

1. **Privacy/source identity is a release blocker.** The current 8832/8838 mismatch must fail closed, and the sidecar needs its own runner gate before `monitor_feed=1`.
2. **60 fps is not yet demonstrated.** A 16–19 ms render thread is already approximately 62.5–52.6 fps before adding the monitor upload. The upload cost cannot be known without profiling.

## 1. In-game PC monitor

### a) Thread model: use the scheduled pump, not an `FRunnable`

Use the existing cam2-style model: one background task in flight, non-blocking FIFO reads, and an atomic `Busy`.

At 60 Hz, a 3–5 ms decode fits comfortably inside the 16.67 ms period. A blocking `FRunnable` would improve latency slightly, but that is not useful if you also adopt the proposed 750 ms privacy playout delay, and it adds shutdown/wake-up complexity.

Requirements:

- The shared state must contain no UObject pointers and must be kept alive by the task itself.
- FIFO open/read/parse/decode all stay off the game thread.
- Completion hands ownership of one compressed or decoded result to the game thread; never update textures from the worker.
- Gate closure increments the epoch and clears the parse buffer, pending playout frames and completed-but-not-uploaded results.
- Shutdown must not wait indefinitely for a FIFO operation. With the non-blocking pump, normal task completion is sufficient.
- Treat writer loss/reconnection as a capture discontinuity: discard the partial frame and buffered playout data.

### b) Parser: the marker-aware parser is reasonable, but not mandatory for privacy

Keep it if implemented with focused tests. It is not excessively complex for a streaming JPEG reader, and it recovers better from “truncated old frame immediately followed by a good new frame” than a naive SOI-to-EOI scan.

It must correctly handle:

- A trailing `FF`, `FF D8`, or partial segment header across reads.
- Fill `FF` bytes and standalone markers.
- Segment lengths before skipping.
- Byte stuffing and restart markers after SOS.
- SOI inside a frame, oversize frames and buffer-limit resync.
- Retaining the newest complete frame without retaining unbounded garbage.

For this exact ffmpeg producer, a plain SOI/EOI parser plus size caps and decode validation would also be acceptable; EXIF embedded EOI is not the main threat. Neither parser is a privacy boundary.

### c) Decode: approve, with validation before allocation

Loading `IImageWrapperModule` once on the game thread and using one wrapper sequentially from the single pump is appropriate.

Before `GetRaw`:

- Require a successful `SetCompressed`.
- Validate positive dimensions and the 1280×1024 layout limit.
- Check the `W*H*4` calculation for overflow.
- After decoding, validate the returned buffer size/stride rather than assuming it.
- Reject unsupported dimensions instead of allocating an unexpectedly large image.

BGRA8 into an sRGB texture is the right color path for these JPEGs.

### d) Upload: keep the render-thread copy; 60 remains a cap, not a proven default

The source-rect upload is:

- `1280 × 720 × 4 = 3,686,400 bytes` per frame.
- At 60 fps: **221.2 MB/s**, or **210.9 MiB/s**.
- At 30 fps: approximately **105.5 MiB/s**.

That bandwidth is not inherently problematic on Vulkan. The unknown is driver/staging and render-thread CPU cost. `UpdateTextureRegions()` on the game thread, followed by the ordered render-command/RHI update, is the correct place for it. Do not build a custom background Vulkan upload path for v22.

Use these rules:

- Create the texture and initialize its complete mip to opaque black before binding.
- Enqueue black initialization before the first source-rect update.
- On a layout/source-rect change—not only a texture-size change—clear again before binding. Otherwise pixels outside a new source rectangle can survive.
- `SrcPitch` for the 1280×720 partial update is `1280*4`, not the layout-texture pitch.
- Keep the pixel allocation alive until `DataCleanupFunc`; if no render command is enqueued, free it yourself.
- Track pending uploads so a stalled render thread cannot cause unbounded pixel-buffer growth.

The JPEG decoder uses approximately 0.18–0.30 of one core at 60 fps, so decode CPU is not the primary concern.

**Default:** retain `monitor_fps=60` as the requested cap, but qualify it with a cam2-on, moving-desktop soak test. If the render thread remains above budget or upload commands accumulate, the pod fallback should be **30**, not a different upload architecture. There is no basis in the supplied material to promise 60.

### e) Binding: approve, but retain the desired own-frame explicitly

Routing all six bridge bind sites through one function is the right fix.

The bridge needs three distinct pieces of state:

- `DesiredOwnFrame`: the latest terminal/graphical texture requested by the bridge.
- `FeedFrame`: the texture supplied by the character.
- `LastBoundFrame`: used solely to avoid redundant MID calls.

The effective selection is:

```text
FeedFrame + gate open + new-epoch frame uploaded
    -> FeedFrame
otherwise
    -> DesiredOwnFrame
```

`SetMonitorFeedFrame()` and every bridge state change should run that same selection logic. In particular:

- `ClearPrivateState()` must immediately select the terminal/neutral picture.
- Gate closure must not depend on the character happening to call `SetMonitorFeedFrame(nullptr)` first.
- A same-pointer persistent texture does not need rebinding on every frame.
- On reopening, enqueue the new-epoch upload before selecting the feed texture.

The character-side and bridge-side checks are both worthwhile: the former prevents unnecessary decode/upload; the latter is the final display enforcement point.

### f) Stale fallback: use a no-progress timeout

The fallback behavior is correct, including closing the fd when `monitor_feed=0`; ffmpeg then stops after the idle period if that was the last reader.

With a 750 ms playout delay, do **not** define freshness solely as “the shown frame was read less than 1 s ago.” A healthy shown frame is already approximately 750 ms old, leaving only 250 ms of jitter tolerance.

Instead use:

- Receive liveness: newest complete FIFO frame arrival.
- Playout liveness: last successful new-frame upload.
- Content age: `now - shown_frame.read_at`, logged separately.

A **1.0 s no-progress timeout** is reasonable for stale fallback. Gate closure itself remains immediate and does not wait for staleness.

## 2. Privacy gate

### Choice: **(iii), with the sidecar gate moved into v22**

Use both sidecar gating and game-side delayed playout. Do not ship option (i) alone, and do not describe the delay as a complete privacy proof.

However, there is an important limitation:

> If the requirement is an absolute guarantee that no private pixel can ever appear, none of (i), (ii) or (iii) is sufficient. A private interval missed by both pollers can still be captured and later displayed after public state resumes. The hard guarantee requires the runner’s neutralizing path to produce the actual streamed frames, or an equivalent per-frame guarantee at capture time.

For a documented best-effort preview, (iii) is the strongest of the proposed designs.

### Blocking source-identity issue

The confirming state read must belong to the **same source as the raw capture**.

With the current configuration:

- Bridge origin: 8832, `pc_mode=chromium`.
- Sidecar source: `:103`, driven by the Vagon runner on 8838.

The proposed `pc_mode=="vagon"` check should therefore keep the feed closed. That is safe but makes the feature inert. Do not weaken the check to make it work.

Use an explicit monitor source configuration, normally:

```text
monitor runner origin = http://127.0.0.1:8838
capture display       = :103
```

Either:

1. Give the feed its own authenticated 8838 state poller, or
2. Deliberately move the whole bridge to 8838 after verifying that all required bridge endpoints behave correctly.

Also validate the sidecar’s configured display. `pc_mode=vagon` alone does not prove that an arbitrary X display belongs to that runner. Missing fields, origin/display mismatch, or unavailable authentication must mean `source_mismatch` and a closed gate. The supplied material does not establish whether the existing token can simply be reused for 8838.

### Gate additions and lifecycle

The listed conditions are appropriate. Keep `PrivacyDesired`, even though it is often redundant with `LocalPrivacy`; it is cheap fail-closed defense. `MonitorMaterial` is an operational condition rather than a privacy condition, but retaining it is harmless.

Additionally:

- Validate the second poll read only after its response arrives, but timestamp it with the request’s **start** time.
- Clear both `FeedSourceConnected` and `PublicConfirmedAt` on `ClearPrivateState()`, source changes and EndPlay.
- Close immediately on a non-public response, malformed response, source disconnect, local privacy or generation change. The 1.5 s age check is only for a hung/absent poll.
- If the 8838 schema provides `display.kind`, require the expected graphical kind rather than accepting `display.available` alone.
- Bump the feed epoch once per closure transition, not repeatedly on every closed tick.
- Clear partial JPEGs, delayed frames and decoded results on every epoch change.

### Delayed playout: implement it against actual confirmations, not just a timer

For frame `f`, require all of the following before upload:

```text
now >= f.read_at + 0.75 s
gate is open now
f.epoch == current epoch
a completed public confirmation C exists with C.start_time > f.read_at
```

The confirmation must be one of the fully validating second reads described above.

This handles the important persistent-lock case: a frame read after the runner locks cannot obtain a later public confirmation while that lock remains in force, even if the game has not yet noticed the lock. It still does not solve a short, entirely unobserved private interval.

**Do not buffer 45 decoded BGRA frames.** At 60 fps and 750 ms, that would be approximately **166 MB**. Instead:

- Retain a ring of compressed JPEGs with read timestamps and epochs.
- Use capacity for at least 64 frames, with a separate approximately 16 MiB byte cap.
- Decode only the frame selected for playout.
- Drop late/ineligible frames and count them separately.

This changes the simpler “always keep only the newest frame” rule, but still preserves the one-decode-in-flight limit.

### Sidecar gate

The sidecar should not start raw capture until an authenticated 8838 read confirms the required public/Vagon state. While running, it should stop offering frames immediately on non-public state, error or stale confirmation, and require a fresh public confirmation before resuming.

Reasonable starting values are:

- State poll: **100 ms**, one request in flight.
- HTTP timeout: **250 ms**.
- Stop writing if no valid public confirmation is available for **300 ms**.

Those are availability/latency choices, not a proof against shorter private intervals. Local privacy still needs the immediate game-side gate. The sidecar must also clear its pending partial write on a gate transition.

### Are 1.5 s and 0.25 s right?

- **1.5 s confirmation age:** keep it. It is a reasonable final liveness timeout for a 0.5 s poll with potentially hung HTTP requests. It bounds the age of the last confirming read, not the actual time since the runner became private.
- **750 ms playout:** reasonable. It gives 250 ms beyond the normal 500 ms confirmation interval. Larger confirmation stalls may starve playout, but they fail safe.
- **250 ms reopen quarantine:** reasonable for the stated approximately 256 KiB pipe and normal pump scheduling. It is not, by itself, proof against every possible ffmpeg-internal buffer. Combine it with epoch resets, draining/discarding and writer-reconnect handling rather than relying on timing alone.

## 3. Persistent textures in the bridges

The helper is worthwhile. The main pitfalls are:

1. **The helper does not provide GC ownership.**  
   A `TObjectPtr<UTexture2D>&` argument does not make the caller’s member a `UPROPERTY`. Every texture cache/slot must have explicit UObject ownership on the game-thread owner. Do not rely solely on a MID parameter to keep textures alive.

2. **`Images.Clear()` is not an unbind operation.**  
   Preserve an explicit neutral-material bind before clearing device state. Also, if `Images` was the only texture owner, clearing it cannot simultaneously make the persistent texture “survive.” Use a separate `UPROPERTY` persistent-texture cache if survival across privacy clears is intended.

3. **Initialize `CreateTransient` completely.**  
   Set sRGB, filtering, clamp addressing, no mip generation and `NeverStream` before resource creation. Its initial mip contents are not a usable black image. Opaque BGRA black is bytes `00 00 00 FF`; zero-filling alone produces transparent black.

4. **Handle resource readiness.**  
   If `GetResource()` is null, do not bind or leak the pixel buffer. Defer and retry, or fail the update and release the buffer. Do not cache a raw `FTextureResource*` across texture recreation.

5. **In-place update while bound is valid.**  
   `UpdateTextureRegions()` orders the RHI update with rendering. There is no need to unbind/rebind or call `UpdateResource()` every frame. Calling `UpdateResource()` per frame would recreate the problem you are trying to remove.

6. **Lifetime and region details matter.**  
   The region descriptor and pixel storage must survive until render-thread cleanup. Pitch, rectangle offsets and buffer size must describe the source rectangle exactly. All UObject and MID access remains on the game thread.

7. **Privacy reopen requires overwrite before binding.**  
   This applies especially to device textures retained across `Clear()`. On any changed layout, clear the whole texture first; a partial new frame must not expose pixels from an older layout.

## 4. Camera 2 exposure

### Default: manual mode, starting at EV bias −3

Use:

```text
cam2_exposure = 2
cam2_ev_bias  = -3.0
cam2_ev_min/max = unset
```

The reason is determinism: you do not yet know whether capture eye adaptation is running. Manual mode avoids shipping an exposure that depends on that unknown. The known-good main view sitting near the −3 floor makes −3 a sensible first fixed-exposure preset.

This is a **starting default, not a value that can be proven from the two JPEGs**. Check the actual shot:

- If the hoodie loses too much detail, raise the bias in 0.5 EV steps: −2.5, then −2.0.
- If large non-emissive surfaces remain clipped, lower it cautiously.
- If you need roughly −4 or less just to make the image usable, investigate the capture/color path rather than continuing to darken the subject.

For diagnosing auto mode, keep `cam2_ev_min/max`. The first useful auto test is:

```text
cam2_exposure = 1
cam2_ev_bias  = 1.0
cam2_ev_min   = -3
cam2_ev_max   = 3
```

That reproduces the level PPV’s stated range instead of assuming the capture inherited the unbound volume. If auto adaptation is demonstrated to work and is desirable for lighting changes, it can then become a tuned preset. Min/max are worth retaining for that reason; they are not needed by the manual default.

Forcing blend weight to 1 in modes 1/2 is correct. Mode 0 must restore the complete originally copied settings and original weight, not merely stop applying the bias.

**Do not change the main camera, lights or unbound PPV.** The main view is the known-good reference.

## 5. Defaults and observability

| Setting | Decision |
|---|---|
| `monitor_feed` | **1 only for a qualified install** with correct 8838/`:103` identity and sidecar gating. For the stack exactly as currently described, effective default **0**. |
| `monitor_fps` | **60 cap**; use **30** as the documented pod fallback if the render-thread soak fails. |
| Playout delay | **750 ms** when the privacy delay is enabled. |
| Public confirmation maximum age | **1.5 s**. |
| Reopen/reconnect discard | **250 ms**, plus epoch/buffer reset. |
| Feed no-progress stale timeout | **1.0 s**. |
| `cam2_exposure` | **2**. |
| `cam2_ev_bias` | **−3.0**, subject to the one-shot visual calibration above. |
| `cam2_ev_min/max` | Unset by default; retained for auto-mode diagnosis/tuning. |

Keep the five-second log, but make its units unambiguous:

- Define `fps` as actual uploaded/shown fps; add FIFO input fps separately.
- Split drops into older-frame, late-playout, epoch/privacy, overflow and decode-error drops.
- Add `epoch`, `confirm_age_ms`, `content_age_ms`, buffered frames/bytes and pending uploads.
- Report decode average and maximum, not only one sample.
- Add upload MiB/s and texture-creation count; a stable texture count is a useful leak check.
- Distinguish `allowed`, `bound`, `stale`, `quarantine` and `source_mismatch` reasons.

Log privacy/gate transitions immediately, rate-limited, rather than waiting for the next five-second line. Receipts should contain requested **and effective** settings, source/display identity, sidecar-gate status, epoch, last gate reason and drop/upload counters—never tokens or frame contents.

[kimi-k3.1-pro · 18537+48837 tokens · 1187.2 s]

## What was applied (install_v22.py, before the code review)

1. Thread model: kept the cam2-style single pump (one task in flight, non-blocking reads); the shared state holds no UObject
   pointers and is kept alive by the task's `TSharedPtr`; gate closure bumps the epoch and clears the parse buffer, the
   playout ring and any decoded-but-not-uploaded frame; a writer that leaves mid-frame is a discontinuity (resync).
2. Parser: kept the marker walk, with tests for every listed case (split SOI/segment header across reads, fill bytes,
   standalone markers, stuffing and RST, SOI inside a frame, oversize, unbounded garbage); added "a reserved marker
   (02..BF) where a marker must be = resync now" so a stray `FF D8 FF` in garbage does not make the reader wait on a bogus
   segment length.
3. Decode: validation before allocation (header size <= 1280x1024, so `W*H*4` cannot overflow), the returned buffer size is
   checked; BGRA8 into an sRGB texture.
4. Upload: opaque black clear of the whole texture at creation (enqueued before the first rect update) AND again whenever the
   source rect changes in the same texture; `SrcPitch` = 1280*4; the pixel buffer stays with the caller when nothing is
   enqueued; a global pending-upload counter (decremented in the RHI cleanup) and the feed skips uploads while 3 are pending
   (`upload_busy`). `monitor_fps` stays a 60 cap; 30 is the documented pod fallback.
5. Binding: one selection `SelectMonitorFrame` (wanted own picture `OwnFrame`, `FeedFrame`, `BoundFrame` to skip redundant
   MID calls) used by every bridge path; `ClearPrivateState` selects the terminal picture at once; the bridge's 0.5 s poll
   timer calls the selection before it can return early (a hung backend), so a closure never depends on the character.
6. Staleness: no-progress (time since the last new upload), not content age; content age is logged separately. Default
   2.0 s as `monitor_stale_s` (the coordinator's later contract with the merged sidecar: above its 0.5 s neutral-frame
   repeat); on fallback the persistent texture is also blanked (it never keeps an old screen).
7. Privacy, option (iii): game-side delayed playout against actual confirmations (`monitor_delay_s` 0.75): a frame is
   decoded only if read >= 0.75 s ago AND before the start of the newest completed validating public confirmation; a ring of
   compressed JPEGs (64 frames / 16 MiB), decode only the selected frame; drops counted by kind. The sidecar gate itself was
   implemented in parallel by another worker and merged as commit 8634ff9 (layout privacy cuts, runner privacy, Vagon
   connected AND phase connected, stale answers, neutral grey frames, a new ffmpeg per open period; the supervisor pins its
   display to the desktop child's): this layer was aligned with it instead of changing the sidecar again.
8. Gate details: kept `PrivacyDesired` and `MonitorMaterial`; the confirming read is validated on arrival and timestamped with
   its start; `FeedSourceConnected`/`PublicConfirmedAt` cleared on `ClearPrivateState` and `EndPlay`; `display.kind` must be
   "graphical"; the epoch is bumped once per transition; 1.5 s confirmation age, 0.25 s reopen quarantine kept.
9. Persistent textures: every slot is a `UPROPERTY` of its owner (`PersistentFrame`, `PersistentImages`,
   `StreamerVisualMonitorTexture`); `Clear()` of the device bridge already binds the blank canvas before emptying `Images`;
   sRGB/NeverStream/filter/clamp set before `UpdateResource`; no `UpdateResource` per frame.
10. Observability: periodic line with fps (uploaded) and in_fps, drops split (older/epoch/overflow/untaken/rejected/
    upload_busy/decode_failed), epoch, confirm_age_ms, content_age_ms, queued frames/KB, pending uploads, decode avg/max,
    upload MiB/s, textures; `..._MONITOR_FEED_GATE` on every transition (at most one line per second, the rest counted);
    receipt with requested and effective settings, gate reason, epoch and counters.

## Not applied, with the reason

- **cam2 default manual exposure at bias -3.** With `AutoExposureApplyPhysicalCameraExposure` off, manual mode fixes the
  exposure at the engine's EV100 base, so the bias is the absolute log2 scale (2^bias). The house's histogram volume pins
  the dim interior at its EV100 -3 floor with bias 1, i.e. a scale of 2^(1+3) = 16 = 2^4 (the same arithmetic as
  `tools/unreal_native_daylight_exposure.py`, "minEV -3 / bias1 caps scale at 16"). Manual -3 would then be 2^-3, about
  7 EV darker than the webcam: a black cam2. The default stays mode 1 (auto + bias) at -1.0, a relative -2 EV shift in every
  eye-adaptation state (adapting, pinned or fixed); manual stays available live (`cam2_exposure` 2, about +4 to match the
  webcam, +2 for two stops darker) and the min/max keys are kept for the auto diagnosis Kimi described. Raised again in the
  code review.
- **`monitor_feed` effective default 0.** The game gate already keeps the feed inert on the current stack (the bridge's
  origin is the old 8832 runner, `pc_mode` chromium) and the sidecar gate is now merged; the compiled default stays 1 so the
  feed works once `SUB01_PC_ORIGIN` is the Vagon runner on 8838, as the brief asks.
- **A separate authenticated 8838 poller in the game.** Not added: the bridge's own origin is the confirmation source and it
  must be the Vagon runner (else `source mismatch`), and the merged sidecar polls 8838 itself with its display pinned by the
  supervisor.
