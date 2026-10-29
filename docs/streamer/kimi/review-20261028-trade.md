# Kimi reviews: trading on fomo.family by chat vote (owner 2026-10-28)

Owner decisions (AskUserQuestion): max $10/trade and $50 total enforced by code; chat vote; only liquid/listed coins; deposit QR shown live; fomo.family used despite ToS sec. 16 (bots/automation forbidden: ban and frozen-funds risk), the owner's explicit choice after the warning.

## trade1 (design consult)

**BLOCK**

1. **ToS:** Owner acceptance does not override fomo.family’s prohibition on automated account control. Require written authorization or a platform/API explicitly permitting automation before live trading.
2. **(a) Caps are not enforced:** Typed-amount checks plus prompting cannot stop a $50/$100 preset, duplicate click, or retry. Presets must be configured **≤$10 and then disabled for trading**. Independently verify via OCR/read-back the token contract, chain, side, and exact amount immediately before confirmation; fail closed. One transaction in flight; no automatic retries. “Deposit only what you can lose” limits exposure but does not enforce the stated caps.
3. **(b) Vote abuse:** Named nicks are not unique identities; three nicks proves nothing. Caps limit losses, not vote fraud. Require authenticated unique accounts and one vote/account, or treat chat as advisory and require owner confirmation.
4. **(c) Token selection:** Max liquidity and thresholds do not resolve symbol collisions or manipulation. Use an owner-maintained allowlist of exact `{chain, contract address}` pairs; chat selects only from it. Three days old and $5M FDV are not “established.”
5. **(d) Manipulation appearance:** $10 trades have negligible direct impact, but livestreamed “ape/send it” voting resembles coordinated promotion. Use neutral wording, remove hype vocabulary, rate-limit proposals per nick and coin, suppress repeat-nick campaigns, and avoid thin/new tokens.
6. **(e) Accounting:** Always counting initiated buys as spent is correctly conservative, but it is only a ledger—not an execution cap. Keep pending/ambiguous attempts spent, never subtract sells, prevent concurrent trades/retries, and require explicit owner reconciliation before any reset.

## trade2 (diff review)

CHANGES

1. **Kill switch is incomplete.** Removing `trading-on` stops chat intake but `trade_tick()` still settles votes, queued trades still run, and `trade_guard()` still permits confirms. Cancel open votes/queued trades and block all unconfirmed trade actions while off.
2. **Confirm is not bound to the trade request.** Any request—including a deposit jumping the queue—can supply `trade_confirm` and click anywhere while a trade is active. Require current request `kind == "trade"`, matching trade ID, and the approved host.
3. **Amount guard is bypassable.** `"1,000"` becomes `1.000` and passes; `"100."`, `"1e3"`, etc. bypass the regex. Reject ambiguous/grouped/noncanonical numeric input rather than allowing it.
4. **Ledger writes fail open.** `save()` swallows `OSError`; a restart can restore an older ledger and reuse budget. A failed reservation save must abort the trade and fail closed until repaired.
5. **“Malformed ledger = all spent” is not enforced.** Negative/NaN amounts, invalid `rows`, and bad timestamps can reduce spending or crash checks. Strictly validate schema, finite nonnegative amounts, IDs/sides/statuses, and timestamps; any invalidity means broken/full budget.

Fixes: kill switch cancels votes/queued/unconfirmed trades; confirm bound to the trade request id; only plain amounts typed; ledger fsync + abort on a failed reservation; strict ledger validation (invalid = all spent).

## trade3 (delta review)

APPROVE — Changes 1–5 are correctly implemented; no new correctness or fail-closed regressions found in the delta.

## fix10 (live fixes 10-29: games, drag, streak, cartoon intro, vid, acks, patience, fomo tab, deposit)

APPROVE

## fix11 (play <game> is a game, not leaving the desk)

APPROVE

## fix12 (scroll end no streak, trade how-to refusal, fomo tab reuse, likes ok)

APPROVE

## watch1 (viewers online on the site)

APPROVE: count, 70 s pruning, 5000 cap, salted hashes, safe badge rendering.

## anon1 (nameless viewers are distinct request owners)

APPROVE

## adult2 (known shock-video names in R_ADULT)

APPROVE

## fix13 (songs are fine, play <artist> on youtube is music, illegal chess move recovery)

APPROVE

## fix14 (sing line, game ack)

CHANGES (cover rap/rapping/beatboxing), applied; fix14b APPROVE

## lag1 / lag2 (2026-10-29): stream delay growth and slow PC steps

- Cause measured live: the director stamps the cartoon FIFO by frame count and its live graph waits for the slowest input;
  every frame the feeder dropped on a full pipe left the whole stream 33 ms further behind (9 drops = +0.30 s lag in one
  sample window). Lag grew ~3-5 s/hour and forced a relaunch at 10 s.
- Fix: cartoon_feed.py frame debt (repeat the tick's frame while frames are owed, max 4 per tick, 20 s rebase).
  Agent: THINK_AFTER_ACTION_S 2.5 -> 1.0; the next waiting request starts in the step the previous one ends.
- lag1 (design): GO / GO. lag2 (diff): APPROVE.

## sec1 / sec2 (10-29): a leak story is a topic, asking for a secret is refused

sec1 CHANGES (explicit logins gate; terse asks), applied; sec2 APPROVE

## var1 (10-29): rotating idea, not only fail compilations

APPROVE

## th1 (10-29): his own thesis on fomo, old video tabs closed

APPROVE

## th2 (10-29): operator-only thesis request

APPROVE

## cost1 / cost2 (10-29): shadow off, audience-aware low power, slower looks while watching

cost1 GO (1-3; pod research only), cost2 APPROVE

## held1 (10-29): a failures hold clears itself (90 s, 3/hour)

APPROVE

## held2 (10-29): unchanged key = focus check; idle paces his own inputs too

APPROVE
