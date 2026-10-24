# Native v21: Kimi's code review (2026-10-24 ~00:33 UTC) and what changed

Model `kimi-k3.1-pro`, 644 s. Question: `q-native-v21-review.txt`; attached: the installer's C++ diff on the pod v20
sources, the launcher diff (game l -> m) and `scripts/streamer_cpu_partition.py`.

## Kimi's answer (verbatim)

**Verdict: do not ship the current v21 artifacts.** Items 1–5 are blocking; the rendering and telemetry issues below are smaller but should be corrected or explicitly documented.

1. **Make FIFO writes SIGPIPE-safe.** A `write()` after the last reader closes raises SIGPIPE; `O_NONBLOCK`/`O_CLOEXEC` do not prevent it, and default SIGPIPE handling kills the whole game before the writer can handle `EPIPE`. Unless v20 already ignores or correctly blocks SIGPIPE—not shown here—install that handling before any writer starts. Verify with a reader disconnecting during a partial frame write.

2. **Replace the cam2 fd handoff with one state machine.** The atomic fd does not make the protocol race-free:
   - The writer can adopt `HandoffFd`, then the probe can observe `Reader == false` and `HandoffFd == -1` before `Reader.store(true)`, opening a second fd.
   - The writer’s legacy `open()` path can also open its own fd while a handoff is pending.
   
   This can leave an active fd plus a pending writer, delay reader EOF, and carry an old session into a reconnect. Remove the writer’s open path; use one opener and an explicit `Closed/Probing/Pending/Owned` state under CAS or a short `try_lock` protocol. Ensure task shutdown precedes fd destruction.

3. **Close the pause/epoch gap.** `SlotEpoch` protects readback slots, but the shown `WriteFrame()` has no epoch or reader-generation argument. Unless omitted code handles it, an already-encoded frame can cross a no-reader interval and be written to a new reader. Carry the epoch/reader generation through capture, JPEG encode and write; discard mismatches and clear partial `Rest` data on session changes. Also document that in-flight encode means “no work without a reader” is only true after a bounded drain, not instantaneously.

4. **Make the partitioner fail closed on game identity.** If the PID file is missing, unreadable or stale, `read_pid()` returns an empty set and `plan()` can move the actual game from 0–5 to 6–9. Abort the apply pass unless the expected live game PID is present; validate executable and process start time to limit PID-reuse errors. Also decide descendant policy explicitly: currently only the exact game PID gets 0–5, so shader workers and other children are reclassified and moved to 6–9 on the next pass despite the launcher’s inheritance comment.

5. **Qualify partition scope and repair restore/thread handling.**
   - Only uid 1001 is scanned. Other users remain free to use 0–5, SMT siblings and cgroup quota; a root-owned Xvfb would not even be detected. This script cannot provide core exclusivity.
   - `--restore` does not restore original affinities: `range(os.cpu_count())` is merely a guessed full mask, new threads can be missed, and a still-running interval partitioner will immediately repartition. Stop the loop first and use saved masks or a validated cpuset-effective mask.
   - Exiting-thread `ESRCH` is benign, but the snapshot/apply TOCTOU remains. Separate it from `EPERM`/`EINVAL`, log real failures, and do not return success when critical pins failed.

6. **Narrow the console whitelist.** Game-thread `GEngine->Exec()` is generally the correct execution context; the problem is the breadth of the commands. `r.`, `a.`, `fx.` etc. permit far more than tuned scalability values, including expensive or disruptive runtime changes, while `csvprofile` can enable sustained profiling overhead. Prefer exact cvar names with finite numeric ranges and explicit `csvprofile start/stop` commands. The charset does usefully block separators, newlines and paths. Also, `console_applied` currently counts attempts even when `Exec` returns false, and value lookup fails for `r.Foo=1` because it searches for the whole string.

7. **Tighten the light/visibility claims and lifetime.** The channel masks are consistent for **direct** lighting: body-only gives the light channel 1 and the body channels 0+1. They do not guarantee isolation from Lumen GI/reflections, so “never lights the chair/desk/walls” is too strong. Set or verify `IntensityUnits == ELightUnits::Candelas`; otherwise `SetIntensity(Cd)` does not itself establish cd units. `SetOnlyOwnerSee(false)` is persistent and global to other views/captures, and lighting channels are likewise left modified—scope them to intended body primitives and save/restore original state if cam2 is not process-lifetime permanent.

8. **Label the PERF values as estimates.** These globals are engine-produced, latest per-frame CPU timing samples, not six synchronized durations for each game tick. Sampling once per tick can repeat or miss render/RHI samples. `GSwapBufferTime` is time around the swap/present path, not end-to-end present latency. Do not sum the six fields as a frame-time breakdown.

9. **Sanity-check the traced chair result.** A successful trace on any chair actor now overrides all shape filtering. A seat/armrest hit could therefore be selected as the backrest. Validate the selected part and measured gap before applying a potentially large chair move; `trace=%d` in the log currently means only “has a primitive,” not “trace succeeded.”

Minimum release gate: repeated reader disconnect/reconnect and cam2 toggle tests with stable fd count and no stale frames, plus missing/stale-PID partition tests proving that **no affinity changes** occur. The private-JSON helper and omitted pause/shutdown code cannot be fully audited from this diff.

## Response (applied in the reviewed build v21 = game m2)
1. SIGPIPE: already handled by the v20 writer (cam2 layer): every write runs with SIGPIPE blocked (`pthread_sigmask`) and a
   pending SIGPIPE is consumed before the mask is restored; the reader-leaves case is in the tests (the driver process survives
   EPIPE). Not visible in the v21 diff, no change needed.
2. fd hand-off: fixed. The game thread's probe is now the ONLY opener (the writer's own `open()` path is removed); the writer
   adopts a pending fd by storing `Reader=true` BEFORE clearing the slot (only the probe sets it, only the writer clears it), so
   the probe can never see "no reader, no fd" while an fd is being adopted. The destructor closes a pending fd.
3. Frames across a no-reader gap: with no writer-side open, a frame still in flight when the reader left finds no fd and is
   dropped (`dropped_no_reader`), never written to the next reader; `Rest` is cleared on adoption and on EPIPE; the existing
   epoch drops stale readback slots after a pause (a no-reader period is a pause).
4. Partitioner fails closed: a pass changes nothing unless a given pid is alive, ours and an `UnrealEditor-Cmd ...
   -Sub01StreamerVisual` process (tests: stale/foreign pid -> 0 changes, exit 1). Descendant policy explicit: the game process
   and Xvfb :99 on the game set, everything else of uid 1001 (the game's own child processes included) on the other set.
5. Scope/restore: documented that only uid 1001 is moved (no core exclusivity); `--restore` uses the cgroup's
   `cpuset.cpus.effective` and says to stop a running `--interval` loop first; ESRCH counts as `gone`, EPERM/EINVAL as
   `failed`, a game thread that could not be pinned makes the pass exit 1.
6. Console: narrowed to `<cvar>` (query) or `<cvar> <number>` under the prefixes, the exact `t.MaxFPS`, and exactly
   `csvprofile start|stop|frames=<n>`; no `=` sets; `console_applied` counts only handled commands (unhandled -> refused).
7. Light: wording fixed (direct light only; Lumen's bounce is not channel-masked). Candela units were set at creation in v20
   (`SetIntensityUnits(ELightUnits::Candelas)`). OnlyOwnerSee/lighting channels: streamer mode is the whole process lifetime,
   documented.
8. PERF: documented as the engine's latest per-frame samples taken once per tick (estimates; not a breakdown to sum).
9. Chair trace: the trace now runs only on the shape-selected backrest candidates, hits kept within -40..+30 cm of the pelvis;
   the part log says `prim=` (has a primitive), not `trace=`.
