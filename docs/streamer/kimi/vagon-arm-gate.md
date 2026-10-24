# Kimi review (2026-10-23): the Vagon start arming gate

All three findings applied: POST /pc/vagon/start goes through the same check-and-consume (409 until armed); the hold is logged once per off period on every denied path and cleared when the machine is on or starting; tests cover the endpoint, the API fallback, one start per arming, expiry and minutes 0.

1. **High — `POST /pc/vagon/start` bypasses arming.** The new checks cover the automatic page-button path and automatic API fallback, but the unchanged `vagon_start` route still reaches `api_start()` directly. With autostart disabled and no active arm, an admin caller can therefore still start an off computer. It also does not consume the arm or increment `starts`; consequently, a manual start during an armed window can leave that window available for another automatic start. Route every start command through one synchronous check-and-consume operation before any `await`. If this endpoint is intentionally an explicit manual override, that exception needs to be stated explicitly; it is not compatible with the stated no-start-without-arming contract.

2. **Low — `start_held` is inconsistent for API-only and external-start flows.** When the computer is off, no start button exists, and the API fallback is disallowed, the condition merely fails: `start_held` remains false and no held event/log is emitted. Also, `start_held` is cleared only by `consume_start()`. If the owner starts the computer externally while it is held, it can remain true into the connected period and suppress the held log/event during the next off period. Set held state through a common denied-start path and clear it when that off period ends.

3. **Low — tests miss the bypass and important boundaries.** The sole non-autostart scenario exercises the page’s Run button. Most harness tests still explicitly use `autostart=True`. Add non-autostart tests for direct `POST /pc/vagon/start`, API fallback both denied and armed, reload while held/armed, expiration, `{"minutes": 0}`, and failed press/API-call semantics.

The automatic paths shown otherwise use a monotonic deadline and perform check/consume synchronously before awaiting, so no check/consume race or wall-clock defect is evident there. No additional reload bypass is visible in the supplied diff.



