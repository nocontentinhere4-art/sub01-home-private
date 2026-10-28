# Kimi pre-commit reviews (2026-10-24 18:20-19:16 UTC): refresh script, sawtooth doc, structural design

Kimi via `tools/ask_kimi.py` (default model), 32000-token budget, 516 s. Attached: `docs/streamer/SAWTOOTH-20261024.md`,
`scripts/streamer_swapchain_refresh.py`, `tests/test_streamer_swapchain_refresh.py` (the versions before this review).

## Question (verbatim)

```text
Pre-commit review for SUB-01 (sawtooth work). Please review the attached files and answer, max ~450 words, numbered:
(1) blocking defects in scripts/streamer_swapchain_refresh.py or its test (correctness, safety: it writes the game's
private live-console file as uid 1001, must always leave r.VSync 0, must not burst after a suspend, kill switch);
(2) whether docs/streamer/SAWTOOTH-20261024.md states the evidence and limits honestly (anything over-claimed, e.g. the
X11 16-bit sequence inference, the ABBA verdict under the two gates, the ablation numbers);
(3) the structural-fix design for the coordinator in that doc (offscreen + main-view FIFO to the director): what is
missing or risky (OnBackBufferReadyToPresent under -RenderOffScreen, readback/encode budget on 6 cores, the director
fallback, operator view), and what the acceptance test should be.

Context since your last answer: the ABBA recr60 finished: A legs 20.45 / 20.09 ms, B legs 18.47 / 18.49 ms (B-A -1.79 ms,
+4.3 fps), p95 22.24/22.18 vs 20.45/18.80, worst 10 s window 45.0/45.1 vs 48.9/53.2 fps; flip frames 74-86 ms, every
>120 ms frame (A: 189, 663, 818, 179; B: 168, 176) is not aligned with a flip; in-ramp slope unchanged (0.52-0.60
ms/min), amplitude 0.11-0.15 ms in B vs 1.6-3.4 ms in A. Offscreen ablation (same v21 binaries, -RenderOffScreen,
cam2_fps 60): capped 59.8-59.9 fps for 15 min with no sawtooth, render 13.5 ms, cam2 capture 59.8 / written 52-53 fps;
uncapped 77.2-77.9 fps (12.9 ms frames), GPU 9.75 ms. The game is back on plain m3 (windowed); a 10-min baseline check
is running. The toggler is not left running. HANDOFF.md gets a 5-line bullet pointing to the doc. Also committed:
tools/sawtooth/*.py (pod analysis helpers: Insights event exports per thread, samplers, the ABBA harness), not attached.
```

## Answer (verbatim)

1. **Block unattended use.** Normal alternation, stop handling and the post-jump `due` reset look correct, but safety is incomplete. `--period nan` bypasses the minimum and causes a no-sleep flip storm; require finite period/duration. `Console.send` must handle short writes; replace shared `.tmp` with a unique, same-directory private temporary. Enforce uid 1001 and one writer/instance: process-local sequence/state races with other writers, while restart or wall-clock regression can make requests—including final `r.VSync 0`—ignored. `finally` is best-effort, not “always” (write failure/SIGKILL); alert and provide external recovery if that requirement is literal. Add short-write/writer-failure tests and a multi-hour fake-clock jump proving exactly one flip, then a full-period gap, including stop-file exit.

2. **Mostly honest, but qualify conclusions.** The 16-bit X11/three-request explanation is labelled inference; keep it and “presents, not time” as hypotheses, not proven driver root cause. Under the stated interpretation of Kimi’s hitch gate, recr60 passes descriptively; both paired median gains are ≤2 ms, so the older gate says inconclusive. Two legs per arm and non-overlap do not override that. Section 6 must remain experimental pending soak. Offscreen strongly supports the diagnosis but changes the whole platform/presentation path; 15-minute capped and four-minute uncapped runs do not isolate a 5.5–9 ms present cost. “30% headroom” is pre-tap throughput. Neither main-view delivery at 60 nor 60/60 margin is demonstrated. Capture 59.8/write 52–53 locates loss downstream of capture, not specifically JPEG versus FIFO/writer/backpressure.

3. **Design and acceptance.** Treat `OnBackBufferReadyToPresent` as go/no-go: verify it fires offscreen with non-black 1080p content, valid texture lifetime/format and safe threading; define another tap otherwise. Budget 8.29 MB/frame (0.498 GB/s at 60), conversion, p99 encode and director 1080p MJPEG decode under full pod load. The estimate is 7.2 ms/encode, or 0.43 core at 60; that alone does not justify “one encode caps below 60.” FIFO JPEG writes can be partial and lack message atomicity: specify buffering/drop/reconnect/SIGPIPE behaviour or another transport. Select x11grab by explicit windowed mode, never missing `main.json` offscreen; otherwise failure becomes black video. A second operator FIFO reader would steal bytes—use preview/tee.

   Run four-leg tap-off/on ABBA against m3o with the real director, then an ≥8-hour soak. Suggested gates: ≥59.5 unique main fps at ffmpeg, ≤0.5% drops, p95 frame-time regression ≤0.5 ms, no tap-aligned >50 ms hitches or sawtooth, and stable/in-budget CPU/RSS/FD/GPU; fix or explicitly waive cam2’s 52–53. Kill/restart each side and suspend/resume; require intact ordered frames, bounded placeholder/recovery, working windowed fallback and no black output.

## Applied

1. Script: finite period (>= 30 s) and duration checked in `run()` and `main()` (NaN/inf refused); `Console.send`
   writes through a loop that completes short writes, into a unique private temporary in the same directory
   (`mkstemp`, 0600, fsync, then rename; removed on failure); `main()` refuses any uid but 1001 and takes an exclusive
   lock file (one instance); the final `r.VSync 0` is retried 3 times and a persistent failure is raised; the docstring
   says it is experimental, best-effort on exit (not after SIGKILL) and must be the only console writer while it runs.
   Tests added: short writes, a failing writer leaving the previous request intact and no temporary behind, a
   five-hour clock jump giving exactly one flip and then a full period, restore retries and failure, NaN/inf/negative
   periods and durations (11 tests pass).
2. Doc: the X11 sequence explanation and the frame clock are stated as hypotheses; the ABBA verdict says "passes
   Kimi's gate descriptively, inconclusive under the project's 2 ms rule, non-overlap does not override it"; the
   refresh is marked experimental pending the soak; the offscreen section says what the ablation does not isolate,
   that 77.5 fps is before any tap, that 60/60 with the tap is not shown, and that cam2's loss is downstream of the
   capture without locating it.
3. Design: `OnBackBufferReadyToPresent` is a go/no-go check with the criteria above; the transport section names the
   PIPE_BUF/atomicity problem and the required behaviours (or a shared-memory ring); the director selects its source
   explicitly (`--game-source fifo|x11`), shows a placeholder instead of a black grab, and the FIFO has one reader;
   the "one encode caps below 60" claim is replaced by "measure p99 encode under load and keep enough in flight";
   acceptance = Kimi's four-leg tap-off/on ABBA against m3o with the real director, an >= 8 h soak and the gates above.

## Second review (2026-10-24 19:11-19:16 UTC): the native hand-off write-up, new numbers, v22 paragraph

Kimi via `tools/ask_kimi.py` (default model), 32000-token budget, 300 s; the updated doc attached.

### Question (verbatim)

```text
Second pre-commit review for SUB-01 (sawtooth doc, attached in full). Since your last review I applied your findings
and added: (a) offscreen per-thread numbers (RHI thread 4.1-4.3 ms user + 0.4 ms sys per frame offscreen vs 8.6 -> 11.5
user + 2.6 sys windowed; Xvfb 210 -> 65 ms/s; GPU busier offscreen), (b) the v22 baseline leg (20.29 ms p50, same
sawtooth as v21), (c) the final runtime state, and (d) a rewritten structural-fix section that is the input for the
next native worker. The coordinator requires that section to state: the native hand-off path with a go/no-go, the
FIFO format and its atomicity, the director's explicit windowed/offscreen mode, how the operator still gets a window,
and the acceptance gates. Please answer, max ~350 words, numbered: (1) anything wrong, unsafe or ambiguous in that
section that a native worker would trip on (especially the single blocking writer + bounded queue design, F_SETPIPE_SZ,
EPIPE/probe handling, the OnEndFrameRT fallback, the director's --game-source mode and placeholder); (2) anything in
the new numbers or the v22 paragraph that is over-claimed; (3) blocking issues before commit, if any.
```

### Answer (verbatim)

1. **Not implementation-safe yet.** One blocking writer provides ordering/non-interleaving, not frame atomicity: a stall can leave a prefix indefinitely, and crash/EPIPE/shutdown can truncate a frame. Remove “never cut” and “only possible partial frame”. On EPIPE or any write failure, close and **discard the whole current frame**; never resume its tail after reconnect. Specify partial-write/EINTR handling, `ENXIO` probing, clearing `O_NONBLOCK`, shutdown while blocked, and single-writer exclusion across process restarts. Bound encoder submission, in-flight/reordering and output queues too; queue=2 plus three readback slots does not alone prove back-pressure isolation. Treat `F_SETPIPE_SZ` as best-effort: check its return and `F_GETPIPE_SZ` (`EPERM`/user-page limits are possible); never assume 1 MiB or three frames. Verify Slate delegate signature and registration thread/lifetime against installed 5.8.3; retain texture references and handle actual format/row pitch. `OnEndFrameRT` is not a drop-in fallback: final/Slate-composited content and texture validity are not guaranteed, so it needs its own go/no-go. Define status cadence, stale `N`, placeholder/recovery/backoff; close a stalled ffmpeg reader to permit recovery. The explicit source modes and operator-window options are otherwise coherent.

2. **Over-claims:** 77.5 fps is an observed four-minute rate, not a ceiling. Subtracting 12.9 ms offscreen-uncapped from windowed ramp points does not isolate present cost; 5.5–9 ms is only a whole-configuration estimate. Higher GPU utilisation/power at higher fps is not independent proof. One v22 leg supports “no improvement detected; consistent with v21”, not that v22 “changes neither” frame time nor sawtooth, or establishes equivalence.

3. **Blocking as native-worker input:** fix the FIFO lifecycle rules, fallback validation, and two acceptance defects. JFIF-only JPEGs carry no sequence, so distinct sequences cannot be counted at ffmpeg without defined instrumentation. Also define the tap-off ABBA control: fifo-mode director then has no main input unless a placeholder/replay control is specified. After those edits and the wording corrections in (2), the investigation/runtime document can commit; 60/60 remains undemonstrated.

### Applied

1. FIFO lifecycle: "never cut" and "only possible partial frame" removed; one writer thread plus an `flock` across
   restarts; non-blocking fd written with `poll(POLLOUT)` loops that resume after partial writes and EINTR, a 500 ms
   per-frame deadline and a stop flag (no hang at shutdown); on EPIPE, any error or the deadline the fd is closed and
   the whole frame discarded and counted, never resumed; ENXIO probing every 1 s; `F_SETPIPE_SZ` best-effort with the
   return checked and `F_GETPIPE_SZ` logged; every stage bounded (readback 3, encodes 2, reorder 2, output 2).
   Hand-off: delegate signature, registration thread and lifetime verified first, texture reference held, actual
   format and row pitch handled; the `OnEndFrameRT` fallback gets its own go/no-go. Director: status every 1 s, stale
   after 2 s, kill the run (releasing a stalled reader), placeholder card, backoff 2-30 s, back after 3 s fresh.
2. Wording: 77.5 fps is "observed over 4 minutes, not a proven ceiling"; 5.5-9 ms is "a whole-configuration estimate
   only"; the GPU utilisation line says it follows from the higher frame rate; v22 is "no improvement detected,
   consistent with v21, not equivalence".
3. Acceptance: each JPEG carries a COM `seq=<n>` marker, counted at the director's input and cross-checked with
   `main.json` and ffmpeg's dup counts; the tap-off ABBA arm runs the director in fifo mode on its placeholder input.
