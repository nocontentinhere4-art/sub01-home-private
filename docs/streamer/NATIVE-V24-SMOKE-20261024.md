# Native v24 build and first live smoke

The reviewed native build passed on the private GPU pod at 2026-10-24 23:41:33 UTC. The offscreen m5 game passed its intrinsic go/no-go check at 23:47:23 UTC and the director received its real FIFO picture. This is an intermediate smoke result; the unique-frame acceptance gate has not passed.

## Build evidence

- Build-slice SHA256SUMS: `26cb79d95911bf56313f6e0d10da34b30575c7d1ee37d70b41f841d7f5ce296a`; all 17 entries verified.
- Installer SHA256: `ad0c3c25efdffbf8e3f24ab26727a39b1d1739b039930e2b9dd19da30b265f5a`.
- Actual source dry run exactly matched delivered JSON after normalizing only its source path. Frozen full source tree matched before application; applied full source tree matched planned hashes. Fresh verified source/binary backups retained.
- Guarded build wrapper exit 0, state complete, BUILD_EXIT=0. Final binary SHA256 `1c78b83cd2afd44436c281a40bb62d4f452077b2b6be7bf8ef5e1d0c7e769b0b`; changed from v23 `830da2d11dcbd671adf5b40cf5afea55d9ea812cc583bd0ca11c9bd6bcc4dfab`. ASCII marker `seq=%llu` absent before, present after.

## Runtime smoke

Followed the existing FIFO cutover runbook. Preserved exact supervisor arguments with only the FIFO-mode child argument added; saved original argv. Confirmed webcam_only, STOP and the recording placeholder before stopping verified old v23 PID 2015338. Launched unchanged reviewed m5 launcher; game PID2033250 and start_ticks verified before updating game.pid. The existing CPU partition loop follows it.

Intrinsic GO: 600 game-window delegate calls for 600 frames, zero duplicate/missed/wrong-thread calls, 1920x1080 A2B10G10R10, pitch1920/rows1080, nonblack=1, jpeg_ok=1, held_ref=1, offscreen=1. The director acquired main.mjpeg automatically. An actual HLS frame was extracted on the pod and visually inspected: the seated streamer and room are visible. The in-game monitor remains blank under the preexisting source mismatch; no PC start or arming was performed.

Warm 10-second windows showed game59.5-59.6fps, main capture/write58.3-58.7fps, rate_skipped rising and intermittent queue drops. Intrinsic GO does not meet the >=59.5 unique-director-fps acceptance gate. No long ABBA or acceptance soak has been claimed.

## Kimi review

The worker's immutable REVIEW-MAP maps the current native output and installer application logic to exact-version approvals, including N1b/N2a/N2b. The coordinator separately closed the documented Python preamble gap: APPROVE, verbatim question/attachment/answer under `kimi/native-v24-preamble-*`. The guarded build wrapper was reviewed before its prior commit.

A reversible cadence diagnosis was approved with 10-second warmups, 120-second windows, repeat60 baseline, six-core and loss gates, and early stop on sustained queue/slot growth. Question/attachment/answer under `kimi/native-v24-cadence-*`. It does not establish delivery capacity or replace the required ABBA, >=8-hour soak, fault tests and owner acceptance. The bounded cadence diagnosis finished with exit0 and restored t.MaxFPS60; its own MEASURING lease was removed. The two 120-second baseline windows captured6981/6944 and wrote6862/6747 frames, with119/200 queue drops. The headroom61 window stopped early at75.08s due sustained drops: captured4477, written4446, queue drops28, no slot drops, game CPU~4.25cores. No62 test was run because61 was not clean. These short, changing windows do not establish acceptance or a reliable long-term improvement. Full samples persist under `/workspace/sub01-codex-v24-build/cadence/`.

The successful binary, applied header/source and receipts were copied to `/workspace/sub01-codex-v24-build/artifacts-v24/`; all hashes match the build receipt. Runtime unchanged by this archive step.

## Desktop-rate diagnosis

The partner approved a single-flag desktop60-to30 test while keeping native cap60/main60/output60. Its30-second rolling loss reached2.37% (captured1731,written1692,queueDrops40,slotDrops1), triggering the specified early stop. The collector exited0, removed its own lease, and the exact previous FIFO supervisor arguments were restored. This is a rejected diagnostic, not a retained performance setting. Verbatim consultation: `kimi/native-v24-delivery-*`.

## Follow-up headroom diagnostic

The partner explicitly approved one cap62 diagnostic after reviewing the failed61 results; no63 was authorized. At62, the producer captured1801 frames in30.025s (~60fps), while1610 were written (~53.6fps), with193 queue drops and one slot drop. The rolling-loss gate reached10.77% and stopped the run. Cap60 was restored with a receipt and the owned lease removed; exit0. Verbatim consultation: `kimi/native-v24-headroom62-*`. This points the next investigation toward writer/consumer backpressure, without proving the component responsible.
