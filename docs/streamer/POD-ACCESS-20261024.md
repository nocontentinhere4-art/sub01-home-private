# Pod command status repair

The terminal helper reported the status of an intervening echo instead of the command; the kernel helper discarded the subprocess status. Both could report success after a failed build or test. The kernel helper also required a Linux-only CA path.

The terminal wrapper now preserves the subshell status immediately and puts multiline command delimiters on separate lines. The kernel wrapper requires its invocation-specific exit marker, an OK execute reply and idle state; errors and disconnects fail closed. Negative signal exits map to 128 + signal. Both reject observed duplicate or out-of-range completion markers and failed HTTP responses. The terminal stops at the first complete marker; it cannot inspect data arriving after completion. TLS verification remains enabled, with the default trust store when the custom bundle is absent.

## Validation

Regression coverage runs the actual CLI scripts through a fake Jupyter transport which executes their submitted payload using real local child processes. It covers successful and failed exits, stdout/stderr and secret masking, a here-document, signal termination, disconnects, missing/duplicate/out-of-range markers, HTTP errors, kernel errors, reply errors, timeout errors and idle/reply ordering. These are transport tests, not native scene acceptance.

All 26 regression tests pass. Live private Jupyter probes returned exactly the expected status (0, 7 and 42) through each helper and preserved stdout. No game, director, supervisor, agent, STOP, lease, Vagon or provider state was changed.

## Kimi review

The initial broad design request exhausted its reasoning budget without an answer; its full question and response are preserved. The focused follow-up approved the limited repair with no concrete blockers and required strict completion checks and verified TLS. Both consultations are saved verbatim in `kimi/pod-helpers-design*-20261024-*`. The exact diff review found one blocker: a status split between digits could be accepted before the line ended. Detection and parsing now share a regex requiring the actual newline, and a regression splits status 42 after its first digit. The follow-up review returned `COMMIT YES`. Both review rounds are preserved verbatim in `kimi/pod-helpers-review*-20261024-*`.
