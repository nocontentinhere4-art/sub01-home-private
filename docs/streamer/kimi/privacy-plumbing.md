# Kimi consultation (2026-10-23/24): privacy plumbing (director privacy cut, runner --allow-credentials)

Model kimi-k3.1-pro through tools/ask_kimi.py on the pod. A first combined brief (director + runner, 8 questions)
used its whole 30000-token budget reasoning and gave no answer; it was split into `q-privacy-director.txt` (with
excerpts of the director and of the agent's privacy code) and `q-privacy-runner.txt` (with the runner's URL policy and
the agent's HOST_CLASSES), 64000 tokens each. The final diffs were reviewed with `q-privacy-review-director.txt` and
`q-privacy-review-runner.txt` (section "Final review" below). The answers are advice to weigh, not project policy; what
was adopted is listed after each.

## Design answer: director

1. **Do not set `desktop_hidden` at spawn; wait for run-scoped output progress.** Spawn proves process creation, not that the new run is producing frames or that an older ffmpeg cannot still write. Require the first `-progress` block with `frame>0` for the **current PID and run prefix**, no pending restart/switch, and termination of every previous ffmpeg writer. For a live switch, use `ret:0` plus subsequent frame progress as the liveness check. This prevents acknowledging while a stalled launch has produced nothing—or while an orphaned desktop-layout ffmpeg is still recording. The excerpts do not show process teardown, so exclusive ownership cannot be assumed.

2. **Replace the `_switching`-only guard with an epoch-bound confirmation; there is a real launch/switch race.** Privacy can end, an away switch or restart can be prepared, and then a new privacy ID can arrive while `live_layout` still says `webcam_only`. In restart mode there may be no map command and therefore no `_switching` marker; meanwhile `_run_once` may already have computed a non-private launch. Change this by incrementing a layout/privacy epoch on every wanted-state change, restart request and process exit, and clearing confirmation synchronously. Require `desktop_hidden` to match the current **privacy ID, epoch and run**. Let `apply_layout` record actual `live_layout` after a valid reply, but if its captured epoch is stale, immediately apply the newest wanted state. Likewise, `_run_once` must not confirm privacy if the epoch changed during spawn.

3. **Only an explicit, matching end transition should end privacy.** An arbitrary later JSON record, an invalid layout request, or a delayed `privacy_end` from an earlier cut must not expose the desktop during the current cut. Change (b) so active privacy ends only through `privacy_end` with the active `privacy_id`, or the authenticated operator override; mismatched records leave privacy unchanged. Normal layout records must not implicitly end it. If ordinary records are accepted while private, consume appended records in order and persist/checkpoint the recovered state—last-line-only recovery is insufficient once several records can be appended between polls.

4. **Close the agent’s acknowledgement-to-keystroke gap as well.** `broker_check` can still await `freshness` after `privacy_acked`, and dispatch happens later. Privacy could be operator-ended or otherwise change during that interval. Recheck privacy immediately before dispatch, after the remaining awaits, and bind the check to the current privacy ID/epoch; keep privacy active until the credential action has finished. A GET followed by an external keystroke cannot be made atomic by the director alone, so an operator force-end must be documented as capable of invalidating the guarantee unless it also waits for the agent to quiesce.

5. **Treat `ret:0` as part of a safe-to-type gate, not as an output-flush barrier.** Your causal argument about future keystrokes is correct: encoder lookahead, NVENC buffering and B-frames can delay or reorder pre-switch images, but cannot put subsequently typed text into those images—provided selection changed before the ack and no away-switch race occurs. However, old frames can still show the private page that triggered the cut. The roughly **24 seconds** of HLS playlist (`6 × 4 s`), plus the open segment and player buffers, are not cleaned by a map command; MP4 already written remains, and RTMP already sent or queued in the tee FIFO cannot be recalled. Document `desktop_hidden` accordingly, and use a separate “outputs flushed” notion if viewers must no longer see old desktop content.

6. **Keep 409 for plain POSTs during privacy, but fix the normal privacy-end ordering.** Accepting a POST as a deferred restore target is not a drop-in change with last-line-only log semantics. The current agent can append `privacy_end` and POST before the director has polled it, so a routine end can receive 409. Re-poll the log before deciding the POST response, or preferably make agent-initiated ending one atomic director operation carrying the layout and expected privacy ID, with the JSONL line written as audit. If you later accept deferred restore requests, return a clearly deferred response such as 202, never an apparent on-air layout change.

7. **Remove the fixed-layout and launch-decision bypasses.** The current fixed-layout early return would otherwise prevent privacy records from being polled at all, and launch/cam2 decisions based on the stored requested layout can still prepare a room/cam2 run while privacy should dominate. Use one effective-wanted-state decision everywhere: privacy first, then `--layout`, then the logged request. Privacy must still be polled with `--layout`; the fixed layout becomes only the restore target. Unused desktop/cam2 inputs may remain open, but they must not influence the private graph or trigger a cam2 relaunch.

8. **Agreed: never end privacy automatically after a maximum duration.** A timeout can expose a login page precisely when the agent has crashed. Fail closed, emit an operator-visible stuck-privacy alert, and retain the explicit `end_privacy:true` override with an audit record containing the ended ID and restore layout. Revoke `desktop_hidden` before beginning the restore switch.

**Adopted:** (4) documented in RUNBOOK.md (hold the agent with STOP before an operator `end_privacy`: an end forced
between the agent's acknowledgement and its keystrokes would put the typing on air); (5) `desktop_hidden` documented
as "safe to type from now on", not "outputs flushed" (the HLS window, the open segment, RTMP already sent); (6) 409 kept
for plain POSTs during a cut, the handler re-reads layout.jsonl first so the agent's end line followed by its POST is
accepted; (7) privacy is followed with a fixed `--layout`, and launch, cam2 and switch decisions all use one
`wanted()` (privacy first); (8) no timer end, a `privacy_still_on` event every 10 minutes and `privacy_seconds` in state;
`desktop_hidden` is revoked the moment the end line is read, before the restore switch. From (1): nothing is
acknowledged while an ffmpeg of an earlier director survived its reap (`stale_ffmpeg_survived`). From (2): when the
wanted layout changed during a live switch, the follow-up switch is kicked at once.

**Not adopted, with the reason:** (1) waiting for the first `-progress` block with frames after a launch: runs are
strictly sequential (the next ffmpeg starts only after the previous one exited), and a launch on the private graph that
produces nothing outputs nothing; the delay (up to the 5 s stats period) would only slow the acknowledgement. (2) an
epoch: `live_layout` is set only on a confirmed reply or at a launch, a switch in flight (`_switching`) or a pending
relaunch (`_restart_reason`, which also covers restart mode, where no map command exists) makes `desktop_hidden` false,
and an unanswered switch sets `live_layout` to unknown; the races named (end, switch away, a new cut mid-switch; restart
mode) have tests. (3) only a matching `privacy_end` ends a cut: only the agent and the director write layout.jsonl, the
director refuses plain POSTs during a cut, so a privacy line can only be followed by the agent's own end line or the
operator's explicit end; last-line semantics (the coordinator's and the agent's contract) also make restart recovery
exact, which the in-order/matching variant would not be without consuming every appended record.

## Design answer: runner

I would **not** ship this as a blanket `allow_login` exception. The main risks are destination confusion and lifting much more than authentication.

1. **Enforce the remote browser’s final destination, not merely the URL before it is typed.**  
   **Prevents:** an allowed login URL redirecting—or receiving `next`, `continue`, `returnUrl`, or `redirect_uri`—to checkout, data export, OAuth consent, or an infrastructure console after the only policy check.  
   **Change:** require HTTPS in credential mode, recursively validate embedded redirect destinations against the full non-lifted policy, and re-check the final remote URL after navigation and redirects. The excerpt shows no reliable remote-browser URL readback; without one, redirect safety **cannot be guaranteed**, so restrict the mode to fixed, approved login entry URLs rather than claiming general enforcement.

2. **Make every never-liftable rule independent and non-short-circuiting.**  
   **Prevents:** `https://auth.runpod.io/` being classified first as `login` and then having that verdict ignored, despite also matching owner infrastructure; similarly, a login-path match must not hide a money match elsewhere in the URL.  
   **Change:** evaluate owner-infrastructure, money, adult, gambling, private-host, account-change, and export rules before applying any login exception, on both runner and agent. Do not implement the lift as “ignore a returned `login` verdict.” Add contract tests for `auth.runpod.io`, `login.railway.app`, and paths matching both login and money classes.

3. **Lift authentication only—not registration, mailboxes, or whole account portals.**  
   **Prevents:** account creation and acceptance of terms through lifted `register`, `sign-up`, `createaccount`, or `join`; reading reset links/OTPs through Gmail or Outlook; and reaching iCloud mail, photos, files, or Find My. Lifting broad `/account`, `/my-account`, and `/password` sections likewise reaches far more than signing in.  
   **Change:** use exact sign-in endpoint allowances where practical. Keep account creation separately denied unless the owner explicitly grants it. Treat mail/file access and account-portal access as separate capabilities, not side effects of `allow_credentials`; in particular, do not automatically lift all of `mail.google.com`, Outlook, or `icloud.com`.

4. **Add a permanent deny class for delegation, persistent credentials, and data export.**  
   **Prevents:** OAuth consent granting a third party durable mail/Drive/repository access; creation of app passwords, API tokens, SSH keys, passkeys, or recovery credentials; and export of the owner’s data. These can remain useful to an attacker after the browser session ends.  
   **Change:** default-deny third-party OAuth/OIDC authorization and consent, connected-app/permission/integrations pages, app-passwords, tokens/API keys, SSH/security keys, passkeys, backup codes, sessions/devices, email/phone/recovery changes, and “download/export your data.” Explicitly deny `passwords.google.com` and `takeout.google.com`; from the shown runner rules, neither is host-blocked already. Keep `signinoptions`, but broaden beyond exact token matches so routes such as security-checkup variants do not escape. A URL regex cannot reliably distinguish federated sign-in from OAuth consent, so ambiguous flows need denial or owner supervision.

5. **Repair money coverage before relying on `CHECKOUT_PATH`; the wholesale `LOGIN_HREF` lift is not proven safe.**  
   **Prevents:** pages such as `myaccount.google.com/payments-and-subscriptions` and `.../payment-methods` passing because a hyphen is not an accepted boundary, direct `/buy`, `/sell`, `/swap`, or `/bridge` destinations passing because `MONEY_PATH` is not consulted by `blocked_url`, and query actions such as `?add-to-cart=...`.  
   **Change:** apply unconditional money checks to canonicalized path, relevant query parameters, and SPA fragments; include the missing money actions and account-portal payment/subscription sections. On **question 7**, ordinary literal `/checkout`, `/cart`, `/subscribe`, and `/donate` paths remain blocked **if** `CHECKOUT_PATH` stays independently evaluated. That much is sound. Wholesale safety cannot be established because the actual `browse.LOGIN_HREF` expression is not supplied and its other alternatives may not be duplicated; split out the truly login-only alternatives or exhaustively test every one.

6. **Add the remote Vagon console to the never-lifted infrastructure policy, and remove optional policy weakening.**  
   **Prevents:** the remote PC’s browser opening `app.vagon.io` even though the pod’s workstation route lock denies its account pages—the workstation lock does not govern that separate remote browser. It also prevents a deployment without `browse.py` silently losing `BAD_HOST`, trading, and other coverage.  
   **Change:** hard-deny `app.vagon.io` for remote navigation and enumerate every other actual owner console from deployment configuration; the complete list cannot be inferred from the excerpt. Package one mandatory shared policy implementation or run versioned contract tests. Your standalone crypto rule is worthwhile, but it does not repair the rest of the optional-`B` gap.

7. **Canonicalize URLs before classification and narrow the Wikipedia exception.**  
   **Prevents:** browser/server normalization changing the resource after the policy decision—for example, a `/wiki/../checkout` form being treated as an article before normalization to checkout—and encoded or client-side routes avoiding path checks.  
   **Change:** remove dot segments, handle encoded separators conservatively, and apply the article exemption only to genuine Wikipedia article URLs on intended Wikipedia hosts. Test encoded, nested-redirect, query-based, and fragment-based routes, not just straightforward literal paths.

8. **Do not treat the unchanged click policy or existing adult rules as compensating controls.**  
   **Prevents:** sensitive buttons labelled “Authorize,” “Allow,” “Export data,” or “Add payment method” falling outside the shown money/login labels, and direct adult URLs on mainstream hosts passing because `blocked_url` does not consult `ADULT_WORDS`. Conversely, unchanged login labels may also block legitimate “Sign in” controls, making the feature only partially functional.  
   **Change:** add consent, mutation, export, and payment labels where marks are used, and apply adult policy to destination URLs and final-page content. Labels and host regexes still cannot provide a complete adult-content or safe-arbitrary-page guarantee; credential mode needs the destination restrictions above.

9. **Make enablement explicit and bind credential use to agent-task provenance.**  
   **Prevents:** an ordinary restart unexpectedly enabling credentialed navigation because the CLI defaults on, and a webpage’s instructions indirectly causing credential use even though direct viewer login requests are refused.  
   **Change:** default the CLI off as well as the library configuration, parse the environment variable strictly, expose/log the effective mode, and make the agent-only scope non-forgeable. Bind each credential to its intended origin and task; instructions encountered in chat or page content must not expand that scope.

**Adopted** as `remote_url_problem` (every navigate on the remote PC, flag or not, because its Chrome may already be
signed in): (1) URLs embedded in query values and the fragment (`continue=`, `redirect_uri=`, `q=`) are checked with the
same rules, three levels deep (`redirect-target (...)`), and a login page over plain http is refused (`insecure-login`);
the remote browser's final URL cannot be read back (pixels only): documented as a limit. (2) `blocked_host` keeps
iterating past a skipped `login` match, so `auth.runpod.io` and `login.railway.app` are `owner-service`; tests added,
also for a path matching both login and money (`/login/checkout`). (4) refused: password vaults
(passwords.google.com, 1Password, LastPass, Bitwarden, Dashlane, Keeper, NordPass), takeout.google.com, account security
and delegation paths (app passwords, passkeys, security keys, backup/recovery codes, access tokens, API keys, SSH/GPG keys,
device activity, third-party/connected/authorized apps, data export, OAuth consent/authorize, Google's /o/oauth2/,
`/settings/tokens|keys|applications|sessions|emails|security`), account portals beyond root and sign-in
(myaccount.google.com, account.microsoft.com, account.live.com, appleid.apple.com). (5) money inside account pages
(`/payments...`, `/payment-methods`, `/billing`, `/purchases`, `/redeem...`, `/addfunds`, `/buy`, `/sell`, `/swap`...,
with `-` as a boundary), SPA fragment routes and `add-to-cart`/`checkout` query actions; a contract test that every
money word of browse.LOGIN_HREF (checkout, cart, basket, subscribe, donate) stays refused with logins lifted. (6)
`vagon.io` refused on the remote PC (his Vagon console; the host page's lock does not govern that browser); a crypto host
rule in the runner itself. (7) paths resolved like a browser (`/wiki/../checkout` is `/checkout`, backslashes, encoded
slashes), in both modes. (8) adult words in the URL itself are refused on the remote PC.

**Not adopted, with the reason:** (3) denying registration, mailboxes and account pages wholesale: the owner's decision
of 2026-10-23 ("Può accedere a tutto quello che vuole") explicitly allows logged-in sessions and account pages, and the
agent's own `login` class (Kimi-reviewed in agent-safety.md) lifts sign-up too; account creation is flagged to the owner
as an open question. (9) default off and strict env parsing: the owner chose default on; `env_bool` keeps the agent's
semantics (only 0/false/no/off turn it off). Click marks do not exist on the remote PC, so (8)'s label point applies to
the pod's Chromium only, which is unchanged.

## Final review: director diff

1. **High — `reap_stale_ffmpeg` / `desktop_hidden`:** A surviving ffmpeg is remembered only in memory as `self.stale_pid`. If that director then restarts, the next instance sees no pidfile—or only a newer ffmpeg’s pid—and can acknowledge `webcam_only` while the forgotten survivor still encodes the desktop. This contradicts the unconditional stale-ffmpeg docstring claim. **Fix:** persist all surviving pids until confirmed dead, or enumerate old director ffmpeg processes, and consult that durable state before every acknowledgement.

2. **Medium — `Director.set_layout`:** `poll_layout_log()` followed by `append_jsonl()` is not atomic with the agent’s append. A POST can re-read just before the agent writes its privacy line, then append its ordinary line afterwards; the privacy line is no longer last and the cut is never entered. Credential typing remains gated, but the login/account page stays visible. **Fix:** use an interprocess lock shared by both writers around check-plus-append, or route privacy transitions through a director-owned atomic endpoint.

3. **Medium — `read_last_record` / `poll_layout_log`:** A valid privacy record longer than the 4096-byte read window is truncated and returns `None`; its file signature is nevertheless cached, so that privacy line is ignored until another append, potentially indefinitely. **Fix:** read back to the preceding newline so the complete record is parsed; enforce a writer-side size bound and fail closed with an alert on overlong records.

4. **Low — startup privacy recovery / `follow_record`:** After a director restart whose last record is a privacy line, `self.layout` is only the fixed layout or `DEFAULT_LAYOUT`; the actual pre-cut request is not recovered. A subsequent `privacy_end` with an invalid/missing layout therefore restores the default—for example, pre-cut `webcam_only` becomes `webcam` with the desktop PiP—contrary to the restore documentation. **Fix:** persist the pre-cut requested layout or scan backwards for the last valid non-privacy request during startup.

**Applied (all four):** D1 at every start the director looks in /proc for every ffmpeg recording into its recordings
directory (argv0 named like ffmpeg, an x11grab or testsrc2 input, the directory on the command line), not only the pid
file's; SIGINT then SIGKILL to all; survivors go to `stale_pids` and block `desktop_hidden` while alive, so a second
restart finds them again. D2 `set_layout` appends a nonce with its line, re-reads the bytes between its read offset and
that line, and when a privacy line landed there it appends it again on top (`reasserted_by: "director"`, event
`privacy_reasserted`) and answers 409; the last line stays the privacy line for a restarted director too. D3 the tail is
64 KB and only a piece before the first newline is dropped, never the last line. D4 the first poll since start (a
restart during a cut) takes the restore target from the last non-privacy request in the tail, else from the privacy
line's `previous`. Tests for each.

## Final review: runner diff

1. **High — `Runner.perform`, `login_url`, `_loggable` (c): URL secrets still reach `events.jsonl`.** `https://user:PW@login.example.com/` is refused as `credentials-in-url`, but `login_url()` returns false and the blocked event records `PW`; likewise, `https://auth.runpod.io/login?token=SECRET` records the query because `owner-service` wins classification. Even when redaction runs, `https://login.example.com/reset-password/SECRET` retains the path token. **Fix:** never log the raw navigate URL: unconditionally remove userinfo/query/fragment, and omit or hash paths on login/account-change URLs. Remote `type` text is masked in the shown event calls; no stdout secret leak is visible in this diff.

2. **High — `remote_url_problem` (a): the account-portal “sign-in” exception admits account management.** `https://appleid.apple.com/account/manage` passes: `LOGIN_PATH` matches `/account/`, although that does not make the page a sign-in page, so `account-settings` is not returned. **Fix:** use a strict sign-in-path allowlist for portals, rather than `LOGIN_PATH`, and apply it to fragment routes as well.

3. **High — `remote_url_problem` / `ACCOUNT_CHANGE_PATH` (a): a real Microsoft 2FA/security page passes.** `https://mysignins.microsoft.com/security-info` matches neither the account hosts nor the security patterns, yet permits changing sign-in methods and related security settings. **Fix:** cover `mysignins.microsoft.com` as an account portal and/or add `security-info` to the refused security paths.

4. **Medium — `blocked_url`, `remote_url_problem` (a): MediaWiki password changes pass.** `https://en.wikipedia.org/wiki/Special:ChangePassword` returns `None` with `allow_login=True`: the `/wiki/` article exemption suppresses one check, and the remote expressions do not recognise this special page. **Fix:** explicitly refuse MediaWiki `Special:ChangePassword` and `Special:PasswordReset` before applying any article exemption.

5. **Medium — `ACCOUNT_CHANGE_PATH`, `ACCOUNT_SECURITY_PATH` (a): common suffixes bypass the rules.** Their terminators omit `.`, so `https://example.com/reset-password.html?token=x` passes with credentials lifted instead of being refused as an account change. **Fix:** use a shared boundary such as `(?=[/?#.]|$)` for both expressions and add suffixed-path tests.

6. **Medium — `_route_paths`, `remote_url_problem` (a): fragment queries are not inspected.** On a fragment-routed SPA, `https://example.com/#/product?add-to-cart=1` passes, and `https://example.com/#/login?next=https%3A%2F%2Fvagon.io%2F` does not recursively check the nested Vagon URL. **Fix:** split the fragment route from its own query, apply `MONEY_QUERY`, and recursively inspect that query’s values.

7. **Medium — `remote_url_problem` (b): ordinary Wikipedia articles are newly refused.** The remote path loop ignores `blocked_url`’s article exemption: `https://en.wikipedia.org/wiki/Security` returns `account-change-path`, and `https://en.wikipedia.org/wiki/Payment` returns `checkout-path`. **Fix:** exempt ordinary `/wiki/` articles from these remote path scans while continuing to handle `Special:*` pages explicitly.

**Applied (all seven):** R1 `loggable_url`: userinfo never; a URL that may carry a secret (`sensitive_url`: credentials
in it, a login/account/account-change/account-security host or path whatever else refuses it, MediaWiki account pages, a
query key named like a token, code, key, password, session...) is logged as `scheme://host/…` only, in both modes; other
remote URLs without query and fragment. R2 a strict `PORTAL_SIGNIN` allowlist (root, /sign-in, /signin, /login, /log-in,
/servicelogin) for the account portals, fragment routes included. R3 mysignins.microsoft.com (plus
myaccount.microsoft.com, account.apple.com, account.google.com) as portals and `security-info` as a security path. R4
`MEDIAWIKI_ACCOUNT` (ChangePassword, PasswordReset, ChangeEmail, ChangeCredentials, RemoveCredentials, OATHManage,
BotPasswords, ResetTokens, Preferences...) before the article exemption, also as `?title=`. R5 `(?=[/?#.]|$)` boundaries
and a password change named inside a segment (`/HelpChangePassword`, `/reset-password.html`). R6 the fragment route and
its own query: money query and nested URLs are checked there too. R7 wiki articles (`/wiki/Security`, `/wiki/Payment`)
keep their exemption on the remote PC (Special: pages do not). Also added after the review: a `type` whose whole text is
one URL or host on the remote PC gets the same check (the address bar typed by hand). Tests for each, including every
URL Kimi named.

## Verification of the fixes (follow-up reviews of the deltas)

### First verification (`q-privacy-review-delta.txt`)

D1 FIXED  
D2 NOT FIXED — `set_layout` takes a fresh `stat` offset after the handler’s initial read; a privacy line landing between those operations is excluded from `_cut_landed_before`, so the POST can overwrite the cut and return 200.  
D3 FIXED  
D4 NOT FIXED — after `A, privacy(A), refused-POST(B), reasserted-privacy(A)`, restart selects refused request `B` as the restore target instead of the privacy line’s `previous` (`A`).  
R1 NOT FIXED — local URLs still log secrets in fragments: `https://app.example/#access_token=…` evades both `SECRET_QUERY` (which examines only `u.query`) and `login_like`.  
R2 NOT FIXED — `PORTAL_SIGNIN` permits arbitrary descendants such as `/login/profile` through `[/?#.].*`, so the exemption is not restricted to the listed sign-in pages.  
R3 FIXED  
R4 FIXED  
R5 FIXED  
R6 FIXED  
R7 FIXED  

NEW:
- **HIGH — `action_policy` / `URL_TOKEN`:** valid typed URLs outside the narrow regex, such as `http://127.0.0.1/` or `https://myaccount.google.com./security`, skip `remote_url_problem` entirely and can bypass navigate policy via the address bar. **Fix:** parse every single HTTP(S) URL token with `urlsplit`/`ipaddress`, including IP literals, localhost and trailing-dot hosts, rather than requiring this regex to match.
- **MEDIUM — `recorder_pids`:** substring matching `recordings_dir` against the joined command line also matches a sibling such as `recordings-old`, causing startup to SIGINT/SIGKILL that unrelated recorder. **Fix:** match individual argv path arguments with path-component boundaries, not a joined-string substring.

**Applied:** D2 the offset is the size the poll read (`_layout_sig`), not a later stat; D4 the reasserted privacy line
carries `refused_nonce`, the running director keeps the previous restore target and a restarted one skips the refused
request; R1 token-like keys are also looked for in the fragment and the fragment route's query (`#access_token=`); R2
`PORTAL_SIGNIN` accepts only the sign-in pages themselves; typed URLs are parsed by `typed_url` (any scheme, IP literals,
localhost, trailing dots); the reaper matches the recordings directory as a path component of one argument (never
`recordings-old`). Tests for each.

### Second verification (`q-privacy-review-delta2.txt`)

D2 offset — FIXED.  
D4 refused POST restore target — FIXED.  
R1 fragment tokens — FIXED.  
R2 PORTAL_SIGNIN — FIXED.  
Typed URLs — NOT FIXED: single-label trailing-dot hosts such as `intranet.` become `intranet` after `rstrip(".")`, fail `TYPED_HOST`, and skip `remote_url_problem`.  
recorder_pids — FIXED.

NEW HIGH — `typed_url`: the blanket `@` rejection is a regression; `myaccount.google.com/?x=a@b` is navigable but skips the portal check. Apply the e-mail exclusion only to authority-like tokens, not when `@` occurs in the path/query/fragment.  
NEW HIGH — `typed_url`: Chromium special-scheme forms such as `http:127.0.0.1/` miss `TYPED_SCHEME` and return `None`, bypassing private-address checks. Reject these forms or browser-canonicalize them before `remote_url_problem`.

**Applied:** Chromium's slashless form (`http:127.0.0.1/`, `https:/localhost/x`) is read as `http(s)://`; an `@` makes a
token an e-mail only before its path (`myaccount.google.com/personal-info?x=a@b` is checked). **Not adopted, with the
reason:** single-label names (`intranet.`, `router/`) are still not taken for URLs: otherwise passwords such as
`Hello123.` or `abc/def` could not be typed (the runner cannot tell the address bar from a password field); IP literals,
localhost and dotted private names (`*.internal`, `*.local`, metadata.google.internal) are caught, and the remote PC is a
cloud VM. Documented as a limit in DESKTOP.md.
