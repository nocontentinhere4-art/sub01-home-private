# Kimi consultation (2026-10-24 ~15:40 UTC): supervised sidecars and the monitor feed's privacy gate

Question: `q-sidecars-design.txt` (324 s, 15441 prompt + 13933 completion tokens of which 12319
reasoning). Attached: excerpts of `scripts/streamer_up.py` (constants, `build_specs`, start gate, kill/status),
`scripts/streamer_monitor_feed.py`, `scripts/streamer_hls_serve.py`, and excerpts of the desktop runner (`/pc/state`,
`VagonState.public`, `privacy_locked`), the director's privacy cut, AGENT.md and the RUNBOOK. A first attempt with
`--max-tokens 24000` and the whole supervisor attached came back empty (16384 completion tokens spent reasoning); the
answer below is the second attempt (64000 tokens, supervisor excerpts only). Answer, verbatim:

Overall: sound design. I would change **B1 and B3** before coding. This is fail-closed for signal loss/staleness; it cannot be fail-closed for private content that appears before either signal detects it.

## A — Supervisor services

**A1 — Accept.** The ports, flags, timeouts and restart policy fit the existing model. Adding both services means `status` will now return 1 when either is down, even though director HLS output remains opt-in; that is reasonable if the HLS server is intentionally always supervised. Update the ORDER-pinned tests and supervisor documentation.

**A2 — Accept.** `REQUIRES=("xvfb",)` and no `restart_with` are correct: X loss is handled by ffmpeg backoff, while desktop loss must leave a healthy monitor service showing neutral. Pass exactly the desktop child’s display, without the screen suffix. Health/start success must not require `showing == "screen"`.

**A3 — Accept, with small implementation requirements.**
- Register `/healthz` explicitly before `/{name}`.
- Return HTTP 200/`ok:true` for a functioning server even without a playlist; use `playlist:false, playlist_age_s:null`. Otherwise opt-in HLS would look like a supervisor failure.
- Warn about a director/HLS directory mismatch on real starts as well as `--dry-run`; parse both `--hls-dir X` and `--hls-dir=X`.
- Giving HLS `base_env` rather than `service_env` correctly withholds the token.

**A4 — Accept.** Leaving the monitor running through `kill` is safer than killing it: a dead writer cannot replace a retained texture. Update `do_kill`/`cmd_kill` text and the module docstring, not only the printed summary. The monitor status line should report the observed state without treating privacy itself as unhealthy.

## B — Monitor privacy gate

**B1 — Change slightly.** The signal set is right, but:
- Do not reuse `read_tail_records()` unchanged: it converts every `OSError` into `[]`, so it cannot distinguish “no file” from EACCES/EIO as required.
- Define deletion, truncation, empty files and inode replacement explicitly. After an observed cut, file disappearance alone must not reopen the gate.
- Validate the runner schema fail-closed. In Vagon mode, a missing/unknown `vagon`, `kind`, or required connection field is malformed/private, not an implicit streams-kind clean answer.
- Your workstation predicate is **stricter**, not identical: the runner uses `workstation and not vagon.connected`; you additionally require `phase=="connected"`. Keeping the stricter predicate is fine, but document it.

**B2 — Accept.** Opening must require all inputs to be currently valid, fresh and continuously clean for 1.0 s—not merely an absence of new PRIVATE observations. Any error, malformed answer or stale input resets the opening timer.

**B3 — Change one important point.** Stopping capture, dropping parsed screen frames and emitting neutral frames is right. However, “neutral unavailable, therefore write nothing” is **not fail-closed**: the game can retain the previous screen image indefinitely. Render and validate the neutral JPEG before permitting any screen capture; if it cannot be produced, keep the feed down/unhealthy and never start x11grab. Also, an immediate neutral write is best-effort when the FIFO is full—retry and do not claim it was displayed.

**B4 — Accept.** Reap the old ffmpeg, discard its parser/buffers and pending output, then create a fresh process only after reopening and when a reader exists (unless `--always`).

**B5 — Accept, with acknowledgement semantics.** `showing:"neutral"` should mean a complete neutral frame was actually written for the current cut, not merely that the gate is private or a write was attempted. Add a cut-specific generation/`neutral_cut_id` or equivalent timestamp so an old neutral result cannot acknowledge a new cut. Neutral-renderer failure should make health not OK.

**B6 — Accept.** Reject `--no-privacy-gate` unless `--test-source` is explicitly present; never permit it through a real x11grab configuration.

**B7 — Accept.** A reader connecting during a cut must receive neutral output and no newly captured screen output. Buffered bytes from before the cut can still precede that neutral frame; the current FIFO design cannot erase them.

## Questions

**Q1 — Accept your view.** Use the layout file and runner as first-hand inputs. Do not make the director necessary for opening: that would couple monitor safety to director availability. `/director/state` is useful as the director’s acknowledgement, not as a superior privacy source.

**Q2 — Use immediate neutral plus periodic neutral; 2 fps is sufficient as a starting point.** Stopping writes is unsafe because of texture retention; full-rate neutral adds decoding work without a meaningful privacy benefit. The excerpts do not establish the game’s frame-freshness timeout, so verify that 0.5 s between frames is comfortably inside it.

**Q3 — Agree.** Stop and relaunch, provided frame offering also checks the gate so an already-scheduled read cannot leak frames while ffmpeg is terminating.

**Q4 — Agree.** A malformed/half-written last line should close the feed immediately even though the director retains its current state. A transient extra cut is preferable to opening on ambiguous input.

**Q5 — Sensible initial values.** They provide roughly four layout checks and at least two runner checks during a clean resume window. Use monotonic clocks for staleness/hysteresis. Explicit request/read failures close immediately; 2.5 s is only the silent-staleness backstop. Measure the complete line-append/runner-change → neutral-write latency in tests.

**Q6 — Accept; no inherent start/stop/kill breakage.** First-start settling still applies, stop becomes reverse order (`hls`, `monitor`, then `director`…), and kill remains unchanged except for messaging. Keep `build_specs` pure and ensure monitor/HLS health is available while neutral or without a playlist.

**Q7 — Yes, add the monitor acknowledgement before typing credentials.** Require it freshly, alongside the director acknowledgement, for the same `privacy_id`; never cache it. It should prove a post-cut neutral write, not just `private:true`. Until then, the director ack alone leaves the monitor’s polling/write window open. Even this ack proves a FIFO write, not that the game decoded it; a game-side texture-generation ack would be the stronger version. Also document FIFO residue as pipe-capacity-dependent, not guaranteed to be exactly two frames.

## Missing / follow-ups

- **Feed death is still not fail-closed.** Only the game can reliably clear a retained texture after the writer crashes. Add a game-side no-valid-frame deadline that restores a neutral texture, and require complete JPEGs/resynchronisation after reconnects.
- **The pre-detection gap remains structural.** For a strict guarantee, put login/account activity on a separate, never-captured display or capture an already privacy-filtered source; raw x11grab plus classification cannot provide one.
- **HLS history is unchanged by a cut.** Existing segments/playlist entries can remain locally readable; `kill` does not purge them. Document this rather than implying neutral output erases recorded content.
- **Migration:** stop the two hand-run sidecars before supervised startup; stale listeners/FIFO state otherwise make testing and health interpretation ambiguous.
- Failure-inject layout truncation/rotation, runner timeout/401/malformed JSON, Xvfb loss, full FIFO/reconnect, slow ffmpeg termination, missing neutral JPEG, and `kill` during an active cut. Scrub the admin token from ffmpeg’s inherited environment as additional least-privilege hardening.


## What was applied

- **A1-A4 accepted as proposed.** `ORDER` = xvfb, desktop, voice, agent, director, monitor, hls; ports 8840/8839 with
  the automatic `--monitor-*`/`--hls-*` flags; `REQUIRES monitor = (xvfb,)`, no `restart_with`; `--hls-dir` (default
  `<streamer-dir>/hls`) with a WARNING on `start` and `--dry-run` when the director's `--hls-dir` differs or is absent
  (both `--hls-dir X` and `--hls-dir=X` parsed); the HLS server answers `GET /healthz` 200 without a playlist
  (`playlist: false, playlist_age_s: null`), registered before `/{name}`; the HLS server and Xvfb get no operator token
  (and the health probe sends it only to children that hold it); `kill` leaves both sidecars up, `do_kill`/`cmd_kill`
  texts and the module docstring updated; `status` prints a `monitor:` summary of what the feed reports, without
  treating privacy as unhealthy.
- **B1 changed.** Own reader `read_layout()` (absent / clean / cut / unreadable: EACCES and EIO are not "no file");
  `LayoutWatch` keeps a cut when the file disappears, is emptied or truncated (`layout_cut_gone`), ends it only with a
  valid line without the privacy reason; a rotated file's last line decides (as for the director). Runner schema
  strict: unknown `pc_mode` or Vagon `kind`, a workstation answer without a boolean `connected` and a string `phase` is
  `runner_bad_answer`; the stricter predicate (`connected` AND phase `connected`) is documented as such.
- **B2** as proposed: any reason, hold or stale input resets the 1 s opening timer (monotonic clock).
- **B3 changed.** No screen capture without a validated neutral JPEG: the gate holds closed (`neutral_unavailable`),
  `/healthz` answers 503 (`ok: false`) so the supervisor reports and restarts the feed; x11grab never starts. The
  neutral write is best effort: a partial write is finished (`FifoSink.flush`) and retried every 0.05 s, never claimed.
  The close itself (drop the screen tail, write the neutral frame) now runs synchronously inside the observation that
  closes the gate, before ffmpeg is stopped (a slow ffmpeg exit no longer delays the neutral frame).
- **B4** as proposed (old ffmpeg reaped, parser dropped, a new process only after reopening and with a reader).
- **B5 changed.** `showing` is `neutral` only after a WHOLE neutral frame went into the FIFO for the current cut
  generation, else `pending` (`nothing` is gone); `privacy.cut_gen` and `privacy.neutral_ack {gen, privacy_id, t,
  reasons}` let a later agent check bind the ack to its own `privacy_id`.
- **B6, B7** as proposed (tests: `--no-privacy-gate` only with `--test-source`; a reader that connects during a cut gets
  the neutral frame within 0.5 s and no screen frame).
- **Q5:** latency measured in the real-ffmpeg test: 0.20 s from the agent's layout line to the first neutral frame read
  from the FIFO, 0.45 s from the runner's privacy flag (asserted < 1.0 s and < 1.5 s).
- **Missing list:** ffmpeg (capture and the neutral render) gets the feed's environment without `SUB01_ADMIN_TOKEN`,
  `*_API_KEY`, `*_TOKEN`, `*_SECRET`; tests inject runner timeout, 401/403, 500, non-JSON and redirect answers, layout
  deletion, truncation, garbage and rotation, a full pipe, a missing neutral frame. RUNBOOK documents the migration
  (stop the hand-run sidecars first), the HLS history a cut does not erase, the FIFO residue as pipe-size dependent,
  the structural pre-detection gap and the dying-feed texture retention.

## Not done here, with the reason

- **Q7, the agent waiting for the monitor feed's acknowledgement** before typing a credential: an agent change outside
  this brief (the feed now exposes what it needs: `showing: "neutral"` plus `privacy.neutral_ack.privacy_id`). Listed as
  a follow-up in the RUNBOOK and the report.
- **A game-side no-valid-frame deadline** for the monitor texture: native work (the feed cannot clear a texture after it
  died). Follow-up.
- **The game's freshness timeout** for the monitor texture is not known from the Python side; the RUNBOOK asks to check
  that 0.5 s between neutral frames is inside it.
