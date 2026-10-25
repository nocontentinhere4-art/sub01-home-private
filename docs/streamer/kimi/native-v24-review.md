# Kimi pre-commit review (2026-10-24): native v24 (install_v24.py, main_fifo_probe.py, the m5 launcher)

Model `kimi-k3.1-pro` via `tools/ask_kimi.py` on the pod, `--max-tokens 24000 --timeout 600`, one call at a time. The code sent is
what `install_v24.py` generates (cuts of `CPP_METHODS`, the header/include/wiring/tuning/receipt/cam2 edit texts), the probe script,
and the m5 launcher's diff against m3o; it is not repeated here (every attachment, byte for byte, and every raw question/answer file
went to the pod's delivery directory `/workspace/sub01-w-v24/`). Open "find bugs" questions ran out of the 24k reasoning budget even
on a 2.7 KB piece (parts 2 and 2b, pieces 2b1, 6, 7b, 7b2, N1 and the first 7c follow-up below: no answer); each was re-asked as
narrower, targeted questions (at most ~40 lines, "APPROVE or numbered findings") over the same code, and every fix was sent back for a
follow-up. Questions and answers below are verbatim. (The pod's `rv-A.cpp` was regenerated after the part-1 fixes, so it is not the
exact text part 1 saw; N1b covers the changed lines.)

## Decisions taken from this review

| Piece | Kimi | Decision |
|---|---|---|
| 1 Stamp, SOS | a truncated or malformed SOS header is copied verbatim | ADOPTED: `Ls == 6 + 2*Ns`, `Ns` 1..4, the header must end before the EOI; stamp tests 120-123 |
| 1 Checksum | not the FNV-1a 64-bit offset basis | ADOPTED: `14695981039346656037ull` |
| 2a destructor | `GetRenderer()` returns `TSharedRef`, so `if(FSlateRenderer* R=...)` does not compile | REJECTED with engine evidence: 5.8.3 `SlateCore/Public/Application/SlateApplicationBase.h:133` `inline FSlateRenderer* GetRenderer() const`; the engine itself writes `else if (FSlateRenderer* Renderer = FSlateApplication::Get().GetRenderer())` (`WebBrowser/Private/CEF/CEFWebBrowserWindow.cpp:476`) |
| 2a teardown | an in-flight render-thread callback can race the destruction; a binding left at engine exit can call a freed tap | REJECTED with engine evidence: the binding is `AddSP`; `Core/Public/Delegates/DelegateInstancesImpl.h:272` pins `TSharedPtr<UserClass, SPMode> SharedUserObject = this->UserObject.Pin()` for each call and `TSharedPtr` defaults to `ESPMode::ThreadSafe` (`SharedPointerFwd.h:25`), so the destructor never overlaps a call (it may run on the render thread after the last one) and a left binding only finds an expired weak pointer; the main_source 1 command holds a `TSharedPtr`. Written down in a comment in the destructor |
| 2a one-shot threads | `Started`/`Stop` are never reset | KEPT one-shot, documented: `StopThreads` runs in the destructor only |
| 2b-api | all six RHI points confirmed (immediate list, the transition, Lock's pitch in pixels, reuse without Lock, Reset with a copy in flight, A2B10G10R10 on the CPU) | no change (pitch and rows are already checked before the copy) |
| 2b-acct | the five render-thread invariants hold | no change |
| 3a encoder | BUG: the in-flight place was freed when an encode ENDED, so a stalled encode let newer work through, `Done` overflowed, the trim dropped an unreleased frame and ordered release stopped for good | ADOPTED: a sequence's place frees at its RELEASE (`Outstanding.pop_front();EncodeInFlight.fetch_sub(1);`), the `Done` trim is removed (`Done` holds at most `Encoders-1` frames by construction, `static_assert(ReorderMax>=Encoders)`), `Collect` reads `Reader` once per slot. New runtime step 5b stalls one encode for 0.4 s: the old code fails it (`failed 26`, the stream never resumes), the new code resumes in order and gap-free with `dropped_slots` counted |
| 3bc writer | BUG: the 0.5 s deadline was checked only on EAGAIN, not under a trickle of partial writes | ADOPTED: checked before every write |
| own, while testing | after `main_tap` 0 -> 1 the lock retry could wait up to 5 s (the last attempt's timer) | the `main_tap` 0 branch resets the lock and FIFO retry timers; the encode-fail NO-GO step waits for its drops instead of reading them at once (it was timing-dependent) |
| 4 game thread | the fallback command, the window compare, the judge's timing, re-arming, the FIFO checks confirmed | no change |
| 5 status/log | the 29 format specifiers, the JSON setters, the rates, the atomic rename confirmed | no change |
| own, before 7b/7c were sent | (found in a self-review) | the probe: `other_readers` cannot see other users' descriptors (as uid 1001 every root process is invisible): such processes are counted and the probe refuses unless run as root or `--force` (README: run it as root); a cut frame followed by a next SOI still arriving lost that next frame (the cut now keeps the bytes from the cut on); a too-short SOF0 is a contract failure, not an exception; tests added |
| 7a m5 launcher | no blocking issue; the whole suffix of game.log rescanned every 2 s, a partial line holding the marker saved truncated, wall-clock deadlines, no last read after the game ends, `chown` through a planted symlink | ADOPTED in m5 (regenerated from m3o by the same anchored derivation; m3o unchanged, sha256 71f8cd1c...): incremental `log_after` that stops at a line without its newline, `time.monotonic()`, one last read when the game ended, `OUT` must be a plain directory and is chowned with `follow_symlinks=False`. Not changed: game.log is opened for append as root in unreal's directory exactly like m3o does (inherited, out of v24's scope) |
| 7c probe read loop | blocking: the rates ignored the idle time after the last frame, frames completed by one read share their arrival time; lstat-then-open TOCTOU; `--save` followed links and replaced files | ADOPTED: `fps_window` and `seq.unique_fps_window` (first frame to the end of the run), `trailing_idle_ms`, the trailing silence in `longest_read_stall_ms`, `max_frames_per_read` (the README's go/no-go reads the gaps only at 1-2 frames per read); the FIFO is opened first with `O_NOFOLLOW` and checked with `fstat`, the reader scan uses that `(st_dev, st_ino)`; `--save` writes with `O_CREAT|O_EXCL|O_NOFOLLOW` and refuses a linked save directory; tests added |
| 7b1 probe contract check | blocking: not an exact validator on its own (SOS optional, segment lengths unchecked, a huge seq could raise) | ADOPTED: SOI ... EOI, every header length >= 2 and before the EOI, an SOS, exactly one SOF0, seq 1..19 digits (the director's limit), never raises; tests added |
| follow-up after 3a/3bc | both fixes confirmed (`Done` bounded at `Encoders-1` with no drop, no leak of the in-flight count, the deadline covers trickles); the teardown accepted: "pinning prevents callback/destruction overlap" | no change |
| 6a character edits | the forward-declared `TSharedPtr` member, the includes, the tuning and receipt lines confirmed | no change |
| 6b cam2 evidence | confirmed (only a sample at the `exchange(0)` reset can be lost, accepted for an evidence field) | no change |
| follow-up after 7a | the m5 changes confirmed | no change |
| 7b2a, 7b2b probe frame cutter (35 and 32 lines) | APPROVE, APPROVE | no change |
| N1 / N1b Stamp and Checksum after the part-1 fixes | N1 (the whole functions): no answer; N1b (the changed lines quoted): APPROVE | no change |
| N2a, N2b the installer's Python (anchors, EDITS, plan; run, main) | APPROVE, APPROVE | no change |
| 7c-a probe opening | blocking: the other-readers scan is TOCTOU (a reader can open after it) | ADOPTED as far as it can go without a protocol the director would have to honour: the scan is documented as advisory, repeated every 5 s and once before the descriptor is closed; a reader seen at any time gives `exclusive: false` with `other_readers_during_run`, and the README's go/no-go requires `exclusive true`; tested with a reader that opens mid-run |
| 7c-b probe read loop | blocking: at EOF a partial frame stays in the cutter and could be glued to the next writer's frame | ADOPTED: `Walker.drop_partial()` at every EOF (counted as a cut); tested with two writer sessions, the first closing mid-frame |
| 7c-c probe summary | APPROVE | no change |
| 7c-d probe main() | minor: an existing file at `--save` raised a traceback; blocking: the save directory's path checks were TOCTOU | ADOPTED: the directory is opened once with `O_DIRECTORY|O_NOFOLLOW` (created 0700), every frame is written through that descriptor (`dir_fd`, `O_CREAT|O_EXCL|O_NOFOLLOW`), every failure is a JSON refusal with exit 2; tested (a file, a link to a directory) |
| F1 follow-up after 7c-a/7c-b | blocking: `exclusive` true only meant "none observed"; blocking: a close/reopen with no EOF in between could still glue an old partial frame to the next one | ADOPTED: the field is `other_reader_seen` (true voids the run; false = none seen, not proof; the README says exclusivity comes from the procedure); the cutter ends a frame at any later fresh SOI (`FF D8 FF` never occurs inside an encoder's frame), counted as a cut. A test glues a frame cut inside its DQT so that the segment length swallows exactly the next frame's SOI+APP0+COM: without the guard a bogus frame with the OLD seq passed the contract (checked by mutation), with it the new frame comes out whole |
| F2 follow-up after 7c-d | APPROVE | no change |
| F3 follow-up after F1 | APPROVE | no change |

Final state: every piece of the native input (the emitted C++, the installer's apply logic) and of the m5 launcher has an approving
answer on its exact current text (or no finding and no later change); the probe likewise. The cut-by-cut map for the build slice is
`/workspace/sub01-w-v24/build-slice/REVIEW-MAP.txt` on the pod.

## Part 1: the pure helpers

Question (verbatim); attached: the helpers of CPP_METHODS (namespace Sub01MainTap).

```text
Context: UE 5.8.3 game-module C++ (Linux, Vulkan, the game run with -RenderOffScreen), generated by install_v24.py and inserted into the character .cpp. You reviewed the DESIGN earlier: FSlateRenderer::OnBackBufferReadyToPresent (render thread) -> a 3-slot FRHIGPUTextureReadback ring -> 2 encoder threads (FRunnableThread) -> in-order release -> output queue 2 -> 1 writer thread -> the FIFO main.mjpeg; main.json once per second; a go/no-go log line. It compiles against a test stub with g++ and clang++ -Wall -Werror -Wshadow, and a runtime driver (real threads, a real FIFO, a fake engine) passes. Review PART A of 6 for BUGS ONLY: threading/races, lifetime, UE API misuse, POSIX/FIFO semantics, counter accounting, anything that breaks the build on the real engine. Be brief (at most ~400 words): for each issue give where, why, and the fix; then say "no blocking issue" or "blocking: ...".

PART A: the pure helpers (format classification, BGRA8 conversion, checksum, the JPEG header rebuild with the COM seq, pipe-max-size, SIGPIPE).
```

Answer (verbatim):

- **`Stamp`, SOS handling:** `Marker==0xDA` breaks before the common segment-length/bounds checks. A truncated or malformed SOS can therefore be accepted and copied verbatim, provided the overall buffer still ends in `FF D9`, contrary to the stated rejection contract. Read and bounds-check `Ls` before breaking; also validate `Ns`, `Ls == 6 + 2*Ns`, and that the complete SOS header precedes the scan/EOI.

- **`Checksum`:** `1469598103934665603ULL` is not the 64-bit FNV-1a offset basis. Use `14695981039346656037ULL`, or stop describing the checksum as FNV-1a. The current value remains deterministic, so this only matters for algorithm conformance or externally expected hashes.

The RGB10A2 bit extraction, COM length/sequence formatting, and zero-timeout pending-SIGPIPE drain are otherwise correct. `ConsumeSigpipe` depends on the stated writer-side requirement that SIGPIPE already be blocked—or ignored—before the first FIFO write.

**no blocking issue**

`[kimi-k3.1-pro · 2150+21042 tokens · 436.2 s]`

## Part 2 (whole tap class): no answer

Question (verbatim); attached: class FSub01MainTap up to the encoder threads (~9 KB).

```text
Context: UE 5.8.3 game-module C++ (Linux, Vulkan, the game run with -RenderOffScreen), generated by install_v24.py and inserted into the character .cpp. You reviewed the DESIGN earlier: FSlateRenderer::OnBackBufferReadyToPresent (render thread) -> a 3-slot FRHIGPUTextureReadback ring -> 2 encoder threads (FRunnableThread) -> in-order release -> output queue 2 -> 1 writer thread -> the FIFO main.mjpeg; main.json once per second; a go/no-go log line. It compiles against a test stub with g++ and clang++ -Wall -Werror -Wshadow, and a runtime driver (real threads, a real FIFO, a fake engine) passes. Review PART B of 6 for BUGS ONLY: threading/races, lifetime, UE API misuse, POSIX/FIFO semantics, counter accounting, anything that breaks the build on the real engine. Be brief (at most ~400 words): for each issue give where, why, and the fix; then say "no blocking issue" or "blocking: ...".

PART B: the tap class members, constructor/destructor/threads, the render-thread side (delegate callback, Pump, Collect).
```

`[kimi-k3.1-pro · 3199+24000 tokens · 486.8 s]`  
`[no answer: max_tokens reached while reasoning (23997 reasoning tokens); raise --max-tokens]`

## Part 2a: members, runnable, destructor, threads

Question (verbatim); attached: the class members, FSub01MainTapRunnable, ~FSub01MainTap, StartThreads/StopThreads.

```text
Context: UE 5.8.3 game-module C++ (Linux, Vulkan, the game run with -RenderOffScreen), generated by install_v24.py and inserted into the character .cpp. You reviewed the DESIGN earlier: FSlateRenderer::OnBackBufferReadyToPresent (render thread) -> a 3-slot FRHIGPUTextureReadback ring -> 2 encoder threads (FRunnableThread) -> in-order release -> output queue 2 -> 1 writer thread -> the FIFO main.mjpeg; main.json once per second; a go/no-go log line. It compiles against a test stub with g++ and clang++ -Wall -Werror -Wshadow, and a runtime driver (real threads, a real FIFO, a fake engine) passes. Review PART B1 of 6 for BUGS ONLY: threading/races, lifetime, UE API misuse, POSIX/FIFO semantics, counter accounting, anything that breaks the build on the real engine. Be brief (at most ~400 words): for each issue give where, why, and the fix; then say "no blocking issue" or "blocking: ...".

PART B1: the tap class members, the runnable wrapper, destructor, StartThreads/StopThreads.
```

Answer (verbatim):

- **Destructor — real-UE build break:** `FSlateApplication::Get().GetRenderer()` returns `TSharedRef<FSlateRenderer>`, not a nullable raw pointer. `if (FSlateRenderer* Renderer = ...)` therefore does not compile. After the lifecycle checks, use:
  ```cpp
  FSlateApplication::Get().GetRenderer()
      ->OnBackBufferReadyToPresent().Remove(Handle);
  Bound = false;
  ```

- **Destructor/`StopThreads` — render-thread lifetime race:** joining the encoder/writer threads does not quiesce `OnBackBufferReadyToPresent`. Unregistration currently happens last, and removing a delegate does not by itself establish that an invocation already running on the render thread has returned. An in-flight callback can consequently race queue/readback destruction. Moreover, destruction off the game thread—or merely while `IsEngineExitRequested()` is true—skips unregistration entirely; Slate may still be alive and retain a callback referencing the freed tap.  
  **Fix:** provide an explicit game-thread shutdown while Slate/RHI are still valid: disable new intake, unregister the delegate, and flush/fence the render thread so active callbacks and queued readback work have drained; only then join workers and release file descriptors/readback members. Do not treat engine-exit as proof that unregistration is unnecessary. If teardown cannot be dispatched safely, require shutdown earlier and assert in the destructor that `Bound == false`.

- **`StartThreads`/`StopThreads` — permanently one-shot state:** after any stop, `Started` remains true and `Stop` remains set. A later start either returns immediately or, if only `Started` were reset, would create threads that immediately exit. If restart or pre-start `StopThreads()` is supported, reset `Stop` before creation, clear `Started` after joining, and roll back partial thread-creation failures. Otherwise enforce/document destructor-only, one-shot use.

**blocking: unsafe render-thread/Slate teardown, plus the `GetRenderer()` compile error on the real engine.**

`[kimi-k3.1-pro · 1778+13803 tokens · 299.0 s]`

## Part 2b (render-thread side): no answer

Question (verbatim); attached: OnBackBuffer, Pump, ResetRing, Collect, TakeBuffer (~4.7 KB).

```text
Context: UE 5.8.3 game-module C++ (Linux, Vulkan, the game run with -RenderOffScreen), generated by install_v24.py and inserted into the character .cpp. You reviewed the DESIGN earlier: FSlateRenderer::OnBackBufferReadyToPresent (render thread) -> a 3-slot FRHIGPUTextureReadback ring -> 2 encoder threads (FRunnableThread) -> in-order release -> output queue 2 -> 1 writer thread -> the FIFO main.mjpeg; main.json once per second; a go/no-go log line. It compiles against a test stub with g++ and clang++ -Wall -Werror -Wshadow, and a runtime driver (real threads, a real FIFO, a fake engine) passes. Review PART B2 of 6 for BUGS ONLY: threading/races, lifetime, UE API misuse, POSIX/FIFO semantics, counter accounting, anything that breaks the build on the real engine. Be brief (at most ~400 words): for each issue give where, why, and the fix; then say "no blocking issue" or "blocking: ...".

PART B2: the render-thread side: the delegate callback, Pump (gates, ring, transition, copy), ResetRing, Collect (oldest first, lock, copy, queue). The members it uses: Pending/SlotProbe/SlotSeq/SlotOrder/SlotSession/SlotAt[3] and Readback[3] (render thread only), atomics for the counters/knobs, Mutex/JobCv/Jobs/Outstanding/Pool shared with the encoders.
```

`[kimi-k3.1-pro · 1949+24000 tokens · 501.0 s]`  
`[no answer: max_tokens reached while reasoning (23997 reasoning tokens); raise --max-tokens]`

## Piece 2b1 (open question, 2.7 KB): no answer

Question (verbatim); attached: OnBackBuffer and Pump.

```text
Context: UE 5.8.3 game-module C++ (Linux, Vulkan, the game run with -RenderOffScreen), generated by install_v24.py and inserted into the character .cpp. Pipeline (you reviewed the design earlier): FSlateRenderer::OnBackBufferReadyToPresent (render thread) -> a 3-slot FRHIGPUTextureReadback ring -> 2 encoder threads (FRunnableThread) -> in-order release -> output queue of 2 -> 1 writer thread -> the FIFO main.mjpeg; main.json once per second; a go/no-go log line. It compiles against a test stub with g++ and clang++ -Wall -Werror -Wshadow, and a runtime driver (real threads, a real FIFO, a fake engine) passes. Review piece 2b1 of the pre-commit review for BUGS ONLY: threading/races, lifetime, UE API misuse, POSIX/FIFO semantics, counter accounting, anything that breaks the build on the real engine. Do not re-derive the parts not shown; trust the summary. Be brief (at most ~300 words): for each issue where, why, fix; then "no blocking issue" or "blocking: ...".

PIECE 2b1: the render-thread entry: the delegate callback and Pump (call/frame accounting, gates, ring slot, transition, EnqueueCopy). Collect() (next piece) drains finished slots oldest first into encoder jobs; ResetRing() resets every slot and its readback. Members used (declared elsewhere): render-thread only: TUniquePtr<FRHIGPUTextureReadback> Readback[3]; bool Pending[3], SlotProbe[3]; uint64 SlotSeq[3], SlotOrder[3]; uint32 SlotSession[3]; double SlotAt[3]; uint64 NextOrder=1, NextSeq=0; int32 RingKind=-1; double NextAt, ProbeAt, LastCallAt; uint32 LastFrameNumber; bool HaveFrame. Atomics: the knobs On, Source, Quality, PeriodUs, GameWindow (const void*), FifoOk, Stop; the counters (int64); Reader (bool, set by the writer when the FIFO is open), Session (uint32, bumped by the writer at every open and close), EncodeInFlight (int32, non-probe jobs queued or encoding). Under std::mutex Mutex: deque Jobs (JobCv), deque<uint64> Outstanding (sequences in release order), deques Done and Out (OutCv), vector Pool of pixel buffers (max 4). Constants Slots 3, Encoders 2, ReorderMax 2, QueueMax 2, Width 1920, Height 1080.
```

`[kimi-k3.1-pro · 1579+24000 tokens · 485.2 s]`  
`[no answer: max_tokens reached while reasoning (23997 reasoning tokens); raise --max-tokens]`

## Piece 2b-api: the render-thread RHI calls

Question (verbatim); attached: none (the lines are quoted in the question).

```text
Context: UE 5.8.3 game-module C++ on Linux/Vulkan, the game run with -RenderOffScreen (Slate renders the game window into a texture, no swapchain). Pre-commit review of install_v24.py's generated code: the Slate back buffer -> 3-slot FRHIGPUTextureReadback ring (render thread) -> 2 encoder threads -> in-order release -> output queue of 2 -> 1 writer thread -> the FIFO main.mjpeg. It compiles against a stub with g++/clang++ -Wall -Werror -Wshadow and a runtime driver passes. Answer ONLY the numbered questions, each in at most 3 lines, starting with yes/no (or "ok"/"bug"); quote the line for any bug and give the fix. Do not review anything else. End with "no blocking issue" or "blocking: ...".

The render-thread code (in FSlateRenderer::OnBackBufferReadyToPresent, called in FSlateRHIRenderer::PresentWindow_RenderThread
before the present, which offscreen is skipped), per accepted frame:
```
FTextureRHIRef Held=Provider.GetBackBufferResource();            // ISlateViewportProvider&, render thread
FRHICommandListImmediate& RHICmdList=FRHICommandListImmediate::Get();
RHICmdList.Transition(FRHITransitionInfo(Held.GetReference(),ERHIAccess::Unknown,ERHIAccess::CopySrc));
Readback[Free]->EnqueueCopy(RHICmdList,Held.GetReference());     // TUniquePtr<FRHIGPUTextureReadback>, one of 3, created lazily
```
and at the start of every callback (polled, never waited on), oldest slot first:
```
if(Readback[S]->IsReady()){int32 Pitch=0,Rows=0;const uint8* P=static_cast<const uint8*>(Readback[S]->Lock(Pitch,&Rows));
 for(int32 Y=0;Y<1080;++Y)FMemory::Memcpy(Dst+Y*1920*4,P+int64(Y)*Pitch*4,1920*4); Readback[S]->Unlock();}
```
1. Is FRHICommandListImmediate::Get() the right list inside this delegate, and is the copy ordered after Slate's draw of that frame?
2. Transition Unknown->CopySrc before the copy (PixelCapture does the same): can it break Slate's own use of the texture next frame
   (Slate transitions it to RTV/SRV itself when it renders again)?
3. 5.8.3: Lock(int32& OutRowPitchInPixels, int32* OutBufferHeight). Is copying 1920*4 bytes per row at Pitch*4 stride correct for a
   4-byte format (B8G8R8A8 or A2B10G10R10)?
4. A slot whose result is not wanted (a diagnostic probe while encoders are busy) is marked free WITHOUT Lock/Unlock and later reused
   with EnqueueCopy: allowed?
5. On a source-format change the 3 readbacks are destroyed (TUniquePtr::Reset) on the render thread, possibly with a copy in flight:
   safe (the staging texture and fence are ref-counted RHI resources, deferred deletion)?
6. The staging texture is created by the first EnqueueCopy from the source's desc. For PF_A2B10G10R10 (the offscreen default,
   r.DefaultBackBufferPixelFormat 4) on Vulkan: any problem reading it on the CPU (bits: R 9:0, G 19:10, B 29:20, A 31:30)?
```

Answer (verbatim):

1. yes—`Get()` returns the render thread’s immediate list used here; Slate’s draw commands are already enqueued, so the transition/copy execute after that frame’s draw.
2. no—leaving the texture in `CopySrc` does not break reuse; Slate’s next-frame transition to RTV/SRV handles the current RHI state, so no restoration is required.
3. yes—for an actual 1920×1080, four-byte/texel source, `Pitch*4` is the byte stride and `1920*4` the active row size; use actual dimensions/`Rows` if they are not fixed.
4. yes—once `IsReady()` is true, an unwanted result may be discarded without `Lock`/`Unlock`; `Unlock()` only pairs with `Lock()`. Never recycle while the copy is still in flight.
5. yes—provided it is not locked, render-thread `Reset` with only GPU work outstanding is safe: RHI command/resource lifetime and deferred deletion cover the staging texture and fence.
6. no—raw CPU reading is valid; on little-endian Linux each texel is a packed 32-bit word with those fields. It is not BGRA8, so an 8-bit MJPEG path must unpack and convert the 10-bit UNORM RGB.
no blocking issue

`[kimi-k3.1-pro · 961+23565 tokens · 474.5 s]`

## Piece 2b-acct: render-thread accounting

Question (verbatim); attached: OnBackBuffer, Pump, ResetRing, Collect, TakeBuffer.

```text
Context: UE 5.8.3 game-module C++ on Linux/Vulkan, the game run with -RenderOffScreen (Slate renders the game window into a texture, no swapchain). Pre-commit review of install_v24.py's generated code: the Slate back buffer -> 3-slot FRHIGPUTextureReadback ring (render thread) -> 2 encoder threads -> in-order release -> output queue of 2 -> 1 writer thread -> the FIFO main.mjpeg. It compiles against a stub with g++/clang++ -Wall -Werror -Wshadow and a runtime driver passes. Answer ONLY the numbered questions, each in at most 3 lines, starting with yes/no (or "ok"/"bug"); quote the line for any bug and give the fix. Do not review anything else. End with "no blocking issue" or "blocking: ...".

Attached: the render-thread side (Pump = per callback; ResetRing; Collect = drains finished slots oldest first). Check ONLY these
invariants (the rest was reviewed):
1. Every capture accepted WITH a sequence (Pending[S]=true, SlotProbe[S]=false, SlotSeq=++NextSeq) ends in exactly ONE of: a job
   queued (EncodeInFlight+1, Outstanding.push_back(seq), Jobs.push_back), ++DroppedNoReader, ++DroppedFormat (bad map or ResetRing).
   Any path that loses it or counts it twice?
2. Sequences pushed to Outstanding are strictly increasing (collection is oldest first by SlotOrder; a slot left pending when no
   encoder is free blocks the newer ones).
3. Probe slots (SlotSeq 0) never touch EncodeInFlight or Outstanding.
4. When the ring is full (no free slot) the NEW capture is refused before a sequence is assigned (++DroppedSlots), so no gap appears.
5. Any data race: render-thread-only members touched by another thread, or shared state touched outside Mutex/atomics?
```

Answer (verbatim):

1. no — each sequenced slot remains pending or takes exactly one terminal path: queued, `DroppedNoReader`, or `DroppedFormat`; clearing `Pending` prevents recounting.
2. yes — oldest-first collection stops at an unready or encoder-blocked slot, so newer sequences cannot overtake it in `Outstanding`.
3. yes — probes never increment `EncodeInFlight` or push `Outstanding`; both operations are guarded by `!Job.Probe`.
4. yes — the `Free<0` return, including `++DroppedSlots` for non-probes, occurs before the acceptance statement containing `++NextSeq`.
5. no — shown shared containers are mutex-protected and cross-thread state is atomic; slot/ring/readback state remains render-thread-only.
no blocking issue

`[kimi-k3.1-pro · 2040+8811 tokens · 206.2 s]`

## Piece 3a: the encoder threads

Question (verbatim); attached: EncodeLoop.

```text
Context: UE 5.8.3 game-module C++ on Linux/Vulkan, the game run with -RenderOffScreen (Slate renders the game window into a texture, no swapchain). Pre-commit review of install_v24.py's generated code: the Slate back buffer -> 3-slot FRHIGPUTextureReadback ring (render thread) -> 2 encoder threads -> in-order release -> output queue of 2 -> 1 writer thread -> the FIFO main.mjpeg. It compiles against a stub with g++/clang++ -Wall -Werror -Wshadow and a runtime driver passes. Answer ONLY the numbered questions, each in at most 3 lines, starting with yes/no (or "ok"/"bug"); quote the line for any bug and give the fix. Do not review anything else. End with "no blocking issue" or "blocking: ...".

Attached: the encoder loop (2 threads). Shared under Mutex: Jobs (JobCv), Outstanding (sequences in release order, pushed by the
render thread with the job), Done, Out (OutCv), Pool. Check ONLY:
1. Each non-probe job decrements EncodeInFlight exactly once and releases its sequence exactly once, in Outstanding order, a failed
   encode releasing its place with an empty frame (skipped, counted DroppedEncode)?
2. Bounds: Out <= 2 (oldest dropped, DroppedQueue), Done <= 2, Pool <= 4. Any path growing without bound?
3. Stop: no deadlock or lost wake-up (StopThreads sets Stop, clears the queues under Mutex, notify_all on both cvs, then joins)?
4. Any data race: the job's pixel buffer, the counters (std::atomic<int64>, += on atomics), LastChecksum/MaxChannel/NonBlack/JpegOk
   (atomics written by both encoders; diagnostics only)?
5. CompressImage(TArray64<uint8>&, EImageFormat::JPEG, const FImageView&, int32 Quality) on IImageWrapperModule from two threads at
   once: safe (5.8.3 creates a new wrapper per call)?
```

Answer (verbatim):

1. bug — the normal path is correct, including failed empty frames, but `while(int32(Done.size())>ReorderMax){Done.pop_front();++DroppedQueue;}` can erase an unreleased sequence’s only `Done` entry, stranding its `Outstanding` entry forever. Remove the drop and apply the backpressure fix below.
2. bug — Out/Pool are capped at 2/4, but `EncodeInFlight.fetch_sub(1);` before ordered release lets later jobs complete indefinitely while the oldest stalls: Done overflow is reachable and Outstanding can grow without bound. With the existing submission cap of 2, move the decrement immediately after `Outstanding.pop_front()`—before the empty-frame `continue`—and remove/assert the trim; then unreleased work and Done are bounded by 2.
3. ok — `Stop` is in JobCv’s predicate, and notification follows the state change; active encoders finish, then observe `Stop`. No deadlock or lost wake-up is shown, assuming encode calls return and Mutex is released before joining.
4. no — pixels remain exclusively owned until returned to Pool after their last use; atomic `+=`, `++`, and stores are race-free. Diagnostic values may be stale or completion-ordered, but that is not a data race.
5. yes — with the stated 5.8.3 fresh-wrapper-per-call implementation, these calls have independent wrappers, outputs, and pixel views. That engine-source implementation detail cannot be verified from the attached stub/excerpt alone.
blocking: Done overflow can permanently halt ordered release while Outstanding grows indefinitely.

`[kimi-k3.1-pro · 1337+19752 tokens · 420.8 s]`

## Piece 3bc: the writer thread

Question (verbatim); attached: WriterLoop .. ReaderGone, WriteWhole.

```text
Context: UE 5.8.3 game-module C++ on Linux/Vulkan, the game run with -RenderOffScreen (Slate renders the game window into a texture, no swapchain). Pre-commit review of install_v24.py's generated code: the Slate back buffer -> 3-slot FRHIGPUTextureReadback ring (render thread) -> 2 encoder threads -> in-order release -> output queue of 2 -> 1 writer thread -> the FIFO main.mjpeg. It compiles against a stub with g++/clang++ -Wall -Werror -Wshadow and a runtime driver passes. Answer ONLY the numbered questions, each in at most 3 lines, starting with yes/no (or "ok"/"bug"); quote the line for any bug and give the fix. Do not review anything else. End with "no blocking issue" or "blocking: ...".

Attached: the writer thread (loop, flock, FIFO open/close, reader-gone check) and WriteWhole. Fd/LockFd are writer-thread only (the
destructor touches them after joining). Check ONLY:
1. Linux FIFO: open(O_WRONLY|O_NONBLOCK) fails with ENXIO when no reader; after the reader closes, poll() on the write end reports
   POLLERR; write() gives EPIPE (SIGPIPE blocked in this thread by pthread_sigmask, the pending one consumed by sigtimedwait with a
   zero timeout). Correct?
2. flock(LOCK_EX|LOCK_NB) on a 0600 regular file opened O_RDWR|O_CREAT|O_NOFOLLOW, released by close(): correct, and EWOULDBLOCK
   when another process holds it?
3. Session/Reader ordering against the render thread: OpenFifo does Session.fetch_add(1) then Reader.store(true); the render thread
   checks Reader, then records Session at acceptance; the writer drops a frame whose Session differs. Can a frame captured before a
   reconnect be written after it?
4. WriteWhole: every frame ends in exactly one of Written, DiscardedMidwrite (some bytes sent), DroppedStalled (deadline, nothing
   sent), DroppedNoReader; the 0.5 s deadline bounds the call (poll slices <= 20 ms, EINTR handled)?
5. Any loop in the writer that can spin without waiting, or block longer than ~0.6 s with Stop set?
```

Answer (verbatim):

1. yes — assuming the last reader has closed: `ENXIO`, `POLLERR`, and `EPIPE` are correct; blocked thread-directed `SIGPIPE` becomes pending and zero-timeout `sigtimedwait` can consume it.
2. yes — `close()` releases the lock here once this open file description has no remaining references; `LOCK_EX|LOCK_NB` contention fails with `EWOULDBLOCK`.
3. no — for a `CloseFifo`/`OpenFifo` reconnect, an earlier acceptance retains an older `Session`; the epoch advances before `Reader` enables new captures, so the writer drops it.
4. bug — terminal accounting is exclusive, but 0.5 s does not bound the whole call.  
   `"if(N>0){Sent+=int64(N);continue;}"`: repeated successful partial writes bypass the deadline check.  
   Fix: immediately after the `Stop` check, insert `if(FPlatformTime::Seconds()>=Deadline){Why=3;break;}`.
5. no — idle waits are ≤100 ms and poll slices ≤20 ms; FIFO writes and `flock` are nonblocking, and `Stop` is checked each write iteration, so no empty busy-spin or >~0.6 s Stop-set wait.

blocking: `WriteWhole` does not enforce its total 0.5 s deadline under continued partial-write progress.

`[kimi-k3.1-pro · 2486+21204 tokens · 457.8 s]`

## Piece 4: the game thread (start, update, arm, judge)

Question (verbatim); attached: StartStreamerVisualMainTap .. JudgeStreamerVisualMainTap.

```text
Context: UE 5.8.3 game-module C++ on Linux/Vulkan, the game run with -RenderOffScreen (Slate renders the game window into a texture, no swapchain). Pre-commit review of install_v24.py's generated code: the Slate back buffer -> 3-slot FRHIGPUTextureReadback ring (render thread) -> 2 encoder threads -> in-order release -> output queue of 2 -> 1 writer thread -> the FIFO main.mjpeg. It compiles against a stub with g++/clang++ -Wall -Werror -Wshadow and a runtime driver passes. Answer ONLY the numbered questions, each in at most 3 lines, starting with yes/no (or "ok"/"bug"); quote the line for any bug and give the fix. Do not review anything else. End with "no blocking issue" or "blocking: ...".

Attached: the game-thread side: Start (once), Update (every tick), Arm, Judge (go/no-go). The tap is MakeShared<FSub01MainTap>()
(thread-safe); its OnBackBuffer/Pump run on the render thread. Verified in 5.8.3: FSlateApplicationBase::GetRenderer() returns
FSlateRenderer*; FSlateApplication::IsRenderingOffScreen() exists; FSlateRHIRenderer::OnWindowDestroyed runs FlushRenderingCommands()
before deleting the viewport info that GetViewportProvider returns; SP delegate bindings pin the object for each call. Check ONLY:
1. The main_source 1 fallback: ENQUEUE_RENDER_COMMAND capturing a raw ISlateViewportProvider* (taken on the game thread this tick)
   and a TSharedPtr to the tap: safe given the flush above?
2. GEngine->GameViewport->GetWindow().Get() stored as an atomic const void* and compared on the render thread against the SWindow&
   of the callback: any problem (only compared, never dereferenced)?
3. The judge's wait condition and the order of reasons: can it judge too early (before 600 render frames when calls arrive) or never
   (with no calls: 30 s; with calls: 120 s at most)?
4. Re-arming on a change of the (format, extent) shape, source or switch-on: any way to re-arm every tick (no verdict ever)?
5. mkfifo/lstat checks at start (refuse a non-FIFO, a foreign owner or group/other bits; never replace the path): correct?
```

Answer (verbatim):

1. yes — For the stated destruction path, the flush drains the already-enqueued command before provider deletion; captured `Self` also keeps the tap alive.
2. no — The atomic avoids a data race, and comparing the address without dereferencing it creates no use-after-free; a stale value only affects identity filtering until refreshed.
3. no erroneous early/never case — Ordinary multi-call, render-thread runs wait for 600 frames, subject to the black/readable hold, or 120 s; `Calls<=1`/`Wrong>0` are explicit 30-second failure exits, and the reason order prevents those cases reaching GO.
4. no — With stable on/source/shape, `StreamerVisualMainShape=Shape` and the latched armed state prevent repeated arming; only genuine per-tick oscillation of those inputs can continually postpone a verdict.
5. yes — `lstat` rejects symlinks/non-FIFOs, and the uid/`0077` checks fail closed; creation uses `0600`, and no branch unlinks or replaces an existing path.

no blocking issue

`[kimi-k3.1-pro · 3071+15503 tokens · 325.6 s]`

## Piece 5: main.json and the log line

Question (verbatim); attached: WriteStreamerVisualMainStatus, LogStreamerVisualMainTap.

```text
Context: UE 5.8.3 game-module C++ on Linux/Vulkan, the game run with -RenderOffScreen (Slate renders the game window into a texture, no swapchain). Pre-commit review of install_v24.py's generated code: the Slate back buffer -> 3-slot FRHIGPUTextureReadback ring (render thread) -> 2 encoder threads -> in-order release -> output queue of 2 -> 1 writer thread -> the FIFO main.mjpeg. It compiles against a stub with g++/clang++ -Wall -Werror -Wshadow and a runtime driver passes. Answer ONLY the numbered questions, each in at most 3 lines, starting with yes/no (or "ok"/"bug"); quote the line for any bug and give the fix. Do not review anything else. End with "no blocking issue" or "blocking: ...".

Attached: main.json (once per second) and the periodic log line (every 10 s), game thread. Check ONLY:
1. Every UE_LOG format specifier against its argument type (int64 via static_cast<long long> -> %lld, uint64 -> %llu, int32 -> %d,
   double/float -> %f/%.Nf, TCHAR* -> %s, FString via * -> %s). Any mismatch (a build error under -Werror=format or garbage)?
2. FJsonObject setters: SetNumberField(const FString&, double) given int32/int64/float arguments; SetBoolField; SetStringField
   with TCHAR*/FString: any ambiguity or narrowing that breaks the build?
3. The windowed rates (fps over the time since the last write; totals minus the previous totals): correct, no division by zero?
4. std::rename after FFileHelper::SaveStringToFile to a .tmp in the same directory: atomic replace?
```

Answer (verbatim):

1. ok — all 29 specifiers match their arguments: integer casts fit `%lld/%llu/%llx`, `%d` receives `int` or promoted values, floating arguments are `double`, and `%s` receives TCHAR strings.
2. ok — numeric arguments convert legally to `double`, boolean conversions are valid, and `TCHAR*`/`FString` arguments bind to `SetStringField`; no ambiguity or build-breaking narrowing.
3. ok — deltas use current totals minus previous bases; status requires `Now > WindowAt`, logging clamps `Span` to `>= 1e-3`, and `D[3]` is guarded before division.
4. yes — on Linux/POSIX, a successful same-directory `std::rename` atomically replaces `main.json`; opens observe the old or new file, not a partially renamed destination.
no blocking issue

`[kimi-k3.1-pro · 2369+11819 tokens · 225.1 s]`

## Piece 6 (other edits, both halves): no answer

Question (verbatim); attached: header fields, includes, wiring, tuning, receipt; the cam2 edits.

```text
Context: UE 5.8.3 game-module C++ on Linux/Vulkan, the game run with -RenderOffScreen (Slate renders the game window into a texture, no swapchain). Pre-commit review of install_v24.py's generated code: the Slate back buffer -> 3-slot FRHIGPUTextureReadback ring (render thread) -> 2 encoder threads -> in-order release -> output queue of 2 -> 1 writer thread -> the FIFO main.mjpeg. It compiles against a stub with g++/clang++ -Wall -Werror -Wshadow and a runtime driver passes. Answer ONLY the numbered questions, each in at most 3 lines, starting with yes/no (or "ok"/"bug"); quote the line for any bug and give the fix. Do not review anything else. End with "no blocking issue" or "blocking: ...".

Attached: the other edits. (a) Character header fields (UCLASS, plain non-UPROPERTY members) incl. TSharedPtr<class FSub01MainTap>
(the class is defined later in the .cpp; the tap is created with MakeShared there); includes added to the .cpp; the start/tick wiring;
the tuning keys (Field(name, float&, min, max)); the receipt (after the class definition). (b) Four one-line evidence edits in the
EXISTING cam2 writer (the parts marked V24 are new): two atomics in its pipe object; the F_GETPIPE_SZ result stored at open; the max
FIONREAD level seen at a full-pipe drop (writer thread); two new cam2.json fields read by the game thread (the max reset by exchange).
Check ONLY:
1. Anything that breaks the build on the real engine or UHT (a forward-declared class in TSharedPtr as a UCLASS member destroyed in
   the class's destructor; includes; the anchors' surroundings)?
2. The cam2 edits: a race or wrong value (load-then-store max from one writer thread, exchange(0) from the game thread)?
3. The receipt and tuning lines: any type or semantic problem?
```

`[kimi-k3.1-pro · 2128+24000 tokens · 482.0 s]`  
`[no answer: max_tokens reached while reasoning (23997 reasoning tokens); raise --max-tokens]`

## Piece 6a: the character edits

Question (verbatim); attached: header fields, includes, wiring, tuning, receipt.

```text
Context: UE 5.8.3 game-module C++ on Linux (pre-commit review of install_v24.py, the main-view tap of an offscreen game). Answer ONLY the numbered questions, each in at most 3 lines, yes/no first; quote the line for any bug and give the fix. End with "no blocking issue" or "blocking: ...".

Attached: (a) fields added to the character class header (a UCLASS; plain non-UPROPERTY members), among them `TSharedPtr<class FSub01MainTap> StreamerVisualMainTap;` where FSub01MainTap is a plain C++ class DEFINED LATER in the .cpp (the tap is created there with MakeShared<FSub01MainTap>()); (b) the includes added to the .cpp; (c) the start and tick wiring lines; (d) the tuning keys (Field(name, float&, min, max) clamps a float); (e) receipt lines placed after the class definition. 1. Does a TSharedPtr to a type that is incomplete in the header compile and destroy correctly when the UCLASS is destroyed (UHT-generated code, the implicit destructor)? 2. Are the includes right for 5.8.3 (Framework/Application/SlateApplication.h, Rendering/SlateRenderer.h, Slate/SlateViewportProvider.h, Widgets/SWindow.h, Engine/GameViewportClient.h, HAL/Runnable.h, HAL/RunnableThread.h) and are the C/POSIX headers enough for poll() and flock()? 3. Any type problem in the tuning and receipt lines?
```

Answer (verbatim):

1. **Yes—provided `MakeShared` occurs after the full definition.** `TSharedPtr` destroys through a type-erased reference controller, so UHT-generated code and the implicit UCLASS destructor need no complete type; the last owner destroys the tap.
2. **Yes for the uses stated.** Those are the appropriate public UE 5.8.3 paths; on Linux `<poll.h>` provides `poll`/`pollfd`, and `<sys/file.h>` provides `flock`/`LOCK_*`.
3. **No.** The tuning values bind to `float&`, bounds convert normally, and `SetNumberField` accepts `double`, making the shown loads/casts valid; the bool and `FString` calls also match.

no blocking issue

`[kimi-k3.1-pro · 1594+14798 tokens · 268.0 s]`

## Piece 6b: the cam2 evidence edits

Question (verbatim); attached: the four cam2 lines.

```text
Context: UE 5.8.3 game-module C++ on Linux (pre-commit review of install_v24.py, the main-view tap of an offscreen game). Answer ONLY the numbered questions, each in at most 3 lines, yes/no first; quote the line for any bug and give the fix. End with "no blocking issue" or "blocking: ...".

Attached: four one-line edits in the EXISTING cam2 FIFO writer (each line replaces its anchor line; only the parts marked V24 are new). The cam2 writer runs on its own thread; it checks the pipe room with FIONREAD before each whole frame (Known = the ioctl worked, Queued = bytes in the pipe) and drops the whole frame when it does not fit (DroppedFull). cam2.json is written by the game thread once per second. 1. FullQueuedMax: load-then-store max from the one writer thread, exchange(0) from the game thread: any race that gives a wrong value beyond losing one sample at the reset? 2. PipeSizeSeen.store(PipeBytes) at open and its load in the status: correct? 3. The F_SETPIPE_SZ/F_GETPIPE_SZ line: any behaviour change for cam2 (it is the same call as before plus the store)?
```

Answer (verbatim):

1. No. With one writer, no stale store can overwrite a newer writer maximum; only the in-flight sample at `exchange(0)` can suffer the accepted reset-boundary loss/misattribution. Exact interval attribution would need writer/reset synchronisation—CAS alone would not fix that.
2. Yes. On the existing valid-fd/`F_GETPIPE_SZ` path, this atomically publishes the actual capacity in bytes—which may differ from 1,048,576—and the status load needs no extra ordering.
3. No. The fcntl sequence and `PipeBytes` assignment are unchanged; the once-per-open atomic store only feeds `cam2.json` and does not affect cam2 writes, room tests, or drops.

no blocking issue

`[kimi-k3.1-pro · 886+15725 tokens · 273.7 s]`

## Piece 7a: the m5 launcher

Question (verbatim); attached: the first m5 diff against m3o.

```text
Context: the native v24 work (offscreen game, main view to the director through the FIFO main.mjpeg). Pre-commit review, PIECE 7a: m5.diff, the new game launcher launch-streamer-game-20261024m5.py derived from the m3o launcher (m3o itself is never edited): its own output directory (created 0755 and chowned to the game user like m3o's), a docstring line, and a bounded wait (3 then 5 minutes) for the v24 start and go/no-go log lines, searched only in the part of the appended game.log written by this launch (byte offset taken before the launch), recorded in status.json. Answer ONLY: 1. can a wait hang or miss a line (log rotation/truncation, a partial last line)? 2. any file-handling or permission problem on a shared pod? 3. anything else that breaks the launcher? Each in at most 3 lines; end with "no blocking issue" or "blocking: ...".
```

Answer (verbatim):

1. With an append-only regular log, waiting is normally ≤3+5 minutes plus the active rescan; that scan and wall-clock `time.time()` prevent a hard bound. Rotation/truncation can invalidate the offset, and child exit can skip a final scan. Split partial lines are reread, but a fragment already containing the marker can be saved truncated.
2. No functional permission failure when run as root: unreal owns `OUT`, and the child writes through the inherited fd. On a shared writable path, symlink-following `chown`/append and `exists()`→`stat()` are unsafe/racy; `exist_ok=True` also leaves an existing directory’s mode unchanged.
3. No other m5-specific launcher breakage is visible. Repeated whole-suffix rescans are the performance concern; marker spellings/timings and external rotation cannot be verified here.

no blocking issue

`[kimi-k3.1-pro · 1687+19972 tokens · 429.2 s]`

## Piece 7b (probe, both halves): no answer

Question (verbatim); attached: main_fifo_probe.py up to the Walker class, the Walker class.

```text
Context: main_fifo_probe.py, a stdlib reader used for the v24 go/no-go while the director does NOT read the FIFO (run as root on the pod). Attached: the first part (the other-readers /proc scan, the per-frame contract check) and the incremental frame cutter (Walker). Answer ONLY, each in at most 3 lines: 1. can the cutter lose the frame after a cut frame or garbage, or loop without progress, or buffer without bound? 2. is the contract check right for SOI, JFIF APP0 first, one COM "seq=<n>" second, no other APPn/COM, baseline SOF0 1920x1080 (frames given to it are whole, SOI to EOI)? 3. the /proc scan: O_RDONLY/O_RDWR from fdinfo flags (octal), unlisted processes counted: correct? End with "no blocking issue" or "blocking: ...".
```

`[kimi-k3.1-pro · 2349+24000 tokens · 505.7 s]`  
`[no answer: max_tokens reached while reasoning (23997 reasoning tokens); raise --max-tokens]`

## Piece 7b1: the probe's reader scan and contract check

Question (verbatim); attached: other_readers, check_contract.

```text
Context: main_fifo_probe.py, a stdlib Python reader used for a go/no-go while nobody else reads the FIFO main.mjpeg (whole baseline JPEGs back to back, each with one COM "seq=<n>"; the writer may cut a frame mid-way, close, and later start again with a fresh SOI). Answer ONLY the numbered questions, each in at most 3 lines, yes/no first; quote the line for any bug and give the fix. End with "no blocking issue" or "blocking: ...".

Attached: other_readers (the /proc scan, run as root) and check_contract (frames given to it are whole, SOI to EOI). 1. other_readers: reading O_RDONLY/O_RDWR from the octal "flags:" line of /proc/<pid>/fdinfo/<fd>, matching the FIFO by (st_dev, st_ino) of os.stat on /proc/<pid>/fd/<fd>, counting a PermissionError on listing a process's fd directory as unchecked: correct? 2. check_contract: does it accept exactly SOI, a JFIF APP0 first, one COM "seq=<digits>" second, no other APPn/COM, baseline SOF0 1920x1080, and can a malformed frame raise instead of returning (False, ...)?
```

Answer (verbatim):

1. Yes — as a non-atomic snapshot: `os.stat(fd)` follows the procfd link, octal `flags` plus `(flags & os.O_ACCMODE) in (os.O_RDONLY, os.O_RDWR)` is correct, and listing `PermissionError` is correctly counted as `unchecked`; concurrent/later opens remain possible.
2. No, even granting whole SOI…EOI input; and yes — `if marker == 0xDA: break` makes SOS optional and skips later APPn/COM, while `pos += 2 + length` follows unchecked lengths; fix: reject `length < 2`/overruns, require SOS and one valid SOF0, and parse through EOI to enforce the whole-frame ban.
   `seq = int(body[len(COM_PREFIX):])` can raise `ValueError` beyond Python 3.11+’s default 4,300-digit conversion limit; fix: catch `ValueError` or enforce a documented digit limit, returning `(False, None, 'bad seq')`.
blocking: `check_contract` is not an exact validator and malformed input can escape its `(False, ...)` path.

`[kimi-k3.1-pro · 1323+23854 tokens · 445.6 s]`

## Piece 7b2 (the probe's frame cutter, open question): no answer

Question (verbatim); attached: the Walker class.

```text
Context: main_fifo_probe.py, a stdlib Python reader used for a go/no-go while nobody else reads the FIFO main.mjpeg (whole baseline JPEGs back to back, each with one COM "seq=<n>"; the writer may cut a frame mid-way, close, and later start again with a fresh SOI). Answer ONLY the numbered questions, each in at most 3 lines, yes/no first; quote the line for any bug and give the fix. End with "no blocking issue" or "blocking: ...".

Attached: the Walker class (an incremental frame cutter: feed(data) returns the whole frames found; .cuts, .garbage, .buffer). 1. Can it lose the frame that follows a cut frame or garbage (including when the next SOI is still arriving)? 2. Can it loop without progress, or keep an unbounded buffer when only garbage arrives? 3. Are the header walk (segments by length up to SOS) and the entropy scan (FF00 stuffing, RST0-7 skipped, FFD9 ends, any other marker = a cut) right?
```

`[kimi-k3.1-pro · 1085+24000 tokens · 557.2 s]`  
`[no answer: max_tokens reached while reasoning (23997 reasoning tokens); raise --max-tokens]`

## Piece 7c: the FIFO probe, read loop and summary

Question (verbatim); attached: main_fifo_probe.py from percentile() to the end.

```text
Context: main_fifo_probe.py, a stdlib reader used for the v24 go/no-go while the director does NOT read the FIFO (run as root on the pod). Attached: the second part: the read loop (O_RDONLY|O_NONBLOCK + poll, never creates the FIFO, bounded by --seconds), the summary, --save, main(). Walker.feed(data) returns a list of whole frames (bytes) and keeps .cuts/.garbage/.buffer; check_contract(frame) returns (ok, seq or None, reason); other_readers(path) returns (pids, unchecked). Answer ONLY, each in at most 3 lines: 1. can the loop hang or spin (no writer yet, writer gone = EOF, EAGAIN)? 2. are the fps, sequence (missing, out of order, unique fps) and arrival-gap numbers right? 3. any unsafe file handling? End with "no blocking issue" or "blocking: ...".
```

Answer (verbatim):

1. For finite `--seconds`, no normal FIFO hang/busy-spin: nonblocking reads, ≤100 ms polls, 50 ms EOF sleeps, and EAGAIN returning to poll cover all three cases; processing/`--save` I/O is outside that guarantee.
2. Not as reliable cadence metrics: frames sharing a read get identical timestamps/zero gaps, while first→last timing ignores leading/trailing idleness—two frames 33 ms apart followed by 29 s idle still report ≈30 fps and a 33 ms maximum gap.  
   For unit-step, nonwrapping sequences, `missing` counts internal holes correctly; `<=` also counts duplicates as non-increasing. `unique_fps` has the same timing flaws.
3. `lstat`→`open` is TOCTOU; open first and verify with `fstat`. `write_bytes` follows symlinks and truncates predictable existing targets, unsafe as root unless the save tree is trusted; otherwise use dirfd-based no-clobber/no-symlink opens.
blocking: make go/no-go rates and stall accounting cover the full observation window, including the trailing idle period; per-read gaps cannot establish true per-frame arrival cadence.

`[kimi-k3.1-pro · 1802+17579 tokens · 311.0 s]`

## Follow-up: the probe's read loop after piece 7c (whole): no answer

Question (verbatim); attached: save_frame, probe, main (after the changes).

```text
Context: main_fifo_probe.py, a stdlib Python reader for a go/no-go while nobody else reads the FIFO main.mjpeg (run as root). In piece 7c you found: the rates ignored the idle time after the last frame (a writer that stopped early still looked fine); frames completed by one read share an arrival time; lstat-then-open was a TOCTOU; --save followed links and replaced files. Attached: save_frame, probe and main after the changes: the FIFO is opened first with O_NOFOLLOW and checked with fstat, the reader scan uses the opened FIFO's (st_dev, st_ino); new fps_window and seq.unique_fps_window (first frame to the END of the run), trailing_idle_ms, the trailing silence in longest_read_stall_ms, max_frames_per_read (the go/no-go reads the gaps only when it is 1-2); --save uses O_CREAT|O_EXCL|O_NOFOLLOW and refuses a save directory that is a link. Answer ONLY, each in at most 3 lines, yes/no first: 1. Are those points fixed? 2. Can the fd leak or the run hang on any refusal path? 3. Anything new that is wrong? End with "no blocking issue" or "blocking: ...".
```

`[kimi-k3.1-pro · 2389+24000 tokens · 462.4 s]`  
`[no answer: max_tokens reached while reasoning (23997 reasoning tokens); raise --max-tokens]`

## Follow-up: the probe's contract check after piece 7b1

Question (verbatim); attached: check_contract (after the change).

```text
Context: main_fifo_probe.py (a stdlib go/no-go reader of the FIFO main.mjpeg). In piece 7b1 you found check_contract was not an exact validator: SOS optional, segment lengths unchecked, a huge seq could raise. Attached: check_contract after the change: SOI...EOI required; every header segment length >= 2 and ending before the EOI; an SOS required; exactly one SOF0; seq 1..19 digits; it never raises. The entropy data is left to the frame cutter (which cuts a frame at any marker other than RST0-7 or EOI, so no APPn/COM can follow SOS in a frame it returns). Answer ONLY, each in at most 3 lines, yes/no first: 1. Are those points fixed? 2. Can any input still raise or be accepted while breaking the contract (SOI, JFIF APP0 first, one COM "seq=<n>" second, no other APPn/COM, baseline SOF0 1920x1080, EOI)? End with "no blocking issue" or "blocking: ...".
```

Answer (verbatim):

1. Yes. SOI/EOI, segment bounds, mandatory SOS, exactly one dimension-matching SOF0, and bounded digit-only `seq` conversion are all enforced; indexing is guarded.

2. No. For `bytes` frames returned by the stated cutter, no contract-breaking acceptance or exception path remains; post-SOS APPn/COM are outside its output domain.

no blocking issue

`[kimi-k3.1-pro · 1180+12255 tokens · 229.5 s]`

## Piece 7b2a: the frame cutter, feed (35 lines)

Question (verbatim); attached: Walker: the class header, _soi, feed.

```text
Context: main_fifo_probe.py, a stdlib Python reader for a go/no-go of the FIFO main.mjpeg while nobody else reads it (run as root on a shared pod). The writer (a game) writes whole baseline JPEGs (SOI ... EOI, a COM "seq=<n>" each) back to back and may cut a frame mid-way, close, and later start again with a fresh SOI. Attached: the frame cutter's class header, _soi and feed(data) -> list of whole frames (.cuts, .garbage, .buffer). _walk() (not attached) returns (end, True) for a whole frame, (cut position >= 2, False) for a cut frame, (None, False) when more bytes are needed. Check: no lost frame after a cut or garbage (also when the next SOI's bytes are still arriving), progress in every loop, a bounded buffer when only garbage arrives.
Review ONLY the attached lines for bugs. Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

APPROVE

`[kimi-k3.1-pro · 774+23359 tokens · 422.0 s]`

## Piece 7b2b: the frame cutter, _walk (32 lines)

Question (verbatim); attached: Walker._walk.

```text
Context: main_fifo_probe.py, a stdlib Python reader for a go/no-go of the FIFO main.mjpeg while nobody else reads it (run as root on a shared pod). The writer (a game) writes whole baseline JPEGs (SOI ... EOI, a COM "seq=<n>" each) back to back and may cut a frame mid-way, close, and later start again with a fresh SOI. Attached: the frame cutter's _walk(): header segments by length up to SOS, then the entropy scan (FF 00 and FF D0..D7 skipped, FF D9 ends the frame, FF + anything else = a cut at that FF, a trailing FF waits). Returns (end, True), (cut position, False) or (None, False). Check the bounds and the returned positions.
Review ONLY the attached lines for bugs. Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

APPROVE

`[kimi-k3.1-pro · 731+19447 tokens · 424.1 s]`

## Native follow-up N1: Stamp and Checksum after the part-1 fixes (whole functions): no answer

Question (verbatim); attached: Checksum, Stamp.

```text
Context: UE 5.8.3 game-module C++ emitted by install_v24.py (the main-view tap of an offscreen game). In part 1 you found: (a) Stamp broke out at SOS before the common length/bounds checks, so a truncated or malformed SOS could be copied verbatim; (b) the checksum used a wrong FNV-1a 64-bit offset basis. Attached: Checksum and Stamp after the fixes (SOS: Ls == 6 + 2*Ns, Ns 1..4, the SOS header must end before the final EOI; basis 14695981039346656037ull). Stamp rebuilds a TurboJPEG baseline header as SOI, the first APP0 if it is first, ONE COM "seq=<n>", then DQT/SOF0/DHT/DRI in order, dropping APPn/COM, refusing anything else, and copies the scan verbatim; it reports SOF0's width/height. Review ONLY the attached code for bugs.
Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

`[kimi-k3.1-pro · 1411+24000 tokens · 468.7 s]`  
`[no answer: max_tokens reached while reasoning (23997 reasoning tokens); raise --max-tokens]`

## Native follow-up N1b: the changed Stamp/Checksum lines

Question (verbatim); attached: none (the lines are quoted).

```text
Context: UE 5.8.3 game-module C++ emitted by install_v24.py. In part 1 you reviewed the JPEG header rebuild `Stamp` and the `Checksum` and found: (a) `Marker==0xDA` broke out before the length/bounds checks, so a truncated or malformed SOS could be copied verbatim; (b) the FNV-1a 64-bit offset basis was wrong. Everything else in part 1 had no finding. These are the changed lines only, verbatim (In = the JPEG bytes, N = its size, already checked to start FF D8 and end FF D9; P = the current marker position):

```
 while(P+4<=N){
  if(In[P]!=0xFF)return false;const uint8 Marker=In[P+1];
  const int64 Length=(int64(In[P+2])<<8)|int64(In[P+3]);if(Length<2||P+2+Length>N)return false;
  if(Marker==0xDA){ // the SOS header must be whole and consistent (Ls = 6 + 2 Ns) with scan data and the EOI after it
   const int64 Components=P+4<N?int64(In[P+4]):0;if(Components<1||Components>4||Length!=6+2*Components||P+2+Length>N-2)return false;Sos=P;break;}
```
and in Checksum:
```
 uint64 Hash=14695981039346656037ull;MaxChannel=0;
 ... Hash=(Hash^uint64(Q[C]))*1099511628211ull;
```
1. Is (a) fixed: the SOS header's length is bounds-checked before use, Ns is 1..4, Ls == 6 + 2*Ns, and the header ends before the final EOI; can any of these lines read out of bounds?
2. Is (b) fixed: the FNV-1a 64-bit offset basis and prime?

Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

APPROVE

`[kimi-k3.1-pro · 641+2656 tokens · 48.5 s]`

## Native follow-up N2a: the installer's anchors, EDITS and plan()

Question (verbatim); attached: install_v24.py lines 566-623.

```text
Context: install_v24.py, a Python installer that patches two UE C++ files (Sub01HomeLab.h/.cpp, LF-normalized text) on top of earlier layers (v23, v22, v21, cam2 markers required). Attached: the cam2 evidence anchors (each replacement keeps its anchor line's content), the EDITS list (applied in order; each anchor must occur exactly once in the text as modified by the edits before it), REQUIRES, and plan(): refuse when already installed or a required layer is missing, all-or-nothing, bracket balance unchanged, the marker present after. The replacement texts were reviewed in earlier pieces. Review ONLY the attached lines for bugs (an edit that can apply twice or in the wrong place, a partial result, a wrong refusal).
Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

APPROVE

`[kimi-k3.1-pro · 1533+11741 tokens · 245.6 s]`

## Native follow-up N2b: the installer's run() and main()

Question (verbatim); attached: install_v24.py lines 626-676.

```text
Context: install_v24.py, a Python installer that patches two UE C++ files in place on the pod (run as the game user by a build wrapper that compares the dry-run JSON with a frozen copy, then applies and checks the after-hashes). Attached: run() and main(): read raw bytes, keep each file's line ending (CRLF or LF), plan on LF text, write both files atomically (v2.write_atomically, the house helper), verify the written bytes against the plan, report JSON (status planned / applied / refused with exit 2). Review ONLY the attached lines for bugs (a partial write, a wrong hash or line ending, a report that differs between dry run and apply in the files part).
Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

APPROVE

`[kimi-k3.1-pro · 1400+4357 tokens · 83.1 s]`

## Piece 7c-a: save_frame and the opening checks (33 lines)

Question (verbatim); attached: save_frame, the start of probe().

```text
Context: main_fifo_probe.py, a stdlib Python reader for a go/no-go of the FIFO main.mjpeg while nobody else reads it (run as root on a shared pod). The writer (a game) writes whole baseline JPEGs (SOI ... EOI, a COM "seq=<n>" each) back to back and may cut a frame mid-way, close, and later start again with a fresh SOI. Attached: save_frame (no replace, no link) and the start of probe(): the FIFO opened first with O_NOFOLLOW and checked with fstat (before: lstat then open, a TOCTOU you found in piece 7c), the other-readers scan by the opened FIFO's (st_dev, st_ino), refusals raise SystemExit. Check: no fd leak on any refusal, no race left.
Review ONLY the attached lines for bugs. Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

1. **blocking** — `readers, unchecked = other_readers(...)`: the scan remains TOCTOU; another reader can open the FIFO immediately afterward and split frames during the probe. The shown refusal paths do close `fd`, and open/`fstat` removes the path-check race.
   **Fix:** hold an exclusive single-reader lock/protocol honoured by every reader for the entire probe, or designate one permanent FIFO owner. Otherwise document the scan as advisory—rescanning `/proc` cannot make exclusivity race-free.

`[kimi-k3.1-pro · 855+12949 tokens · 250.2 s]`

## Piece 7c-b: the read loop (42 lines)

Question (verbatim); attached: probe(): the read loop.

```text
Context: main_fifo_probe.py, a stdlib Python reader for a go/no-go of the FIFO main.mjpeg while nobody else reads it (run as root on a shared pod). The writer (a game) writes whole baseline JPEGs (SOI ... EOI, a COM "seq=<n>" each) back to back and may cut a frame mid-way, close, and later start again with a fresh SOI. Attached: probe()'s read loop (poll 100 ms, non-blocking reads, EOF = no writer, sleep 50 ms; frames counted, contract-checked, saved). Check: no hang or spin, correct counting, frames completed by one read share its time (max_frames_per_read is reported for that).
Review ONLY the attached lines for bugs. Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

1. **blocking — `if not data:` branch:** EOF leaves any partial JPEG buffered in `walker`. After a mid-frame close, the next writer’s fresh SOI can be parsed as its continuation, yielding a bogus frame/seq and invalid go/no-go results. Reset the parser before `continue`—`walker = Walker()` or `walker.reset()`—discarding the incomplete frame.

`[kimi-k3.1-pro · 818+10020 tokens · 192.9 s]`

## Piece 7c-c: the summary (24 lines)

Question (verbatim); attached: probe(): the summary.

```text
Context: main_fifo_probe.py, a stdlib Python reader for a go/no-go of the FIFO main.mjpeg while nobody else reads it (run as root on a shared pod). The writer (a game) writes whole baseline JPEGs (SOI ... EOI, a COM "seq=<n>" each) back to back and may cut a frame mid-way, close, and later start again with a fresh SOI. Attached: probe()'s summary. In piece 7c you found the rates ignored the idle time after the last frame; now fps_window and seq.unique_fps_window run from the first frame to the END of the run, trailing_idle_ms is reported and longest_read_stall_ms includes the trailing silence. Check the arithmetic and the edge cases (no frame, one frame).
Review ONLY the attached lines for bugs. Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

APPROVE

`[kimi-k3.1-pro · 1055+10322 tokens · 201.3 s]`

## Piece 7c-d: main() (29 lines)

Question (verbatim); attached: main().

```text
Context: main_fifo_probe.py, a stdlib Python reader for a go/no-go of the FIFO main.mjpeg while nobody else reads it (run as root on a shared pod). The writer (a game) writes whole baseline JPEGs (SOI ... EOI, a COM "seq=<n>" each) back to back and may cut a frame mid-way, close, and later start again with a fresh SOI. Attached: main(): arguments, the --save directory (created 0700, refused when it is a link), the JSON output, exit codes (0 ok, 2 refused). Check for bugs.
Review ONLY the attached lines for bugs. Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

1. **minor — L11 (`args.save.mkdir`)**: an existing regular file or dangling/non-directory symlink raises `FileExistsError` before L12, producing a traceback/exit 1 instead of JSON refusal/exit 2. Catch `FileExistsError`, then perform the plain-directory check; route other expected setup `OSError`s through the refusal path too.
2. **blocking — L11–12 and L16**: pathname validation is TOCTOU; with an attacker-writable parent, the directory can be replaced after `is_symlink()`—even between the two checks—so this is not a safe root symlink defense. Open using `O_DIRECTORY|O_NOFOLLOW`, verify with `fstat`, and have `probe` save through that held dirfd rather than reopening the path.

`[kimi-k3.1-pro · 772+12774 tokens · 258.8 s]`

## Follow-up F1: the probe after 7c-a and 7c-b

Question (verbatim); attached: drop_partial, the rescans, the EOF branch, the report fields.

```text
Context: main_fifo_probe.py, a stdlib Python go/no-go reader of the FIFO main.mjpeg (run as root on a shared pod; the writer, a game, writes whole JPEGs and on a cut closes the FIFO, never resuming a frame's tail; it reopens with a fresh SOI). Follow-up on your findings: piece 7c-a (blocking: the other-readers scan is TOCTOU) -> the scan is now documented as advisory, repeated every RESCAN_S = 5 s and once more before the probe closes its descriptor, and any reader seen makes the run "exclusive": false (its numbers then do not count); piece 7c-b (blocking: a partial frame left in the cutter at EOF could be glued to the next writer's frame) -> at EOF the cutter drops its partial frame and counts it as a cut. Attached: those lines.
Review ONLY the attached lines. Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

1. **blocking — `'exclusive': None if force else not intruders`:** empty `intruders` means only “not observed”; 5-second/final scans can miss an open-read-close reader, so they cannot certify numbers that count. Fix: report `False` when readers are seen, otherwise `None`/unknown, and count runs only under externally enforced exclusivity (private FIFO/namespace or cooperating lock).
2. **blocking — `walker.drop_partial()` under `if not data`:** close/reopen between reads can produce no EOF, leaving the old partial to be glued to the next writer. Fix: when a fresh SOI arrives with an unfinished frame buffered, also increment `cuts`, clear/resync, and start from that SOI; retain the EOF cleanup.

`[kimi-k3.1-pro · 856+15025 tokens · 264.7 s]`

## Follow-up F2: the probe after 7c-d

Question (verbatim); attached: open_save_dir, save_frame, main()'s --save part.

```text
Context: main_fifo_probe.py, a stdlib Python go/no-go reader of the FIFO main.mjpeg (run as root on a shared pod; the writer, a game, writes whole JPEGs and on a cut closes the FIFO, never resuming a frame's tail; it reopens with a fresh SOI). Follow-up on your findings in piece 7c-d: an existing file at --save raised a traceback (minor), and the save directory's path checks were TOCTOU (blocking) -> the directory is now opened once with O_DIRECTORY|O_NOFOLLOW (created 0700 when absent), every frame is written through that held descriptor with dir_fd and O_CREAT|O_EXCL|O_NOFOLLOW, and any failure is a JSON refusal with exit 2. Attached: open_save_dir, save_frame and main()'s --save part.
Review ONLY the attached lines. Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

APPROVE

`[kimi-k3.1-pro · 923+15574 tokens · 331.6 s]`

## Follow-up F3: the probe after F1

Question (verbatim); attached: none (the changed lines are quoted).

```text
Context: main_fifo_probe.py, a stdlib Python go/no-go reader of the FIFO main.mjpeg (the writer, a game, writes whole TurboJPEG baseline frames; on a cut it closes the FIFO and later reopens with a fresh SOI; FF D8 FF never occurs inside one of its frames: entropy data is stuffed, header bodies (JFIF APP0, COM "seq=<n>", DQT at quality >= 40, SOF0, DHT, SOS) hold no FF D8 FF). In follow-up F1 you found: (1) `exclusive` true only meant "no other reader observed"; (2) a close/reopen with no EOF seen in between could glue an old partial frame to the next writer's frame. The changes, verbatim:

(1) the report field (the scans every 5 s and at the end are unchanged):
```
            # the scans can show another reader, never prove there was none (one could open and close between two scans)
            'other_reader_seen': None if force else bool(intruders), 'other_readers_during_run': sorted(intruders)}
```
(the README's go/no-go now asks for `other_reader_seen false` AND states that exclusivity comes from the procedure: the director stopped or in x11 mode, its tap not draining the FIFO)

(2) in Walker.feed, right after `end, complete = self._walk()` (end None = more bytes needed; complete False = a cut detected at `end`):
```
            fresh = self._soi(2)   # a NEW frame's SOI after this one's start (FF D8 FF never occurs inside an encoder's frame)
            if fresh > 0 and (end is None or end > fresh):
                # the writer restarted (it closed on a cut and reopened with no EOF seen in between): this frame can never complete,
                # and a walk that ran past the new SOI would glue two frames together
                self.cuts += 1
                del self.buffer[:fresh]
                continue
```
(`_soi(start)` = `self.buffer.find(b'\xff\xd8\xff', start)`; the loop then restarts on the new SOI; a test glues an old frame cut inside its DQT so that the segment's length swallows exactly the new frame's SOI+APP0+COM: without the guard a bogus frame with the OLD seq passed the contract; with it the new frame comes out whole and one cut is counted)

1. Are (1) and (2) fixed? 2. Can (2) drop a good frame or loop without progress?

Answer in at most 12 lines: APPROVE, or numbered findings with severity (blocking/minor), each with the line and the fix.
```

Answer (verbatim):

APPROVE

`[kimi-k3.1-pro · 770+8435 tokens · 156.8 s]`

## Follow-up: the fixes after pieces 3a and 3bc

Question (verbatim); attached: Collect, EncodeLoop, the main_tap 0 branch, WriteWhole, the destructor (after the fixes).

```text
Context: UE 5.8.3 game-module C++ on Linux (pre-commit review of install_v24.py, follow-up). In earlier pieces you found: (a) the encoder released a sequence's EncodeInFlight place when its ENCODE ended, so an early finisher let more work in while an older encode stalled, and the Done trim could drop an unreleased frame and stop ordered release for good; (b) WriteWhole checked its 0.5 s deadline only on EAGAIN. Attached: the code after the fixes: (1) Collect reads Reader once per slot and admits a non-probe job only while EncodeInFlight < 2; the encoder decrements EncodeInFlight only when the sequence is RELEASED (after Outstanding.pop_front()), the Done trim is removed; (2) main_tap 0 also resets the lock/probe retry timers so a switch-on tries both at once; (3) the deadline is checked before every write; (4) a comment on teardown (you raised a teardown race in an earlier piece; in 5.8.3 TBaseSPMethodDelegateInstance::ExecuteIfSafe pins the object for each call, and TSharedPtr defaults to ESPMode::ThreadSafe; FSlateApplicationBase::GetRenderer() returns FSlateRenderer*, not a TSharedRef). A runtime test now stalls one encode for 0.4 s: the old code stops the stream for good, the new code resumes in order and gap-free. Answer ONLY, each in at most 3 lines, yes/no first: 1. Are (a) and (b) fixed, and is Done now bounded without any drop (at most Encoders-1 frames)? 2. Any new deadlock or leak of EncodeInFlight (e.g. Stop clearing the queues, a failed encode, a probe job)? 3. Is (2) safe? 4. Given the pinning, is the teardown acceptable? End with "no blocking issue" or "blocking: ...".
```

Answer (verbatim):

1. Yes. Release—not encode completion—frees capacity, and the deadline now bounds partial-write trickles too. A stalled head leaves at most `Encoders-1` retained `Done` frames; nothing unreleased is trimmed.
2. No. Failed encodes release via an empty frame; probes touch neither `Outstanding` nor the counter. `Stop` may abandon queued work only during terminal, one-shot teardown, so it cannot poison a restart.
3. Yes. Zeroing writer-local retry timestamps while disabled merely makes both existing, gated attempts immediately due after re-enable; cleanup and `WaitIdle()` ordering remain intact.
4. Yes. Pinning prevents callback/destruction overlap, an abandoned binding can only observe an expired weak pointer, and game-thread removal checks the raw renderer pointer before use.

no blocking issue

`[kimi-k3.1-pro · 2823+10110 tokens · 222.7 s]`

## Follow-up: the m5 launcher after piece 7a

Question (verbatim); attached: the new m5 diff against m3o.

```text
Context: the game launcher launch-streamer-game-20261024m5.py (derived from m3o, which is never edited; runs as root, the game as uid 1001). You reviewed it in piece 7a and noted: the whole suffix of game.log was rescanned every 2 s; a partial last line holding the marker could be saved truncated; wall-clock time.time() for the deadline; the child's exit could skip a final scan; os.chown(OUT) could follow a symlink planted in unreal's directory. Attached: the new unified diff against m3o. Changes: log_after reads incrementally (the caller passes back the offset after the complete lines read) and stops at a line without its newline; time.monotonic() deadlines; one last read when the game has ended; OUT must be a plain directory (not a symlink) and is chowned with follow_symlinks=False. Answer ONLY, each in at most 3 lines, yes/no first: 1. Are those points fixed? 2. Can the new loop hang or miss the marker (each marker search starts at the launch offset)? 3. Anything else new that breaks the launcher? End with "no blocking issue" or "blocking: ...".
```

Answer (verbatim):

1. Yes — scans are incremental and complete-line-only, deadlines are monotonic, child exit gets a final read, and the OUT chown no longer follows a symlink.
2. No—for newline-terminated markers: each wait terminates on marker/deadline/exit, unfinished lines are retried, and restarting at `log_offset` prevents either search skipping earlier output.
3. No — no new launcher-breaking regression is evident in the supplied diff; a permanently unterminated final marker line remains intentionally ignored.
no blocking issue

`[kimi-k3.1-pro · 1892+11254 tokens · 235.3 s]`
