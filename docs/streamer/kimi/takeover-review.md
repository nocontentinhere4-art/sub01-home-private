# Takeover handoff review (2026-10-24, coordinator)

The owner asked that Codex can continue from the exact same point with the same rules and mechanics when the Claude session runs out of usage. Three review rounds (kimi-k3.1-pro) of `AGENTS.md`, the HANDOFF "Takeover" section and `tools/pod/README.md`.

## Round 1

**Changes requested — small additions, but needed for an exact resume:**

- **Pin the code/deployed baseline.** Record branch HEAD and pushed-remote SHA, clean/dirty status and any uncommitted-patch locations, plus the deployed v23 and director source commits/artifact hashes and absolute pod workdir. Commit/push this handoff and all referenced spec/RUNBOOK/review files; give Codex the resulting branch tip.
- **Clarify the in-flight v24 worker.** State running/stopped status, PID, log and installer paths, last completed stage, and whether pod source/binaries were already modified. “Redo if commits are absent” is unsafe until partial work is inspected and any old worker is stopped; otherwise work could be lost or two builders could overlap.
- **Make rollback executable.** Provide exact commands and post-rollback health checks. Specify which backup/artifact `m3` will load—or why v24 is inert under `m3`—and include restoring director `x11`/`webcam_only` and checkpoint p5 with `cam2_fps=30`. Also state whether the sawtooth tools manage `MEASURING`; otherwise add lease creation/removal for ABBA and soak.
- **Harden guard resumption.** Record PID 63’s expected command/start time. On the first takeover at or after 00:20 UTC, verify it is still that paused guard before `kill -CONT`; handle stale PIDs/pod restarts, then verify polling, log the change and notify the owner.

Rules and secret storage are otherwise adequate. Clarify only that `pods.json` is pre-provisioned or the Jupyter password arrives through an approved secret channel, since secrets must not enter chat. After these edits, save the required Kimi review of the final diff before committing.

## Round 2

Remaining blockers:

- **Baseline pin:** the branch tip is mutable; after the next push, `git log -1 origin/claude/happy-einstein-1x0561` no longer identifies the takeover baseline. Add a mandatory post-push step recording the full takeover commit SHA—preferably with an immutable tag—and resume against that SHA.
- **Rollback executability:** `$P` is not defined in the handoff, the tuning command does not identify the uploaded JSON’s absolute path, and the relaunch depends on a `/tmp` script that a pod restart wipes. Use absolute paths and restore/invoke the repository copy. Also explicitly restore `binaries-v23-linux` before the known-good m3 relaunch if v24 may have replaced `Binaries/Linux`; m3 itself does not select v23.

## Round 3

APPROVE
