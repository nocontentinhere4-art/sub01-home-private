# Kimi consultation (2026-10-23): director v2 (60 fps, NVENC, cam2 layouts, live switching, HLS)

Model kimi-k3.1-pro through tools/ask_kimi.py on the pod. Design brief: `q-director-v2.txt` (a first attempt ran out of
tokens while reasoning and gave no answer); code review brief: `q-director-v2-review.txt`. The answers are advice to
weigh, not project policy; what was adopted is listed after each.

## Design answer

1. **(a)** The graph is structurally correct; nothing silently selects 30 fps. `-r 60` is redundant with the three `fps=60` filters in steady state, but can still duplicate/drop after a timestamp discontinuity. Sixty CFR output frames does **not** mean sixty new captures: `fps` duplicates/drops, overlays can repeat a PiP, and `tpad` clones frames.

2. **(a/e)** The open-but-idle cam2 FIFO remains a hard stall: neither `fps` nor `tpad` runs while the demuxer is blocked; `tpad` helps only after EOF. Your 5-second staleness test polled every 3 seconds can take roughly **5–8 seconds** to detect failure. A separate cam2 reader/pacer emitting the last frame or black at 60 is the robust nonblocking design.

3. **(b)** Sixteen vCPUs are plausibly sufficient, but CPU model, overcommit and X-server behaviour are unknown, so actual headroom cannot be inferred. The budget is **16.67 ms/frame**; two 4-byte-per-pixel 1080p60 grabs alone represent about **0.995 GB/s** of raw capture traffic. NVENC removes encoding cost, not grab, MJPEG-decode or filter cost.

4. **(b)** Your sharing of full-size frames and PiP scales is already reasonable. Easy savings are `scale=960:540:flags=area` for the split halves and bilinear rather than default bicubic upscaling for cam2. A single `streamselect` map command cannot also rebuild/gate the upstream scenes; if those must not be rendered, `--layout-switch restart` is the substantial saving.

5. **(b)** Do not add `hwupload_cuda` merely before NVENC: `h264_nvenc` already uploads software frames. `scale_cuda`/`overlay_cuda` require a deliberately CUDA-frame-based pipeline, and standard CUDA equivalents for your complete `hstack`/`pad` split path are not available; partial conversion is unlikely to be a drop-in win.

6. **(c)** Xvfb at 1080p60 with working SHM is realistic; GPU-X-server readback on `:99` is the uncertain capture. `-use_shm 1` is already the default but can be stated explicitly; `-show_region 0` is also default and provides no additional saving. `-framerate 60` requests pacing—it does not prove delivery.

7. **(c)** `thread_queue_size` counts packets, not milliseconds. At 60 fps, 512 video packets are **8.53 seconds**; if each is 1920×1080×4 bytes, their maximum queued payload is about **3.96 GiB per grab**. Start around **32–64** instead: approximately 253–506 MiB maximum payload per grab, when actually queued.

8. **(d)** `-stdin` is correct and explicit, though interaction is already enabled here because stdin is not an input. `-progress pipe:1` does **not** disable it. Drain stdout and stderr continuously, serialize commands, and accept both `stream 0` and `graph 0` replies. `ret:0` acknowledges the filter command, not presentation of the first switched frame.

9. **(e)** Raw MJPEG over a FIFO with `-use_wallclock_as_timestamps 1` is reasonable; `-framerate 60` cannot pace the writer. `fps=60:round=near` uses the existing default rounding. `setpts=PTS-STARTPTS` only shifts the origin; `setpts=N/(60*TB)` forces one frame per index but discards wallclock timing and can drift against audio.

10. **(e)** MJPEG decode is **55.3 Mpixel/s** at 720p60; its exact vCPU cost is unknown but is usually secondary to the 1080p upscaling/filtering. `yuvj422p` is full-range 4:2:2, not a frame-rate problem. Make conversion explicit, for example `scale=1920:1080:flags=bilinear:in_range=full:out_range=limited,format=yuv420p`.

11. **(f)** `dup_frames`/`drop_frames` primarily describe final output frame-sync behaviour. They do **not** count duplicates created inside `fps`, clones from `tpad`, repeated overlay inputs, or identical x11grab images. With CFR filters feeding `-r 60`, they can remain zero during substantial source duplication.

12. **(f)** Your proposed logging proves output count and pace, not unique source frames. A complete continuous 600-second segment should contain **36,000 video frames**, have 60-fps presentation timestamps, and approximately 600 seconds duration; verify this with `ffprobe`. Keep `frame/wall` and `speed` as stall/throughput indicators. Proving source delivery requires timestamps/counts **before** each `fps` filter.

13. **(g)** `onfail=ignore` on HLS is correct if MP4 must survive HLS failure. It handles errors, not an indefinitely blocked local write. `use_fifo=1` is valid per branch but optional; do not add `drop_pkts_on_overflow=1` to MP4/HLS unless gaps are acceptable. Your bounded, recovering FIFO policy is appropriate for the disposable RTMP branch.

14. **(g)** The listed HLS flags are compatible; six nominal 4-second entries give about a **24-second** live window. Add `+program_date_time` if absolute-time mapping is wanted. `independent_segments` is only a declaration: verify actual IDR-aligned segments. With `-g 120`, GOPs are 2 seconds and 4-second HLS cuts are normally available. These flags do not make reuse of `live.m3u8` across process restarts seamless.

15. **(h)** On a normal 6.1 build, the H.264 option names are valid; `-g 120` is correct. Most names are shared with `hevc_nvenc`, but B-frame support and actual configuration remain codec/GPU/driver dependent, and HEVC CQ 23 is not visually equivalent to H.264 CQ 23. Successful option parsing alone does not prove `-bf 2` was honoured.

16. **(h)** `-tune ll` has little value for local MP4 plus 4-second HLS, and LL/ULL/zerolatency settings interact with B-frame/lookahead choices. Do not blindly add `-zerolatency 1` or `-rc-lookahead`; `-spatial-aq 1` is an optional quality trade-off, not a 60-fps requirement.

17. **(h)** A 640×360 one-second probe is only an option/driver smoke test—not a throughput or GOP/HLS test. It never reaches the normal 2-second GOP boundary or a 4-second HLS segment. Probe at **1920×1080, 60 fps**, with the exact options, for at least 10 seconds and preferably 60 seconds under concurrent Unreal load.

18. **(i)** Starting every stream’s PTS near zero does not establish a common acquisition epoch. Expect a constant startup offset and possible long-term drift between wallclock video and sample-count audio. `apad` handles EOF, not an open FIFO that stops supplying samples; `aresample=async=1` cannot discipline audio against the video clock.

19. **(i)** The cheap mitigation is to have the voice writer continuously emit real-time PCM, including silence: every 20 ms, write **960 sample frames = 3,840 bytes** of stereo s16le at 48 kHz. Calibrate any residual fixed offset with input `-itsoffset`; optionally use `aresample=async=1:first_pts=0,apad` for timestamp-gap/EOF sanitation. Drift-proof synchronisation requires audio timestamps derived from the same clock domain as video.

### Adopted / rejected

| Point | Decision |
|---|---|
| 1, 11, 12 output CFR is not proof of distinct source frames | adopted as documentation: `fps_measured` and `segment_fps` prove the output pace; RUNBOOK "Proving 60" gives the ffprobe packet count (36000 per 600 s) and an mpdecimate distinct-frame check (verified locally: 30 fps upsampled to 60 gives 301 of 600 distinct, true 60 gives 600) |
| 2 an open but idle cam2 FIFO stalls everything | partly: cam2.json freshness every 1 s while ffmpeg reads cam2, stale limit 3 s, /proc writer scan only every 5th tick (detection about 4-6 s). The separate pacer process is rejected for now (new Python frame path at 60 fps and JPEG splitting of the game's stream); documented as a limit |
| 4 `flags=area` on split halves, bilinear for the cam2 upscale | adopted |
| 5 no hwupload/scale_cuda | agreed, nothing added |
| 7 thread_queue_size 512 = up to ~4 GiB of raw 1080p frames per grab | adopted: 128 (~2 s at 60 fps, ~1 GiB worst case) |
| 8 `-stdin` + `-progress pipe:1`, drain both pipes, serialise commands, accept both reply wordings | already so (lock around switches, stdout and stderr always read, regex for `stream 0` and `graph <0>`) |
| 10 explicit JPEG range conversion | adopted: `in_range=full:out_range=limited` on cam2 (not on lavfi test frames) |
| 14 `program_date_time` | adopted |
| 16 `-tune ll` of little value | kept: it is the owner's spec; harmless for MP4 + HLS |
| 17 probe 1080p60 for 10-60 s under load | partly: the probe now runs at the real size and rate; it stays 1 s (owner's spec, startup delay), throughput is watched live by the meter |
| 18-19 A/V clock domains | no code change: the voice server already writes continuous real-time PCM; `-itsoffset` calibration noted for the pod rehearsal |

## Code review answer (diff of streamer_director.py, the monitor feed, the HLS server, RUNBOOK)

1. **high — `output_args` / `build_ffmpeg_argv`:** `--rtmp-url-file` still puts the URL in ffmpeg’s tee argument, exposing it through `/proc/<ffmpeg>/cmdline` and `ps`; `--rtmp-url` additionally exposes the director’s argv. **Fix:** document this residual exposure, or use a publisher that receives the secret through protected IPC without placing it in argv.

2. **high — `cam2_status` / `cam2_tick`:** If the game replaces `cam2.mjpeg`, the tap follows the new inode but ffmpeg remains on the old FIFO. Fresh JSON/writer checks can then stay green while `room` repeats an old frame indefinitely—or the old open FIFO stalls the graph. **Fix:** store the FIFO `(st_dev, st_ino)` at launch and force a relaunch when it changes.

3. **medium — `apply_layout` / `_run_once`:** A watchdog/cam2 restart can replace run A while its `send_command()` is still waiting; A’s later timeout can then restart run B, and a late reply can overwrite B’s `live_layout`. **Fix:** associate commands/replies with the process/run generation, cancel or await switches before relaunching, and ignore stale completions.

4. **medium — `_run_once` / `build_ffmpeg_argv`:** In restart mode, non-`room` layouts still add cam2 whenever available although their graph never consumes `[3:v]`; the director also stops draining it. A stalled cam2 can consequently obstruct startup or fill its FIFO and disrupt a recording that does not use it. **Fix:** attach cam2 only when `live` or `target == "room"`.

5. **medium — `MonitorFeed.run` / `FifoSink.try_open`:** After spawn failure there are no writes to reveal reader disconnect via `EPIPE`; `fd` can remain non-`None` forever, giving stale `reader: true` and endless capture attempts without a reader. A blocking game read also receives neither frames nor EOF. **Fix:** close/reopen the sink on such failures and require game-side read timeouts/nonblocking reads.

6. **medium — `FifoSink.offer` / `_write_pending`:** A frame prefix can be in the FIFO with its tail in `pending`; overlapping reader handoff can give the new reader only that tail, and stop/crash can leave a truncated JPEG. **Fix:** withdraw the RUNBOOK’s whole-JPEG guarantee and require SOI/EOI resynchronization or length framing; a FIFO cannot provide reconnect/crash atomicity.

7. **medium — `OutputMeter.feed`:** `floor(out_time / segment_seconds)` does not represent actual keyframe-driven cuts. For example, with an 11 s segment time and 2 s GOP, the cut is around 12 s, but the meter may close at the 15 s progress block and mix frames from both files. **Fix:** use actual segment-cut information, or label these as approximate progress windows and correct the RUNBOOK’s per-file claim.

8. **low — `OutputMeter.feed` / `finish`:** `_seg is None` is handled before `progress=end`; a run ending before its first periodic block can therefore produce a zero-frame/zero-wall record. An end block crossing a segment boundary can also merge the full and final partial segments. **Fix:** handle end/boundary transitions explicitly and initialize a run-start baseline.

9. **low — `_run_once` / `prune_hls`:** After downtime exceeding 60 s, startup deletes previous segments before the new ffmpeg replaces `live.m3u8`; clients can receive the old playlist and then 404s for its segments. **Fix:** retain the previous prefix until the new playlist is visible.

10. **low — `send_command`:** A nonzero reply such as `ret:-22` does not fail immediately; the loop waits for a nonexistent later `ret:0` until timeout. **Fix:** return failure on the first nonzero reply, using one absolute deadline.

11. **low — module docstring / `parse_args`:** The documentation names `--layout-interval` and `--cam2-interval`, but neither argument exists, so either produces an argparse error. **Fix:** wire them to `DirectorConfig` or document the fixed one-second intervals.

### Applied / rejected

| Finding | Decision |
|---|---|
| 1 RTMP URL in ffmpeg's argv | documented (RUNBOOK flag table): ffmpeg takes an output URL only on its command line, so `ps` shows it while it runs; the director never logs, prints or stores it and redacts ffmpeg's messages |
| 2 replaced cam2 FIFO | fixed: the run remembers the FIFO's (dev, inode); a different one reported by the tap means a relaunch (test) |
| 3 switch racing a relaunch | fixed: a switch is tied to the process it was sent to; if the run changed meanwhile it returns `stale` and touches nothing; the reply queue is cleared at each launch (test) |
| 4 restart mode attaching an unused cam2 | fixed: restart mode attaches cam2 only to `room` runs; live mode attaches it whenever usable (test) |
| 5 monitor feed: stale `reader: true` | fixed: poll() POLLERR on the write end notices a vanished reader without writing; used by health and before relaunching ffmpeg (test). The game-side non-blocking read is documented |
| 6 whole-JPEG guarantee across reconnect/crash | accepted: claim narrowed to a connected reader; the game must resync on SOI (RUNBOOK, docstring) |
| 7 per-segment fps is approximate | accepted: rows are documented as windows numbered like the segment files, not exact files |
| 8 meter edge cases | fixed: the first block is the baseline, an end block past a boundary closes the full window, no zero-frame records (tests) |
| 9 HLS pruning at launch | fixed: pruning only runs from the watchdog (every 30 s, segments older than 60 s), after the new playlist exists |
| 10 non-zero reply waits for the full timeout | partly: one absolute deadline and only 0.5 s more after a non-zero reply. Not an immediate failure, because ffmpeg answers once per filtergraph and a run without voice has an audio graph that answers ENOSYS |
| 11 `--layout-interval` / `--cam2-interval` missing | fixed: both flags exist (test) |
