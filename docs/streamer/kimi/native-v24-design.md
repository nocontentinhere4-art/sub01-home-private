# Kimi design review (2026-10-24): native v24, the offscreen main-view hand-off (spec steps 1-3 and 6)

Model `kimi-k3.1-pro` via `tools/ask_kimi.py` on the pod, `--max-tokens 24000 --timeout 600`, one call at a time. The first, single
question (all three parts at once, with `spec-structural-fix.md` = the "Structural fix" section of `docs/streamer/SAWTOOTH-20261024.md`
attached) failed twice: a read timeout at 600 s, then "max_tokens reached while reasoning" (24k reasoning tokens, no answer). It was
split into three shorter parts; part 1 had the spec section attached. The answers below are verbatim.

## Decisions taken from this review (what changed in install_v24.py)

| Point | Kimi | Decision |
|---|---|---|
| 1.1 fallback `main_source` 1 | defer it, or give it the same go/no-go and a verified provider lifetime | KEPT, selectable (default 0 = the delegate) with its own go/no-go window; lifetime verified in the 5.8.3 source: `FSlateRHIRenderer::OnWindowDestroyed` runs `FlushRenderingCommands()` before `delete ViewportInfo`, so a command enqueued in the same game tick always runs first; the staleness (previous frame) is documented |
| 1.3 null `Held`, ring rebuild, extent change | check null; old readbacks alive or reset; an extent change disables rather than reconfigures | null counted (`NoTexture`); ring readbacks are `Reset()` on a format change (RHI resources are deferred-deleted; nothing waits); a non-1920x1080 back buffer is refused per frame (`dropped_format`) and NO-GO |
| 1.4 no encoder free | leave the ready slot pending, do not drop it as dropped_encode | ADOPTED: the copy stays in its slot (in order); a full ring drops the newest capture (`dropped_slots`); `dropped_encode` = failed encodes only |
| 1.4 the 1 ms copy | render-thread work, must pass the ABBA gates | logged as `copy_ms`; part of the go/no-go build's numbers |
| 1 (missed) A2B10G10R10 | TurboJPEG cannot take packed 10-bit: unpack, check colour against the windowed image | already unpacked on the encoder threads (`>>2` per channel, SDR display-encoded, no tone mapping); the visual check is a go/no-go step (the FIFO probe saves frames) |
| 1/2 sequence | assign at acceptance, exactly one terminal result per sequence | ADOPTED and documented: assigned after the reader and rate gates; each accepted seq ends written or in one drop counter |
| 2.5 alpha 255 | force it | not done for B8G8R8A8: TurboJPEG's BGRA input ignores the 4th byte (A2B10G10R10 input gets 255) |
| 2.7 waits | POLLHUP/POLLNVAL, monotonic deadline, interruptible waits | already so (`FPlatformTime::Seconds` is monotonic; the writer's waits are 100 ms condition waits with the stop flag) |
| 2.9 status | define the fields, PENDING, 0600 temp file | ADOPTED: field meanings in the docstring, `go` = PENDING/GO/NO-GO; the temp file is in the 0700 streamer dir (same as cam2.json) |
| 2.10 go/no-go | raw calls before the gates, independent duplicate/missed criteria, pitch unit, reset on source/format/extent change, non-black from the max channel | ADOPTED: duplicates <= 1 %, missed <= 5 % as separate criteria; `Lock` returns the pitch in PIXELS (5.8.3 `FRHIGPUTextureReadback::Lock(int32& OutRowPitchInPixels, ...)`), compared with 1920; the window re-opens on source/format/extent changes; non-black = a sampled channel > 16 |
| 2.11 auto | resolve after Slate is up, log it | resolved at streamer v2 start (Slate is initialized), logged in the `started` line |
| 2.12 teardown | the join time is not bounded by 20 ms: clear, notify, join, log | ADOPTED: `StopThreads` clears the queues first and logs `SUB01_STREAMER_VISUAL_MAIN_TAP_STOPPED join_ms=` |
| 2.13 probe tool | O_RDONLY|O_NONBLOCK + poll, tolerate EOF, report truncated frames | ADOPTED in `main_fifo_probe.py` (and it refuses when another process already reads the FIFO) |
| 2 (missed) sessions | an output-session generation so stale frames never cross a reconnect | ADOPTED: every open/close bumps the session; frames of another session are dropped (`dropped_noreader`) |
| 2 (missed) second writer's status | a lock-busy process must not overwrite `main.json` | ADOPTED: only the lock holder writes the status |
| 3 cam2 | agree: back-pressure from the reader; do not switch cam2's writer in v24 | cam2 unchanged except `pipe_size` and `full_queued_max_kb` in cam2.json; the reader-timing measurements go to the coordinator |

## Part 1: question (verbatim)

```text
Native v24 (UE 5.8.3 editor build run with -game, Linux, Vulkan SM6, game pinned to 6 cores): hand the main view to the director WITHOUT the X11 present (spec steps attached where relevant). I do the game side. This is PART 1 of 3 of my design review; keep the answer short (at most ~500 words): per point agree/change with the reason, then anything missed.

## A. What I verified in the 5.8.3 engine source (grep only)
1. `FSlateRenderer::OnBackBufferReadyToPresent()` is `DECLARE_TS_MULTICAST_DELEGATE_TwoParams(FOnBackBufferReadyToPresent, SWindow&,
   class ISlateViewportProvider&)` (SlateCore/Public/Rendering/SlateRenderer.h). It is broadcast as the FIRST statement of
   `FSlateRHIRenderer::PresentWindow_RenderThread(FRHICommandListImmediate&, ...)`, which `DrawWindows_RenderThread` calls for every
   drawn window after the Slate RDG graph has executed (render thread). `ISlateViewportProvider::GetBackBufferResource()`
   (Engine/Public/Slate/SlateViewportProvider.h) returns the window's back buffer; its implementation `check(IsInRenderingThread())`.
2. With `-RenderOffScreen` on Linux: `FLinuxPlatformApplicationMisc::CreateApplication` returns the NULL platform application,
   `FNullWindow::IsRenderingOffScreen()` returns true, so `FSlateViewportInfo` creates NO RHI viewport but an `FTextureRHIRef`
   "SlateOffScreenViewportTexture" (ShaderResource|RenderTargetable, initial SRVMask) with `PixelFormat =
   GetViewportPixelFormat()` = `r.DefaultBackBufferPixelFormat`, whose default here is 4 = PF_A2B10G10R10 (the project does not
   override it). `FSlateApplication::bRenderOffScreen` makes Slate draw every window even if not "visible". In PresentWindow the
   texture case skips EndDrawingViewport (no present). So the delegate SHOULD fire once per drawn frame, with the final
   Slate-composited picture (in game mode the scene viewport renders straight into that same Slate texture: FSceneViewport takes
   `ViewportProvider->GetBackBufferResource()` as its render-thread target when it has no separate RT).
3. PixelStreaming2 (this engine) does exactly this: `FVideoProducerBackBuffer` registers on the GAME thread with
   `Renderer->OnBackBufferReadyToPresent().AddSP(...)`, removes it on the game thread in its destructor (skipped when
   `IsEngineExitRequested()`), and in the callback pushes `ViewportProvider.GetBackBufferResource()` to PixelCapture, whose
   same-format copy does `Transition(Src, Unknown, CopySrc)` then `CopyTexture` and leaves the source in CopySrc (Slate's
   PresentWindow transitions Unknown->Present right after the broadcast when needed).
4. The spec's fallback (FCoreDelegates::OnEndFrameRT + the FSceneViewport's render target) does NOT work in this configuration:
   `FSceneViewport::EnqueueEndRenderFrame` SafeRelease()s `RenderTargetTextureRenderThreadRHI` when there is no separate RT, so at
   OnEndFrameRT `GetRenderTargetTexture()` is null.
5. `FRHIGPUTextureReadback::EnqueueCopy` creates its staging texture ONCE from the first source's desc (same format; "assume every
   enqueue uses the same format and size") and does not transition the source. `Lock(int32& OutRowPitchInPixels, int32* OutHeight)`
   -> `MapStagingSurface`, which flushes the RHI thread ONLY if the fence is not ready (we only lock ready slots); on Vulkan the map is
   a persistent pointer, rows tightly packed (pitch = width).
6. The engine JPEG writer (`IImageWrapperModule::CompressImage`) is TurboJPEG `tjCompress2`, TJSAMP_420, TJFLAG_FASTDCT: baseline
   JFIF, full-range YCbCr (cam2 uses it today: 3.5 ms per 720p frame at q85 on a background worker).

## B. My design (please review each item)
1. Path selection key `main_source`: 0 (default) = the back-buffer delegate. 1 = fallback: every game tick enqueues one render
   command carrying `FSlateRenderer::GetViewportProvider(*GameWindow)` (taken on the game thread) and reads its back buffer, i.e. the
   PREVIOUS frame's final picture (render commands are FIFO: frame N-1's Slate draw precedes frame N's command). Same checks for both.
   The provider pointer is only used inside a command enqueued in the same game tick; the renderer deletes a viewport info only after
   FlushRenderingCommands on the game thread. OK, or drop the fallback until the delegate is proven not to fire?
2. Window filter: the game window pointer (`GEngine->GameViewport->GetWindow().Get()`, refreshed each game tick) stored in an atomic and
   compared by address on the render thread, never dereferenced there. Other windows are counted, not captured.
3. Per accepted frame on the render thread: `FTextureRHIRef Held = GetBackBufferResource()`; checks (render thread, extent 1920x1080,
   format in {B8G8R8A8, R8G8B8A8, A2B10G10R10}; anything else = dropped_format + NO-GO); `Transition(Held, Unknown, CopySrc)`;
   `EnqueueCopy(RHICmdList, Held)` into a free slot of a 3-slot ring (none free = dropped_slots); the ring is rebuilt if the extent or
   format changes. The ref is held until EnqueueCopy returns.
4. Ready slots: unlike cam2 (which keeps only the NEWEST ready copy and drops older ones as "busy"), the main tap must not lose frames,
   so EVERY ready slot is processed in sequence order on each call: if fewer than 2 encodes are in flight, lock, copy the rows
   (pitch-aware memcpy, ~8.3 MB, ~1 ms) into a pooled buffer, unlock, queue the job; else dropped_encode. I chose the memcpy on the
   render thread (spec + cam2 pattern; slots are free again at once) over zero-copy (hand the mapped pointer to the encoder and unlock
   later: no 1 ms memcpy, but each slot then stays busy ~2.5-3.5 frames, so 3 slots would drop at 60 fps). Agree?
```

## Part 1: answer (verbatim)

1. **Change: defer fallback 1.** The delegate has a defined post-Slate insertion point; the fallback does not. FIFO makes “previous Slate picture” plausible, but does not guarantee one fresh Slate frame per game tick, so cadence, duplication and staleness still need proof. If retained, give it the same content/cadence go/no-go and preserve provider lifetime through shared ownership or an explicitly verified teardown rule. Otherwise remove it until the delegate actually fails.

2. **Agree, with a teardown condition.** Address-only comparison is suitable for steady-state filtering and avoids render-thread Slate access. The atomic pointer provides no lifetime protection, however: stop capture, unregister on the game thread, and drain render/worker activity before window/renderer destruction. Handle a null game window during startup and shutdown.

3. **Mostly agree.** Check `Held` for null, use the render thread’s immediate command list, and mark the slot busy before enqueueing. Holding the texture reference through `EnqueueCopy` and explicitly transitioning to `CopySrc` are consistent with the cited engine path. Ring rebuild needs one addition: old readbacks must remain alive until their copies complete, or be explicitly discarded/reset; never flush or wait on the render thread merely to rebuild. A fixed 1920×1080 requirement also means an extent change should normally disable capture rather than silently reconfigure output.

4. **Keep the memcpy initially, but change the scheduling policy and justification.** Ordered draining and bounded encode credit are correct. When no encode credit exists, stop at the next ready slot and leave it pending; do not repeatedly count that same frame as `dropped_encode`. If intentional overload dropping is preferred, specify exactly which sequence is discarded and how its readback slot is reset.

   The 1 ms copy is still render-thread work—potentially about 3 ms when draining a backlog—so it must pass the ABBA/frame-time gates, not be assumed free. Also, 7.2 ms is only **0.43 frame at 60 fps**; zero-copy occupancy of 2.5–3.5 frames therefore depends on measured readback readiness and queueing latency, not encode duration alone. A bounded pipeline cannot promise literally zero loss.

**Missed—blocking:** the actual format is **A2B10G10R10**. TurboJPEG cannot consume those packed 10-bit pixels directly. You must either pin and validate an 8-bit back-buffer format or explicitly unpack/swizzle/scale to 8-bit RGB/BGR before JPEG, with colour/gamma checked against the windowed image. Reinterpreting the bytes is wrong, and the conversion cost is absent from the 7.2 ms encode budget. Finally, assign `seq` at capture acceptance and carry it through the ring; readiness/ring order must not become the output sequence accidentally.

## Part 2: question (verbatim)

```text
Native v24 (UE 5.8.3 editor build run with -game, Linux, Vulkan SM6, game pinned to 6 cores): hand the main view to the director WITHOUT the X11 present (spec steps attached where relevant). I do the game side. This is PART 2 of 3 of my design review; keep the answer short (at most ~500 words): per point agree/change with the reason, then anything missed.

(Part 1 covered the engine path: back-buffer delegate on the render thread, 3-slot readback ring, every ready copy oldest-first, render-thread memcpy into pooled buffers.)

## B (continued)
5. Threads: 2 dedicated encoder threads + 1 dedicated writer thread (std::thread + std::mutex/condition_variable, named with
   pthread_setname_np), not the task pool (cam2 on the task pool shows dropped_busy when windowed: background workers starved).
   Encoder: convert to BGRA8 if needed (A2B10G10R10 -> 8 bit by >>2 per channel, R8G8B8A8 swizzle), CompressImage(JPEG, main_quality),
   then rebuild the header: SOI, the JFIF APP0, ONE COM `seq=<n>`, then every other segment up to SOS except APP1..APP15 and COM; check
   SOF0 (baseline) 1920x1080 and the trailing FF D9; a frame failing this = dropped_encode.
6. Ordering: a reorder buffer (<= 2) releases frames to the output queue strictly in sequence order (a failed encode releases its slot
   in the order too). Output queue 2: when full, the OLDEST queued frame is dropped (dropped_queue) to keep latency low. Sequence =
   capture order of accepted frames, so the director sees gaps for every drop.
7. Writer thread: holds `flock(LOCK_EX|LOCK_NB)` on `main.mjpeg.lock` (open O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW 0600) for the tap's
   lifetime (busy = another writer: no output, reason logged, retried every 5 s). FIFO `main.mjpeg` created by the game (mkfifo 0600
   when absent; an existing path that is not this uid's FIFO with no group/other bits = refused, never replaced). No fd: probe
   `open(O_WRONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW)` every 1 s (ENXIO = no reader), fstat re-check, `F_SETPIPE_SZ` to
   /proc/sys/fs/pipe-max-size (best effort, result and F_GETPIPE_SZ logged). SIGPIPE: BLOCKED in the writer thread's own signal mask
   for its lifetime (a broken pipe then returns EPIPE; a pending SIGPIPE is consumed with sigtimedwait) instead of changing the
   process-wide disposition (the engine's handlers stay untouched). Per frame: write in a loop, EAGAIN -> poll(POLLOUT) in <= 20 ms
   slices (stop flag checked between slices), EINTR retried, partial writes resumed; EPIPE/other error/POLLERR/500 ms deadline ->
   close the fd and discard the WHOLE frame (frames_discarded_midwrite if any byte went out, else dropped_noreader or dropped_stalled),
   never resume a tail on a new fd. main_tap 0 closes the fd (the director sees EOF -> placeholder).
8. No reader: no readback, no encode (like cam2's reader gate) EXCEPT one diagnostic readback per second (locked, checksummed, not
   encoded) so the go/no-go and main.json keep format/pitch/checksum without the director. Frames already in flight when the reader
   leaves are counted dropped_noreader.
9. main.json once per second from the game thread (tmp + rename): the spec's fields (sequence, fps, written, dropped_slots,
   dropped_encode, dropped_queue, dropped_noreader, frames_discarded_midwrite, pipe_size, last_write_utc) + schema, native_pid,
   updated_utc, on, reason, reader, source, width/height/pixel_format, quality, target_fps, captured, encoded, dropped_format,
   dropped_stalled, encode_ms (mean, max), readback_ms, kb_per_frame, go (the verdict).
10. Go/no-go line `SUB01_STREAMER_VISUAL_MAIN_TAP_GONOGO verdict=GO|NO-GO reason=...`, decided once after >= 600 render frames with the tap
   on (re-logged if the source changes): fires_per_frame = matched calls / GFrameNumberRenderThread delta within [0.95,1.05], duplicate
   calls in one render frame and missed frames counted, every call on the render thread, extent 1920x1080, known format, pitch >= width
   and rows >= height from Lock, a NON-BLACK checksum (64 sampled pixels, 8-bit RGB, logged as hex + max channel) seen at least once,
   held ref = yes. Plus every 10 s a `SUB01_STREAMER_VISUAL_MAIN_TAP fps=... written=... drops...` line.
11. Tuning keys (own V24 block in the tuning reader): `main_tap` 0/1 (compiled default "auto": resolved once at start to 1 if
   `FSlateApplication::Get().IsRenderingOffScreen()` else 0; the tuning file overrides), `main_fps` 1..60 (default 60; a render-thread
   rate gate with half-a-frame tolerance), `main_quality` 40..95 (default 85), `main_source` 0/1.
12. Lifetime: the character has no EndPlay in the files the installer owns (it lives in native_cinematic_character.inc), so as the
   monitor feed does, teardown is by destruction: the delegate holds the tap via AddSP (weak; the TS broadcast pins it during a call);
   the tap's destructor sets the stop flag, joins the 3 threads (<= ~20 ms), closes the fds, releases the flock, and removes the
   delegate binding when it runs on the game thread and the engine is not exiting (else the dead weak binding stays, harmless).
13. A stdlib Python test reader for the go/no-go (`main_fifo_probe.py`: reads main.mjpeg N seconds, counts frames, distinct/missing
   seq, checks SOF0 1920x1080 baseline and one COM) to be used ONLY while the director does not read the FIFO.
```

## Part 2: answer (verbatim)

Mostly sound; I would change **6, 10 and 12** before sign-off.

**5 — Agree, with guards.** Dedicated threads are justified, but still inherit the six-core affinity. Use a separate image wrapper/compressor per encoder, force output alpha to 255, and make header rebuilding a bounds-checked marker parse through SOS. `>>2` is valid 10→8-bit RGB reduction for SDR; it is not tone mapping.

**6 — Change.** Reorder depth two is sufficient only with bounded encoder input/outstanding work or capture backpressure; depth alone does not prevent overflow. Assign a 64-bit sequence at acceptance and produce exactly one terminal result per sequence. Gaps demonstrate **post-acceptance** drops only—pre-acceptance or rate-gated frames have no sequence to miss.

**7 — Agree.** The thread-local SIGPIPE design is correct. Also handle `POLLHUP|POLLNVAL`, use a monotonic 500 ms deadline, and make the 1 s/5 s waits stop-interruptible. A partial JPEG cannot be retracted: closing the fd and having the reader discard it at EOF is essential.

**8 — Agree.** Treat lock-busy as output-unavailable for gating. On reader loss, drain queued work and discard later encoder completions, accounting for each accepted sequence exactly once. Keep diagnostics outside stream sequence/encoded/written accounting; explicitly define whether they affect `captured`.

**9 — Agree.** Define cumulative versus one-second-window values, and precisely define `sequence` and `fps`; `go` needs `PENDING`. Snapshot without a lock that can stall the game thread. Use a same-directory 0600 temporary file, close it, then rename.

**10 — Change two details.** Frequency must use raw matched delegate calls **before** reader/FPS gates. Make anomalies independent criteria—for example, duplicates `==0`, missed `<=5%`; a net ratio can hide cancellation. If `Lock` pitch is bytes, require at least `1920*4 = 7680` for these four-byte formats, not merely `pitch >= 1920`. Reset the window and non-black evidence on source/format/extent changes; determine non-black from sampled RGB/max-channel, not merely checksum nonzero.

**11 — Agree.** Resolve `auto` only after Slate is initialized, and log the resolved value. Snapshot quality per encode job; drain old-source frames when `main_source` changes.

**12 — Change.** A roughly 20 ms join cannot be guaranteed: JPEG compression may exceed it, and retry sleeps can dominate. Stop intake, clear queues, notify CVs, then join and log actual teardown time. The weak-delegate/conditional-unbind scheme is fine.

**13 — Agree.** Use `O_RDONLY|O_NONBLOCK` plus polling, never `O_RDWR`; tolerate initial EOF and report truncated final frames. Exclusive readership is essential because FIFO readers split bytes.

**Missed:** use an output-session generation so stale frames cannot cross reconnects. If lock-busy represents a second process, prevent it overwriting the active writer’s `main.json`.

## Part 3: question (verbatim)

```text
Native v24 (UE 5.8.3 editor build run with -game, Linux, Vulkan SM6, game pinned to 6 cores): hand the main view to the director WITHOUT the X11 present (spec steps attached where relevant). I do the game side. This is PART 3 of 3 of my design review; keep the answer short (at most ~500 words): per point agree/change with the reason, then anything missed.

## C. cam2 loss (asked to locate it): 59.8 captured, 52-53 written offscreen
Evidence: m3o log (offscreen, 15 min): per 30 s window dropped_no_reader_or_full 196-251 (~7/s), dropped_busy 0-2, dropped_slots 0,
reader=1, encode 3.5 ms, readback 0.45 ms, ~100 KB/frame. cam2.json now (windowed, cam2_fps 30, the director's ffmpeg reading it):
over 20 s dropped_full 6.95/s, dropped_busy 1.04/s, dropped_no_reader 0, written 22 of 30 captured. The writer drops a WHOLE frame
when FIONREAD says the 1 MiB pipe has no room for it (or write() gives EAGAIN); it never waits. AND: during the m3o measurement the
director's ffmpeg was NOT reading cam2 at all (its log: 17:54:06 relaunch "cam2 stopped delivering" -> runs with cam2:false and
layout webcam_only until 18:33); the reader was the director's own FIFO tap draining every 0.1 s (+ its loop overhead). A 1 MiB pipe
holds ~9-10 cam2 frames (~165 ms at 60 fps); a drain later than that drops frames. With ffmpeg reading (now), its cam2 demuxer
logs "Thread message queue blocking" (queue 512) at every run start and the pipe still fills (~7 drops/s). So the loss is FIFO
back-pressure from the reader, not encode or slots. A game-side wait would just move drops to "busy" (one encode in flight, newest
frame only), so I do NOT plan to change cam2's writer in v24; only add `pipe_size` and `full_queued_max_kb` (FIONREAD at the drops)
to cam2.json as evidence. Do you agree, or would you switch cam2 to the v24 writer (thread + poll + 2-frame queue)?
Note for the director side: ffmpeg 6.1.1 decodes all inputs and runs the graph on ONE main thread; a 1080p MJPEG main input
(~4-6 ms decode) plus cam2 720p plus the filter graph plus NVENC may not keep 60 fps steadily, and a 1 MiB pipe holds only ~4
main frames (~65 ms). What should the coordinator measure first?
```

## Part 3: answer (verbatim)

**Diagnosis — agree, with one qualification.** The loss budgets close: at 30 fps, `22 + 6.95 + 1.04 ≈ 30`; offscreen, `52–53 + ~7 ≈ 59.8`. That establishes **full-pipe back-pressure as the dominant proximal cause**, not readback, encoding capacity, or slots. It does **not yet establish why the reader drains poorly**: tap scheduling, ffmpeg’s main loop, and pod scheduling remain candidates. The start-up `Thread message queue blocking` message is consistent with back-pressure, but is not steady-state proof; `512` is not a 512-frame pipe buffer. Also, the residual `dropped_busy ≈ 1/s` is real, albeit secondary.

**Writer — agree: do not switch cam2 for v24.** A two-frame queue adds only **33 ms at 60 fps** or **67 ms at 30 fps**, versus existing pipe buffering of roughly **165 ms at cam2/60** or **330 ms at cam2/30**. `poll()` cannot create reader throughput; it would mainly smooth very short jitter or reclassify losses. Keep the lossy, nonblocking semantics and add your evidence fields. Report actual capacity from `F_GETPIPE_SZ`, and timestamp/rate-limit drop-batch logs so they can be correlated with the reader.

**Coordinator’s first measurement — reader service timing, not average CPU.** For 60 seconds, use one wall-clock timeline to record, per input:

- bytes drained per second and frame/read-completion cadence;
- inter-service gap p50/p95/p99/max;
- writer `dropped_full` timestamps;
- ffmpeg output frame rate/`speed` and output PTS progression.

Starting from empty, a stall exceeding roughly **65 ms on main**, **165 ms on cam2 at 60**, or **330 ms on cam2 at 30** can fill the respective pipe; shorter stalls can do so when it is already partially occupied. This directly distinguishes insufficient sustained drain rate from periodic main-loop stalls.

**Missed / useful controls:**

- With the director stopped, run an always-draining reader such as `cat cam2.fifo >/dev/null` for 60 seconds at fixed capture. Near-zero `dropped_full` would strongly clear the writer; otherwise investigate writer/pod scheduling.
- Then compare ffmpeg **decode-only to null output** against the **full filter/NVENC graph**, using identical live inputs and writer counters. That isolates graph/encode overhead without guessing from averages.
- Monitor the **main FIFO simultaneously**; the same ffmpeg stall can damage main before cam2. Larger pipes or `thread_queue_size` only increase burst tolerance—and potentially latency—not sustainable throughput.
