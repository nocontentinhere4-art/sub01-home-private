# Kimi review (2026-10-23) of the agent safety diff: shadow, guard rails, logins and installs

Model kimi-k3.1-pro; brief `q-agent-safety-review.txt` (in the worker's scratchpad), with the diff of streamer_agent.py, scripts/streamer_watchdog.py, the tests and AGENT.md attached. Verbatim answer below; every finding was fixed (tests named `test_review_*` in tests/test_streamer_agent.py) and the fixes were sent back for a second look (section "Second look").

## Answer

I find **three blockers**; do not commit as-is.

1. **Blocker — `streamer_agent.py`, `Agent.privacy_acked` / `privacy_on`.** A director merely reporting `layout: "webcam"` satisfies the acknowledgement, even if it never read the privacy line and its desktop PiP remains visible. The acknowledgement is also cached indefinitely. The tests’ pre-existing `{"layout":"webcam"}` fake demonstrates this false positive. `webcam` is acceptable **only** as a director privacy mode guaranteeing no desktop PiP, cam-2 monitor feed, or other desktop pixels. Require a per-cut identifier and a fresh acknowledgement such as `{privacy:true, privacy_id:..., desktop_hidden:true}`; refuse typing if the layout append or acknowledgement fails. Add a director integration test of the composed output, not just JSON.

2. **Blocker — `streamer_agent.py`, `decide` / `build_request` / `fire_shadow`.** On the remote PC, the first private frame is sent to the shadow before the primary model can return `private_screen:true`; `req["private"]` reflects only the previous look. Thus “no private frames to the shadow” is not enforced. Skip shadow for vagon until an independent detector exists, or at minimum defer firing until primary validation explicitly returns `private_screen:false`. Test that the first private PC frame never calls `shadow.ask`.

3. **Blocker — `streamer_agent.py`, `decision_row`, `apply`, `dispatch`, `routine_act`.** Secrets enter `typed_secrets` only in `dispatch`, after decision logging. With privacy off—or a refusal before `privacy_on`—a secret appearing in `thought`, `say`, or `chat_replies` can reach `events.jsonl`; `raw_for_log` protects only `raw`. `routine_act` also logs `act=action` before masking/registration. The speech filter additionally ignores secrets shorter than four characters. Register candidate secrets immediately after validation, log only sanitized decisions/actions, omit all generated text during privacy, and use sanitized structures for prompts, memory and state. Add refused-action and secret-in-thought tests.

4. **Should-fix — `streamer_agent.py`, `pc_context` / `apply`.** During a viewer install, `winget install <anything>` remains permitted because `url_ok` examines only URLs. Subsequent landing URLs are checked with generic `model_url_problem`, not the request’s official hosts. Disable shell/winget typing for chat installs and apply the same request-specific validator before dispatch and to landing URLs. Test unrelated winget packages and off-source redirects.

5. **Should-fix — `streamer_agent.py`, `source_ok` / `official_entries`.** A curated prefix such as `github.com/obsproject/obs-studio` also matches `/obsproject/obs-studio-evil`. Additionally, allowing all of `github.com` does not establish vendor provenance. Require exact path-segment boundaries and curated repository `/releases/` paths; do not treat arbitrary GitHub repositories as official sources.

6. **Should-fix — `streamer_agent.py`, `Agent.on_timeout`.** A timed-out Enter or click that submits credentials is not `sensitive`, despite `auth_submission` identifying it. It can therefore be retried after a newer frame instead of holding immediately. Include `auth_submission(action, now)` in the sensitive test and cover both Enter and click timeouts.

7. **Should-fix — `streamer_agent.py`, `act` / `dispatch`.** Broker checks precede awaits for director state and re-observation. A lease revoked or expiring during those awaits can still be followed by dispatch. Re-run deny checks—at least hands-off/lease and caps—immediately before `services.act`, with no intervening await.

8. **Should-fix — `scripts/streamer_watchdog.py`, `Watchdog.trip`.** `tripped_by` is set even when writing STOP fails, so subsequent checks never retry stopping the agent. Latch only after STOP is confirmed; otherwise retry and alert on every check. Also validate the release response body where the runner provides one, rather than treating every HTTP 200 as success.

9. **Should-fix — `streamer_agent.py`, `privacy_clear_look` / `set_layout`.** Held layout requests change `privacy["previous"]` but not `layout_now`. Restoring that different layout leaves agent and director state desynchronized, potentially suppressing a later necessary cut. On successful restoration, update `layout_now`/`layout_at` or re-read director state.

10. **Should-fix — `streamer_agent.py`, shadow lifecycle/budget.** Shadow tasks are cancelled at shutdown but not on STOP, and hourly admission does not reserve in-flight calls, allowing the cap to be exceeded. Cancel and gather them on STOP; reserve budget when creating each task.

11. **Nit — watchdog and tests.** The watchdog counts `wait`/`zoom` rows that the agent’s own rate cap excludes, permitting false trips. Align the vocabularies. The suite also lacks rotation/truncation, STOP-write-failure, and agent-only over-cap watchdog tests; its privacy tests do not prove pixel privacy.

No direct `services.act` bypass of the broker is visible in the supplied diff.


## Second look (the fixes of findings 1-11)

**A blocker remains: finding 3. Findings 1 and 2 are closed; do not commit yet.**

1. **CLOSED (agent side).** Per-cut ID, layout-write failure refusal, and fresh exact ACKs address the bypass. The composed-pixel director test is reported, not supplied, so I cannot independently verify it.
2. **CLOSED.** PC shadow admission now requires validated `private_screen is False` with no active privacy cut; private/unknown answers skip it.
3. **STILL OPEN — blocker.** Registration ordering and structural decision/action logging are substantially fixed, but `SECRET_MIN = 3` still leaves registered one- or two-character credentials unmasked and eligible for speech. No validation rule making such credentials impossible is shown. Handle every registered credential, regardless of length, and test lengths 1/2/3. Also, escaped-form masking was deleted; serialized-raw safety now depends on `raw_for_log`, whose implementation is not supplied.
4. **CLOSED.** Viewer-install command typing and request-specific landing-source validation are wired into PC validation.
5. **STILL OPEN.** Segment boundaries and generic GitHub provenance are fixed, but nothing enforces curated repository **`/releases/`** paths. A curated repository root still authorizes every repository subpath. Curate/release-check the required path prefix.
6. **CLOSED.** The computed submission flag reaches `on_timeout`; Enter and click holds are covered.
7. **CLOSED.** `final_check` rechecks hands-off/lease and both caps after the awaits, with no intervening await before dispatch.
8. **STILL OPEN.** `body.get("session") is not True` accepts `{}`, malformed responses, and `session: 1` as confirmed release. Require an explicit success representation from the runner contract; missing/unknown state must remain unconfirmed. Unconfirmed release also needs continued alerting/retry after STOP latches.
9. **CLOSED.** Restoration now goes through asynchronous `set_layout`, synchronizing successful restoration with agent layout state.
10. **STILL OPEN.** Production cancellation is not gathered; the test gathers externally. Moreover, cancelled calls are charged zero although a request may already have been sent, allowing reservations to be recycled and actual hourly calls to exceed the cap across pauses. Gather on STOP and conservatively charge/reserve at admission.
11. **STILL OPEN (test nit).** Wait/zoom handling and the other watchdog cases improved, but the “rotation” test only truncates via `write_text`; add an `os.replace` rotation test. Pixel coverage is absent from this suite.

**New bug — Low, `register_secret`/`dispatch`:** every ordinary credential is appended during registration and again unconditionally in dispatch; repeats grow `typed_secrets` indefinitely. Reuse `register_secret` or append only when absent.


## Third look (the fixes of the second look)

3. **STILL OPEN** — short-credential refusal, threshold removal, speech filtering, and quote/backslash escaping are fixed. **New bug: High, `scrub_text`.** It generates only the `ensure_ascii=False` JSON form. For registered `pässword`, raw JSON produced by ordinary `json.dumps(...)`—as the tests use—contains `p\u00e4ssword`; neither replacement matches, leaving a recoverable credential in `events.jsonl`. Fix: mask both `ensure_ascii` forms for the current serializer and add a non-ASCII regression test. For arbitrary raw JSON, prefer logging the parsed, scrubbed decision rather than the raw answer.

5. **CLOSED** — curated, generated, and owner-supplied GitHub hosts are constrained to repository `/releases` paths; the raw-executable and whole-account cases are covered.

8. **CLOSED** — confirmation now requires HTTP 200 plus exactly `session: false` or `privacy: true`; `{}` remains pending, is logged, and is retried with an ALERT.

10. **CLOSED** — admission records the call, completion adds only `"call": false` spend, reload distinguishes those rows, and pause cancels and gathers shadow tasks.

11. **CLOSED** — the `os.replace` test demonstrates that all 15 old-file and six new-file actions are counted.

**Duplicate append: CLOSED** — both registration and dispatch use the deduplicating `add_secret`.

**Blocker remains: yes, finding 3’s credential-masking hole.** No other new blocker is evident in the supplied delta.


## Fourth look (masking of every JSON escape form)

**Finding 3: STILL OPEN**, although both supplied regressions are fixed. New bug: containment searches `json.dumps(d)`, not fully decoded text. For decoded credential `Abcd1234"Z9`, emitted with its quote as `\u0022`, `blob` contains `\"`; containment fails, and neither canonical scrub form matches `\u0022`. The escaped raw credential can therefore survive without re-serialization or withholding. Recursively search decoded string keys/values for detection, then reuse the current scrub/re-serialize/fallback path; add this regression. No other new bug is evident. **A credential-leak blocker remains** unless secret text is explicitly restricted to exclude quotes, backslashes, and control characters; no such restriction is shown.


## Fifth look (raw answers never logged as is once a credential is known)

Finding 3’s original escape/prose defect is **CLOSED**: credential-known paths discard the raw answer, mask decoded strings and keys, and withhold on failure.

**New bug:** non-string JSON scalars bypass `mask_decoded`. With `typed_secrets=["12345678"]`, a parseable answer containing `{"pin":12345678}` is re-serialized with `12345678` intact, exposing the credential; the old containment path would have withheld it. Handle matching scalar occurrences or withhold when the serialized result still contains a secret, and add a numeric-PIN regression test.

**Blocker:** yes, at `raw_for_log`’s stated safety boundary. A downstream scrub might mitigate this, but that guarantee is not shown.


## Sixth look (numeric credentials)

CLOSED. No new bug is evident in the supplied delta, and no blocker remains on the material provided. Recursive scalar masking now handles numeric PINs while preserving unrelated booleans, `None`, and floats. The post-serialization guard fails closed by withholding the entire raw value whenever a literal credential survives. Tests cover top-level and nested numeric values plus unaffected scalars; downstream scrubbing additionally covers registered escaped forms. Unshown call sites cannot be assessed from this delta.


Outcome: no blocker remains (sixth look). Open by design, reported to the coordinator: the director must prove pixel-level privacy (its webcam layout carries a desktop PiP; it acknowledges a cut only with privacy_id + desktop_hidden), the runner's own HOST_RULES still refuse login hosts on navigate, click provenance and UAC identity on the remote PC cannot be verified from pixels.
