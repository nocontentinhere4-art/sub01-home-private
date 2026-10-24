# Kimi consultation (2026-10-23): agent shadow mode, guard rails before unattended runs, the owner's credentials and installs decisions

Model kimi-k3.1-pro; brief in `q-agent-safety.txt` (design before implementation). The answer below is verbatim; what was adopted is listed in AGENT.md ("Shadow model", "Guard rails before unattended runs", "Logins and installs") and in the worker report.

## Answer

**S — CHANGE, mostly KEEP.** The 60 s timeout, two in flight, 240/h skip-not-queue policy, and absence of act authority are sound. Retain task references, consume exceptions, and cancel tasks on shutdown. Make `valid` mean full `validate_decision`, with `parse_valid` separate; report null/null agreement separately so idleness does not inflate agreement.

Agreement is **not correctness**. It is sufficient for the 30-minute trial as a comparison/health signal, not a cutover or safety metric. Add `click_in_target` only where a genuine target box or human label exists; otherwise use `null`. For mark-versus-point agreement, require containment in the mark box, not merely proximity within 40 px of its centre. Save structured actions and frame references for later labelling. Do not send detected private/credential frames to shadow without separate approval; text redaction does not redact images.

**A — CHANGE.** Keep 2 s re-observation and `stale_refused`. Treat dHash as correlation, not identity: bind dispatch to frame ID, capture timestamp, decision ID, and a single-use action ID. The 32×18 mean-diff threshold of 12 can miss small dialogs and focus changes; add a target-region check for clicks/types, while acknowledging Vagon remains heuristic.

The game exemption is acceptable only for `w/a/s/d/space` during an active game routine, with a frame ≤2 s old, connected/nonblack stream, and every other gate intact. Do not exempt clicks, Enter, or Tab; release held keys after timeouts.

After a timeout, a newer frame alone must not authorize repeating non-idempotent login/download/install/UAC actions. Require an observed postcondition or admin resume.

**B — KEEP, with enforcement clarification.** The values 3/decision, 20/rolling-60-s, and 3 failures are reasonable trial settings. Enforce them in one broker across model/chat/routine/quiet paths, reserving capacity before dispatch and counting timeouts. At 2 s cadence, 20/min will intentionally throttle. `/resume` should require a fresh usable observation and cancel pending routines/chat steps.

**C — KEEP.** Use monotonic expiry and no automatic renewal. Expiry should release inputs and cancel routines, although an already launched installer may continue. Re-arming a lease must not implicitly clear `held` or frozen/black latches; require explicit resume.

**D — CHANGE.** Use decoded-pixel/perceptual comparison plus capture-timestamp liveness, not only encoded screenshot bytes; compression can change while the picture remains frozen. Add missing-new-frame detection in both modes. The 60 s and 0.03 thresholds are reasonable fail-safe starting points. On latch, release inputs immediately. Resume only after admin resume plus two fresh, connected, nonblack observations 2 s apart.

**E — CHANGE.** Process separation and the 5 s/30 s/60 s timings are reasonable, but do not calculate the rate cap solely from the agent’s `events.jsonl`: it can die before logging. Consume runner/broker dispatch receipts. Fail closed after grace on unreadable state, verify `/pc/session` succeeded, and place STOP where the agent cannot delete it. A watchdog on the same pod cannot survive pod failure.

**F — CHANGE.** Disable request-body logging at runner/proxy layers too. On private screens, omit `raw` and generated history rather than relying on 1,500-character pattern redaction. Mask every type action while privacy is active, including shadow `target` fields. Redact URL user-info/query/fragment and relevant page text: OAuth and reset links can contain secrets without anything being typed. Suppress generated `say` and chat answers on private screens; use a fixed neutral line.

**O1 — CHANGE.** **KEEP `owner_infra` blocked** and report that decision. Evaluate canonical hosts after redirects using proper domain-boundary/eTLD+1 matching. Also distinguish authentication from account mutation: password/email/2FA/recovery/deletion changes should require explicit owner confirmation, not merely `--allow-credentials`.

“Never guess” is not a lockout control. Start with at most **two possible authentication submissions per host/privacy session per rolling 10 min**, then require admin resume; count ambiguous Enter/click submissions, not just secret typing. Vagon cannot guarantee lockout prevention.

Model-set `private_screen` is not a security boundary. Require director acknowledgement that the desktop is hidden **before** dispatching secret text. Keep privacy active until two fresh nonprivate observations 5 s apart. Password heuristics miss values such as `letmein` and `123456`.

**O2 — CHANGE substantially.** Keep pod installs refused. **DROP the vendor-token heuristic**: `vlc-download.com` can pass while `videolan.org` fails. Limit chat installs to Steam, Microsoft Store/winget, and GitHub releases whose official owner/repository is curated or owner-confirmed; support other vendors through a curated domain map.

Strictly parse winget package IDs and flags; the shell denylist already misses `pwsh`, `msiexec`, and `rundll32`. Apply provenance restrictions to model-driven installers too, preferably with a limited Windows user and restorable snapshot.

`install_window_s` is prompt-only, not enforcement. If autonomous UAC remains, narrow it to one install session and one claimed approval within **120 s of installer launch**. Owner confirmation is the only actual UAC gate. Because Vagon hides post-click URLs and code cannot authenticate UAC prompts, official-source and UAC enforcement cannot be guaranteed.

**Three highest remaining risks**
1. A malicious or prompt-injected installer plus UAC can compromise the Windows PC.
2. A privacy-detection/redaction miss can expose account data to the stream, logs, or Kimi.
3. Screenshot-only Vagon operation cannot reliably verify URL, focus, purchase state, or installer/UAC identity; several controls remain advisory.

