# Brain actor: the brain chooses, the room executes

Status: design only. Nothing changed, deployed or published. Private home only.

## Scope and recommendation

A vote needs the brain's live clone, which only the brain server holds. Option A (recommended): one additive route in `home_api.add_home_routes` (`live_server.py:2300`). It needs owner approval: every brain server serves home routes and returns 404 only when `HOME_ENABLED` is off (`home_api.py:49-51`). Option B: no route; the brain only tilts the rule planner.

## 1. Current flow

| Stage | Where | Behaviour |
|---|---|---|
| Tick and choice | `live_server.py:965, 979`; `life.py:636, 660` | `rel` enters every tick; `choose()` picks at an activity end or interrupt |
| Scores | `life.py:353-423, 418-422` | Score 0 means infeasible; `rel` tilts six groups; day plan +0.35, viewer vote +1.2 |
| Brain votes | `brain_vote.py:202`; `live_server.py:1391` | Pick links, music, chess moves and plan steps, never the activity |
| Execution | `life.py:526`; `web/room.html:624, 1915` | `start()` sets duration; the room maps activity to pose |

## 2. Message contract

```
request  {id, seq, state, earliest, not_after, mood, options:[{action, place, device, min, max, networks}]}
answer   {id, seq, state, action, place, device, earliest, duration_min, reason, net, ms}
```

- Options are the feasible set (score > 0), with static network tags, never LLM tags.
- `duration_min` counts from arrival (`life.py:515-521`), clipped to `ACTIVITIES` (`life.py:134-152`).
- Idempotent: a repeated `id` returns the stored answer and starts nothing. Ordered: `seq` only grows. Stale: applied only if `state` still matches.
- Place names differ (`life.py:137, 149-150` against `home_world.py:79-81`: eat, play_console, use_bathroom). Map them once.

## 3. Cadence and delay

- One request per boundary, at activity start. Needs and single options skip the call.
- About 4 per awake simulated hour, one every 40 real seconds at 24x (a simulated hour is 150 real seconds).
- Urgent needs stay rule-only: hunger (`life.py:460-470`), courier (`587-589`), sleep (`631`), bladder (`417`). The brain is asked afterwards.
- The shortest brain-choosable activity lasts 5 real seconds (`life.py:138`), so a 2 s answer lands in time. A late answer costs at most 48 simulated seconds.
- No LLM here: eyes keeps 30 calls per hour and $1 per day (`eyes.py:52-53`). Spiking should get one query per decision; `brain_vote.py:369-384` can query twice today.

## 4. Fallback

- A miss is no valid answer by the deadline, or a stale or invalid one.
- Two misses in a row, or a tick gap over 5 s (`live_server.py:87`), set `mode=rule`. `life.py:660` runs `choose()` as today, and the room logs `actor: rule`.
- Back to brain after 3 valid answers in a row, at a boundary only. The room logs `actor: brain`.

## 5. Devices and "done"

Actions move requested, accepted, observed. Only observed counts as done and reaches the brain as reward.

- PC: one command per 18 real seconds while seated and native-ready (`home_computer.py:159-187`). Today a command counts once written to the guest's stdin (`home_computer.py:96-112`), which is acceptance, not effect. Done needs new serial output and a framebuffer change within 3 simulated minutes.
- Console: play_console (`home_world.py:81`) offers Pong, Minecraft or chess (`web/house/home.js:2069-2078`). Done = paddle, score or Minecraft frame change. It is not PS5 software (`docs/HOME_COORDINATION.md:106`).
- Phone and desk: new frame_id or title (`live_server.py:1211`). Kitchen: dish visible and `life.food` falls (`life.py:643-644`). Bathroom: privacy blocks frames (`home_api.py:53-56`), so the timer decides.

## 6. Verification on the pod

Gate: AGENTS.md's last GPU deadline (2026-10-16 02:19:35 UTC) has passed. Start no pod without new authorization. Device checks use `HOME_NATIVE_REQUIRED=1`.

1. Contract: 500 bad answers (unknown, wrong place, duplicate, old, stale, late). Pass: none applied.
2. Virtual clock, 3 simulated days, real `brain_vote`. Pass: one decision or logged fallback per boundary; at most 4 requests per awake hour; zero LLM calls.
3. Real time at `--time-scale 24` (`live_server.py:2536`), 2 simulated hours. Pass: p95 answer at most 2 s; 95% brain-applied while healthy.
4. Fault: block the route 60 s. Pass: rule takes over at the next boundary; brain returns only after 3 valid answers.
5. Devices: one scripted action each. Pass: zero "done" on acceptance; 95% observed within 3 simulated minutes.
6. Visual: first-person screenshots, viewed against the SimbasJungles reference. Software GL can take 8-16 s a frame (`web/room.html:3795`), so windows run in simulated time.

## 7. Questions for the owner

1. Approve Option A, the additive route? I recommend it.
2. Should hunger, courier, sleep and bladder stay rule-only? I recommend yes.
3. The console is a TV with Pong, Minecraft or chess, not a PlayStation. Is that the device you mean, and what counts as "done"?

Risks: I found no outage audit file under `docs/`, so call limits come from code. Life actions have no network tags yet.
