# Kimi review (2026-10-24): director recording retention

Context: the overnight disk-full incident (an all-night recording filled the 20 GB root disk and every service crashed). Both findings applied: retention retries up to three passes, skips segments it could not delete and counts them toward the cap, so a stuck file never stalls reclamation; non-finite `--min-free-gb` values are rejected at config time and any arithmetic error is caught inside `apply_retention`. Tests cover the cap, the protected in-progress segment, free-space deletion and an undeletable segment.

1. **Medium — a failed deletion can permanently stall free-space reclamation.** Victim selection assumes every selected file's bytes will be freed, but `apply_retention()` silently ignores `unlink()` failures and selects no substitutes. For example, if another 60 MB is required, each tick can select the same undeletable 60 MB file, calculate that it would suffice, stop, and fail again, even though later segments are deletable. Track successful deletions and continue selecting victims, re-checking free space, until the target is met or candidates are exhausted.

2. **Low — non-finite thresholds escape the "never raises" guarantee.** argparse accepts `--min-free-gb nan` and `inf`; both pass the `< 0` validation. `int(cfg.min_free_gb * 1024 ** 3)` then raises `ValueError` or `OverflowError`, which propagates through `to_thread()`. Reject non-finite values using `math.isfinite()`.

No blocking normal-path finding: the counting leaves exactly N segments after successful cap deletion, ffmpeg's next segment is either absent from the snapshot or protected as newest, and retention does not traverse the HLS directory.

## Follow-up review of the final code (`q-retention-delta.txt`, 314 s)

> Both original findings are resolved: retries are bounded at three, failed files cannot be reselected and still count
> toward the cap, and `min_free_gb` conversion is guarded. I see no wrong-file deletion, deletion of the current writing
> segment, or infinite loop.
>
> One remaining exception-path concern: `apply_retention` is not unconditionally "Never raises." `list_segments(...)`
> is outside any `try`; if it can propagate a filesystem `OSError`, including on a later pass, that exception escapes.
> The `events(...)` callback can likewise propagate an exception.

Applied: the passes run inside `try/except OSError` and the `events` call is isolated. The default free-space floor is now
3 GB (above the backend's 2.5 GB reserve; at 60 fps NVENC a 10-minute segment is ~160 MB).
